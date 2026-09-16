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
from backend.services.process_mining import compute_process_graph, filter_event_log
from backend.services import storage as storage_svc

router = APIRouter()


@router.get("/api/process-graph")
@router.get("/api/process-map")
def get_process_graph(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
    start_date: Optional[str] = Query(None, description="Filter: start date ISO string"),
    end_date: Optional[str] = Query(None, description="Filter: end date ISO string"),
    resource: Optional[list[str]] = Query(None, description="Filter: resource (repeatable or comma-separated)"),
    min_duration_hours: Optional[float] = Query(None, description="Filter: min cycle time in hours"),
    max_duration_hours: Optional[float] = Query(None, description="Filter: max cycle time in hours"),
):
    """Return interactive process graph JSON (nodes + edges with stats), with optional filtering."""
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

    has_filters = any([
        bool(start_date and str(start_date).strip()),
        bool(end_date and str(end_date).strip()),
        bool(resource),
        min_duration_hours is not None,
        max_duration_hours is not None,
    ])

    if has_filters:
        try:
            import pandas as pd
            raw_df = pd.read_csv(str(log_path))
            filtered_df, matched_cases, total_cases = filter_event_log(
                raw_df,
                start_date=start_date,
                end_date=end_date,
                resources=resource,
                min_duration_hours=min_duration_hours,
                max_duration_hours=max_duration_hours,
            )
            if matched_cases < 2:
                res = {
                    "available": True,
                    "nodes": [],
                    "edges": [],
                    "matched_cases": matched_cases,
                    "total_cases": total_cases,
                    "filtered": True,
                    "message": "Not enough cases match these filters to discover a process",
                    "fallback": is_fallback,
                }
            else:
                graph = compute_process_graph(df=filtered_df)
                res = {
                    "available": True,
                    **graph,
                    "matched_cases": matched_cases,
                    "total_cases": total_cases,
                    "filtered": True,
                    "fallback": is_fallback,
                }
            if is_fallback:
                res["warning"] = storage_svc.FALLBACK_WARNING
            return res
        except Exception as exc:
            return JSONResponse(status_code=500, content={"error": str(exc)})

    # Unfiltered baseline path
    try:
        graph = compute_process_graph(log_path)
        res = {"available": True, **graph, "fallback": is_fallback}
        if is_fallback:
            res["warning"] = storage_svc.FALLBACK_WARNING
        return res
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

