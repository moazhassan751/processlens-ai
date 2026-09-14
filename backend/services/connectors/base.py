"""
ProcessLens — Base Connector & Deterministic Normalization
===========================================================
Defines the abstract base class for all data ingestion connectors.
Enforces the standardized ingestion lifecycle:
  1. Validate configuration
  2. Test connection
  3. Retrieve source records (read-only)
  4. Deterministic normalization & column mapping
  5. Validate canonical event log (using existing validate_data)
  6. Workspace & run isolated persistence
  7. Return ingestion telemetry
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from backend.config import (
    PROJECT_ROOT,
    STORAGE_ROOT,
    OUTPUT_FILES,
    UPLOAD_STATE_FILE,
    EVENT_LOG_PREVIOUS,
)
from backend.models.event_log import (
    CANONICAL_COLUMNS,
    CANONICAL_COLUMN_SET,
    ColumnMapping,
)
from backend.services import storage as storage_svc

logger = logging.getLogger("processlens.connectors")


class BaseConnector(ABC):
    """
    Abstract lifecycle for ProcessLens data source connectors.
    All connectors feed the existing pipeline without creating separate processing pipelines.
    """

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def validate_config(self) -> Tuple[bool, Optional[str]]:
        """Validate credentials, host, table, and connection parameters."""
        pass

    @abstractmethod
    def test_connection(self, column_mapping: Optional[ColumnMapping] = None) -> dict:
        """
        Verify database or API accessibility, table existence, and columns.
        Returns { 'success': bool, 'message': str, 'available_columns': list[str], 'row_count': int }
        """
        pass

    @abstractmethod
    def fetch_records(self, mapping: ColumnMapping, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Execute read-only query to retrieve source rows.
        Returns a DataFrame with columns matching the source table.
        """
        pass

    def normalize_records(self, df: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
        """
        Deterministically transforms raw source DataFrame into canonical ProcessLens event log:
          ['case_id', 'activity', 'timestamp', 'resource']
        
        Requirements:
          - Deterministic mapping of source columns
          - Stripping string values
          - Parsing timestamps into ISO-8601 strings
          - Rejecting null required values
          - Preserving original activity, case_id, and resource semantics
        """
        if df is None or df.empty:
            raise ValueError("Retrieved dataset contains no records.")

        # Validate source columns exist in retrieved DataFrame
        source_cols = {
            "case_id": mapping.case_id.strip(),
            "activity": mapping.activity.strip(),
            "timestamp": mapping.timestamp.strip(),
            "resource": mapping.resource.strip(),
        }

        for canonical_col, src_col in source_cols.items():
            if src_col not in df.columns:
                raise ValueError(
                    f"Source column '{src_col}' mapped to '{canonical_col}' was not found in retrieved data. "
                    f"Available columns: {list(df.columns)}"
                )

        # Build normalized DataFrame
        norm_df = pd.DataFrame()
        norm_df["case_id"] = df[source_cols["case_id"]].astype(str).str.strip()
        norm_df["activity"] = df[source_cols["activity"]].astype(str).str.strip()

        # Deterministic timestamp parsing
        parsed_ts = pd.to_datetime(df[source_cols["timestamp"]], errors="coerce")
        if parsed_ts.isna().all():
            raise ValueError(
                f"Unable to parse valid timestamps from column '{source_cols['timestamp']}'."
            )
        norm_df["timestamp"] = parsed_ts.dt.strftime("%Y-%m-%d %H:%M:%S")

        # Resource mapping
        norm_df["resource"] = df[source_cols["resource"]].astype(str).str.strip()

        # Replace empty strings with NaN for strict checking
        for col in CANONICAL_COLUMNS:
            norm_df[col] = norm_df[col].replace(r"^\s*$", None, regex=True)

        # Drop rows with null values in required canonical columns
        initial_len = len(norm_df)
        norm_df = norm_df.dropna(subset=["case_id", "activity", "timestamp"]).reset_index(drop=True)
        if len(norm_df) < initial_len:
            logger.warning(
                f"Dropped {initial_len - len(norm_df)} rows with missing case_id, activity, or timestamp."
            )

        # Fill missing resource with 'SYSTEM' if any
        norm_df["resource"] = norm_df["resource"].fillna("SYSTEM")

        # Sort chronologically within case to ensure monotonic sequence
        norm_df["_parsed"] = pd.to_datetime(norm_df["timestamp"])
        norm_df = norm_df.sort_values(by=["case_id", "_parsed"]).drop(columns=["_parsed"]).reset_index(drop=True)

        return norm_df[CANONICAL_COLUMNS]

    def validate_canonical_df(self, df: pd.DataFrame) -> Tuple[bool, list[str]]:
        """
        Run the exact Phase A validation checks using validate_data.py.
        Returns (is_valid: bool, error_messages: list[str]).
        """
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
            return False, [f"Could not run validation: {exc}"]
        finally:
            if inserted and root_str in sys.path:
                sys.path.remove(root_str)

        if not passed:
            fail_lines = [
                line.strip().replace("  [FAIL] ", "")
                for line in report.splitlines()
                if "[FAIL]" in line
            ]
            # Ignore "Unexpected activities" for external connector logs as domain vocabularies vary
            content_errors = [
                line for line in fail_lines if "Unexpected activities" not in line
            ]
            if content_errors:
                return False, content_errors

        return True, []

    def persist_normalized_log(
        self,
        df: pd.DataFrame,
        project_id: str,
        source_type: str,
        table_or_source_name: str,
    ) -> dict:
        """
        Saves the validated canonical DataFrame into the isolated project workspace
        and updates the active runtime environment.
        """
        row_count = len(df)
        case_count = int(df["case_id"].nunique())
        activity_count = int(df["activity"].nunique())

        csv_content = df.to_csv(index=False).encode("utf-8")

        # 1. Project-level isolation: save into storage/projects/{project_id}/uploads/event_log.csv
        try:
            proj_dir = storage_svc.ensure_project(project_id)
            proj_upload_path = proj_dir / "uploads" / "event_log.csv"
            with open(str(proj_upload_path), "wb") as f:
                f.write(csv_content)
        except Exception as exc:
            logger.warning(f"Could not write project upload copy: {exc}")

        # 2. Active root-level file for backward compatibility
        event_log_path = OUTPUT_FILES["event_log"]
        backup_created = False
        if event_log_path.exists():
            try:
                shutil.copy2(str(event_log_path), str(EVENT_LOG_PREVIOUS))
                backup_created = True
            except Exception as exc:
                logger.warning(f"Failed to create event_log backup: {exc}")

        with open(str(event_log_path), "wb") as f:
            f.write(csv_content)

        # 3. Clean stale downstream outputs
        stale_to_delete = ["predictions", "explanation_output", "conformance"]
        deleted_stale: list[str] = []
        for key in stale_to_delete:
            p = OUTPUT_FILES.get(key)
            if p and p.exists():
                try:
                    p.unlink()
                    deleted_stale.append(p.name)
                except Exception as exc:
                    logger.warning(f"Could not delete stale output {p.name}: {exc}")

        # 4. Compute date range
        parsed_ts = pd.to_datetime(df["timestamp"])
        min_ts = parsed_ts.min()
        max_ts = parsed_ts.max()
        date_range = {
            "start": min_ts.isoformat(),
            "end": max_ts.isoformat(),
            "duration_days": round((max_ts - min_ts).total_seconds() / 86400.0, 1),
        }

        # 5. Write upload state (NEVER store passwords or connection strings!)
        now_iso = datetime.now(timezone.utc).isoformat()
        state = {
            "source": source_type,
            "filename": table_or_source_name,
            "row_count": row_count,
            "case_count": case_count,
            "activity_count": activity_count,
            "upload_time": now_iso,
            "project_id": project_id,
        }
        try:
            with open(str(UPLOAD_STATE_FILE), "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as exc:
            logger.error(f"Failed to write upload state: {exc}")

        return {
            "accepted": True,
            "source_type": source_type,
            "project_id": project_id,
            "table_name": table_or_source_name,
            "row_count": row_count,
            "case_count": case_count,
            "activity_count": activity_count,
            "date_range": date_range,
            "import_time": now_iso,
            "backup_created": backup_created,
            "deleted_stale": deleted_stale,
            "message": (
                f"Successfully imported {row_count} events across {case_count} cases "
                f"from {source_type} source '{table_or_source_name}'."
            ),
        }
