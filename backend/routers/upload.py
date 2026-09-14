"""
ProcessLens — Upload Router
==============================
File upload and reset-to-synthetic endpoints with enhanced CSV validation.
Preserved from Phase 5/6/7 with identical response shapes.
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import sys
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse

from backend.security import require_api_key

from backend.config import (
    PROJECT_ROOT, OUTPUT_FILES, UPLOAD_STATE_FILE,
    EVENT_LOG_PREVIOUS, REQUIRED_COLUMNS, VENV_PYTHON,
    GRAPHVIZ_BIN,
)
from backend.services import storage as storage_svc

logger = logging.getLogger("processlens.upload")
router = APIRouter()


# ---------------------------------------------------------------------------
# Upload state helpers
# ---------------------------------------------------------------------------

def _read_upload_state() -> dict:
    try:
        if UPLOAD_STATE_FILE.exists():
            with open(str(UPLOAD_STATE_FILE), encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning(f"Failed to read upload state: {exc}")
    return {"source": "synthetic"}


def _write_upload_state(state: dict) -> None:
    try:
        with open(str(UPLOAD_STATE_FILE), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        logger.error(f"Failed to write upload state: {exc}")


def _clear_upload_state() -> None:
    _write_upload_state({"source": "synthetic"})


FORMULA_PREFIXES = ("=", "+", "-", "@")


def _is_numeric(val: any) -> bool:
    """Check if value is genuine numeric or converts cleanly to a number."""
    if isinstance(val, (int, float, complex)) and not isinstance(val, bool):
        return True
    try:
        s = str(val).strip()
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def sanitize_cell_value(val: any, is_timestamp_col: bool = False) -> any:
    """
    Sanitize a single CSV cell value against spreadsheet formula injection.
    Prefixes text cells beginning with '=', '+', '-', '@' with a single quote.
    Preserves genuine numeric values, booleans, nulls, and timestamps.
    """
    import pandas as pd
    if val is None or pd.isna(val) or is_timestamp_col:
        return val

    # Preserve numeric types directly
    if isinstance(val, (int, float, complex)) and not isinstance(val, bool):
        return val

    # Only inspect string-like / text values
    if isinstance(val, str):
        trimmed = val.strip()
        if trimmed.startswith(FORMULA_PREFIXES):
            # Check if this is a genuine numeric representation (e.g. -5, -3.14, +42)
            if _is_numeric(trimmed):
                return val
            # Text starting with dangerous prefix -> neutralize with leading single quote
            return f"'{val}"

    return val


def sanitize_dataframe_for_csv(df) -> any:
    """
    Sanitize an entire DataFrame to prevent CSV formula injection before persistence.
    Preserves numeric dtypes, timestamps, and genuine negative/positive numbers.
    """
    import pandas as pd
    df_clean = df.copy()
    for col in df_clean.columns:
        col_lower = str(col).lower().strip()
        is_ts = "timestamp" in col_lower or pd.api.types.is_datetime64_any_dtype(df_clean[col])

        # Skip numeric dtypes entirely
        if pd.api.types.is_numeric_dtype(df_clean[col]) or is_ts:
            continue

        # Sanitize object/string column values
        df_clean[col] = df_clean[col].apply(lambda v: sanitize_cell_value(v, is_timestamp_col=is_ts))

    return df_clean


def _validate_uploaded_csv(content: bytes, filename: str):
    """Validate an uploaded CSV. Returns (ok: bool, errors: list[str], df_or_None)."""
    import pandas as pd

    # 1. Empty content check
    if not content or len(content.strip()) == 0:
        return False, ["CSV file is empty"], None

    # 2. Parse CSV
    try:
        df = pd.read_csv(io.BytesIO(content))
    except pd.errors.EmptyDataError:
        return False, ["CSV file is empty"], None
    except pd.errors.ParserError as exc:
        first_line = str(exc).splitlines()[0]
        return False, [f"Malformed CSV structure: {first_line}"], None
    except Exception as exc:
        first_line = str(exc).splitlines()[0]
        return False, [f"Malformed CSV structure: {first_line}"], None

    # 3. Empty data records
    if df is None or len(df) == 0 or df.empty:
        return False, ["Dataset contains no valid event records"], None

    # 4. Required columns
    actual_cols = set(df.columns.astype(str).str.strip())
    missing_cols = REQUIRED_COLUMNS - actual_cols
    extra_cols = actual_cols - REQUIRED_COLUMNS

    errors: list[str] = []
    if missing_cols:
        if len(missing_cols) == 1:
            errors.append(f"Missing required column: {sorted(missing_cols)[0]}")
        else:
            errors.append(f"Missing required columns: {sorted(missing_cols)}")
    if extra_cols:
        errors.append(f"Extra columns not allowed: {sorted(extra_cols)}")

    if errors:
        return False, errors, None

    df.columns = df.columns.astype(str).str.strip()

    # Sanitize dataframe against formula injection before validation and persistence
    df = sanitize_dataframe_for_csv(df)

    # 5. Run thorough validation using validate_data module
    root_str = str(PROJECT_ROOT)
    inserted = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        inserted = True
    try:
        from validate_data import validate
        passed, report = validate(df)
    except Exception as exc:
        logger.error(f"Validation execution error: {exc}")
        return False, [f"Could not run validation: {exc}"], None
    finally:
        if inserted and root_str in sys.path:
            sys.path.remove(root_str)

    if not passed:
        fail_lines = [
            line.strip().replace("  [FAIL] ", "")
            for line in report.splitlines()
            if "[FAIL]" in line
        ]
        # Ignore "Unexpected activities" for uploaded files as custom domain logs vary
        content_errors = [
            line for line in fail_lines if "Unexpected activities" not in line
        ]
        if content_errors:
            return False, content_errors, None

    return True, [], df


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/upload", dependencies=[Depends(require_api_key)])
async def upload_event_log(
    file: UploadFile = File(...),
    project_id: str = Query("default", description="Workspace project ID"),
):
    """Accept a CSV file via multipart form upload."""
    content = await file.read()
    original_filename = file.filename or "upload.csv"

    ok, errors, df = _validate_uploaded_csv(content, original_filename)
    if not ok:
        logger.warning(f"Upload rejected for '{original_filename}': {errors}")
        return JSONResponse(
            status_code=422,
            content={
                "accepted": False,
                "filename": original_filename,
                "errors": errors,
            },
        )

    row_count = len(df)

    # Project-level isolation: save sanitized copy in project's uploads directory
    try:
        proj_dir = storage_svc.ensure_project(project_id)
        proj_upload_path = proj_dir / "uploads" / "event_log.csv"
        df.to_csv(str(proj_upload_path), index=False)
    except Exception as exc:
        logger.warning(f"Could not write project upload copy: {exc}")

    # Active root-level file for backward compatibility
    event_log_path = OUTPUT_FILES["event_log"]
    if event_log_path.exists():
        shutil.copy2(str(event_log_path), str(EVENT_LOG_PREVIOUS))

    df.to_csv(str(event_log_path), index=False)

    # Delete stale predictions and explanation files
    stale_to_delete = ["predictions", "explanation_output"]
    deleted: list[str] = []
    for key in stale_to_delete:
        p = OUTPUT_FILES[key]
        if p.exists():
            p.unlink()
            deleted.append(p.name)

    from datetime import datetime as _dt
    _write_upload_state({
        "source": "uploaded",
        "filename": original_filename,
        "row_count": row_count,
        "upload_time": _dt.now().isoformat(),
        "project_id": project_id,
    })

    logger.info(f"Accepted upload '{original_filename}' with {row_count} rows for project '{project_id}'")

    return {
        "accepted": True,
        "data_source": "uploaded",
        "filename": original_filename,
        "row_count": row_count,
        "backup_created": EVENT_LOG_PREVIOUS.exists(),
        "deleted_stale": deleted,
        "message": (
            f"Uploaded '{original_filename}' ({row_count} rows) accepted. "
            f"event_log.csv replaced. "
            + (f"Deleted stale outputs: {deleted}." if deleted else "No stale outputs to delete.")
        ),
    }


@router.post("/api/reset-to-synthetic", dependencies=[Depends(require_api_key)])
@router.post("/api/reset", dependencies=[Depends(require_api_key)])
def reset_to_synthetic():
    """Discard uploaded log, regenerate synthetic data."""
    import subprocess, os

    env = os.environ.copy()
    if os.path.isdir(GRAPHVIZ_BIN) and GRAPHVIZ_BIN not in env.get("PATH", ""):
        env["PATH"] = GRAPHVIZ_BIN + os.pathsep + env.get("PATH", "")

    generate_script = PROJECT_ROOT / "generate_data.py"
    result = subprocess.run(
        [str(VENV_PYTHON), str(generate_script)],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )

    if result.returncode != 0:
        logger.error(f"generate_data.py failed during reset: {result.stderr}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "generate_data.py failed during reset.",
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        )

    if EVENT_LOG_PREVIOUS.exists():
        EVENT_LOG_PREVIOUS.unlink()

    _clear_upload_state()
    logger.info("Reset to synthetic event log completed.")

    return {
        "success": True,
        "data_source": "synthetic",
        "message": "Reset complete. Synthetic event_log.csv regenerated from generate_data.py.",
        "stdout": result.stdout,
    }
