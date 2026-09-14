"""
ProcessLens — Data Router
===========================
Read-only endpoints that serve live flat-file data.
These endpoints are 100% backward compatible with Phase 4/5/6.
"""

from __future__ import annotations

import json

from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse

from backend.config import OUTPUT_FILES
from backend.services.process_mining import compute_bottlenecks, compute_paths
from backend.services.ml_service import compute_prediction_data
from backend.services.data_quality import compute_data_quality
from backend.services import storage as storage_svc

router = APIRouter()


def _file_exists(key: str) -> bool:
    return OUTPUT_FILES[key].exists()


def _not_available(resource: str) -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content={
            "available": False,
            "message": f"{resource} not yet available. Run the pipeline first.",
            "fallback": False,
        },
    )


# ---------------------------------------------------------------------------
# Status & Data Quality
# ---------------------------------------------------------------------------

@router.get("/api/status")
def get_status():
    """Return which output files currently exist on disk, plus upload metadata and data quality."""
    from backend.config import UPLOAD_STATE_FILE

    status = {key: path.exists() for key, path in OUTPUT_FILES.items()}
    phase1_done = status["event_log"] and status["process_map"]
    phase2_done = status["predictions"] and status["delay_model"] and status["open_cases"]
    phase3_done = status["explanation_output"]

    upload_state = _read_upload_state()
    stale = _compute_stale_flags(upload_state)
    data_quality = compute_data_quality() if status["event_log"] else None

    return {
        "files": status,
        "phases": {
            "phase1": phase1_done,
            "phase2": phase2_done,
            "phase3": phase3_done,
        },
        "data_source": upload_state.get("source", "synthetic"),
        "upload_meta": {
            "filename":  upload_state.get("filename"),
            "row_count": upload_state.get("row_count"),
        } if upload_state.get("source") != "synthetic" else None,
        "stale": stale,
        "data_quality": data_quality,
    }


@router.get("/api/data-quality")
def get_data_quality(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """Return comprehensive data-quality summary computed directly from active dataset."""
    log_path, is_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "event_log")
    if not log_path or not log_path.exists():
        return _not_available("event_log.csv")
    try:
        dq = compute_data_quality(log_path)
        if isinstance(dq, dict):
            dq["fallback"] = is_fallback
            if is_fallback:
                dq["warning"] = storage_svc.FALLBACK_WARNING
        return dq
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@router.get("/api/discovery")
def get_discovery(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """Return the bottleneck table as JSON."""
    log_path, is_log_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "event_log")
    if not log_path or not log_path.exists():
        return _not_available("event_log.csv")
    try:
        bottlenecks = compute_bottlenecks(log_path)
    except Exception as exc:
        return JSONResponse(
            status_code=500, content={"error": f"Failed to compute bottlenecks: {exc}"}
        )

    map_path, is_map_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "process_map")
    is_fallback = is_log_fallback or (is_map_fallback if run_id else False)

    res = {
        "available": True,
        "process_map_exists": map_path is not None and map_path.exists(),
        "bottlenecks": bottlenecks,
        "fallback": is_fallback,
    }
    if is_fallback:
        res["warning"] = storage_svc.FALLBACK_WARNING
    return res


@router.get("/api/discovery/paths")
def get_discovery_paths(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """Return discovered path variants from event_log.csv."""
    log_path, is_log_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "event_log")
    if not log_path or not log_path.exists():
        return _not_available("event_log.csv")
    map_path, is_map_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "process_map")
    if not map_path or not map_path.exists():
        return _not_available("process_map.png (Phase 1 not fully complete)")

    is_fallback = is_log_fallback or (is_map_fallback if run_id else False)
    try:
        path_strings = compute_paths(log_path)
    except Exception as exc:
        path_strings = [f"(Could not extract paths: {exc})"]
    res = {"available": True, "paths": path_strings, "fallback": is_fallback}
    if is_fallback:
        res["warning"] = storage_svc.FALLBACK_WARNING
    return res


@router.get("/api/discovery/map")
def get_process_map(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """Serve process_map.png as an image file response."""
    map_path, is_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "process_map")
    if not map_path or not map_path.exists():
        return _not_available("process_map.png")
    headers = {"X-ProcessLens-Fallback": "true" if is_fallback else "false"}
    if is_fallback:
        headers["X-ProcessLens-Warning"] = storage_svc.FALLBACK_WARNING
    return FileResponse(str(map_path), media_type="image/png", headers=headers)


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

@router.get("/api/predictions")
def get_predictions(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """Return model metrics, feature importances, and open cases."""
    pred_path, is_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "predictions")
    if not pred_path or not pred_path.exists():
        return _not_available("predictions.json")
    try:
        dm_path, _ = storage_svc.resolve_artifact_path(project_id, run_id, "delay_model")
        td_path, _ = storage_svc.resolve_artifact_path(project_id, run_id, "training_data")
        pred_data = compute_prediction_data(
            predictions_path=pred_path,
            delay_model_path=dm_path,
            training_data_path=td_path,
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    res = {"available": True, **pred_data, "fallback": is_fallback}
    if is_fallback:
        res["warning"] = storage_svc.FALLBACK_WARNING
    return res


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------

@router.get("/api/explanation")
def get_explanation(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """Return the full contents of explanation_output.json."""
    exp_path, is_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "explanation_output")
    if not exp_path or not exp_path.exists():
        return _not_available("explanation_output.json")
    try:
        with open(str(exp_path), encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    res = {"available": True, **data, "fallback": is_fallback}
    if is_fallback:
        res["warning"] = storage_svc.FALLBACK_WARNING
    return res


# ---------------------------------------------------------------------------
# Helpers (from original main.py)
# ---------------------------------------------------------------------------

def _read_upload_state() -> dict:
    from backend.config import UPLOAD_STATE_FILE
    try:
        if UPLOAD_STATE_FILE.exists():
            with open(str(UPLOAD_STATE_FILE), encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"source": "synthetic"}


def _compute_stale_flags(upload_state: dict) -> dict:
    event_log = OUTPUT_FILES["event_log"]
    if not event_log.exists():
        return {"discovery": False, "prediction": False, "recommendation": False}
    el_mtime = event_log.stat().st_mtime

    def _stale(key: str) -> bool:
        p = OUTPUT_FILES[key]
        if not p.exists():
            return False
        return el_mtime > p.stat().st_mtime

    return {
        "discovery":      _stale("process_map"),
        "prediction":     _stale("predictions"),
        "recommendation": _stale("explanation_output"),
    }
