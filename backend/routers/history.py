"""
ProcessLens — History Router
===============================
Supabase-backed history endpoints (Phase 6 compat).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.services import supabase_client as sb

router = APIRouter()


@router.get("/api/runs")
def get_runs(limit: int = 10):
    """Return recent pipeline runs ordered most recent first."""
    runs = sb.get_pipeline_runs(limit)
    if runs is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Supabase client not initialized or unavailable."},
        )
    return {"runs": runs}


@router.get("/api/runs/{run_id}")
def get_run_details(run_id: str):
    """Return full discovery, prediction, and explanation results for a past run."""
    result = sb.get_run_details(run_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": f"Run '{run_id}' not found."})
    return result
