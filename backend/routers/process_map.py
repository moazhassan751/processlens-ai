"""
ProcessLens — Process Map Router
===================================
Interactive process graph endpoint (Phase 7 Feature 2).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.config import OUTPUT_FILES
from backend.services.process_mining import compute_process_graph
from backend.services import storage as storage_svc

router = APIRouter()


@router.get("/api/process-graph")
@router.get("/api/process-map")
def get_process_graph(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """Return interactive process graph JSON (nodes + edges with stats)."""
    log_path, is_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "event_log")
    if not log_path or not log_path.exists():
        return JSONResponse(
            status_code=202,
            content={
                "available": False,
                "message": "event_log.csv not yet available. Run the pipeline first.",
                "fallback": False,
            },
        )
    try:
        graph = compute_process_graph(log_path)
        res = {"available": True, **graph, "fallback": is_fallback}
        if is_fallback:
            res["warning"] = storage_svc.FALLBACK_WARNING
        return res
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
