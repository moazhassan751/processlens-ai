"""
ProcessLens — Simulation Router
=================================
REST API endpoints for deterministic What-If Process Simulation (Phase F).
Allows business analysts to simulate operational interventions
and estimate cycle-time impacts against actual baseline event logs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.config import OUTPUT_FILES
from backend.services import storage as storage_svc
from backend.services.simulation_service import compute_simulation_baseline, simulate_scenario

logger = logging.getLogger("processlens.simulation")
router = APIRouter()


class SimulationRunRequest(BaseModel):
    project_id: str = Field("default", description="Workspace project ID")
    run_id: Optional[str] = Field(None, description="Specific run ID")
    scenario_type: str = Field(
        "bottleneck_wait_reduction",
        description="Scenario type: bottleneck_wait_reduction, rework_reduction, activity_duration_reduction, resource_capacity",
    )
    target_activity: Optional[str] = Field(None, description="Target activity to adjust")
    target_resource: Optional[str] = Field(None, description="Target resource for capacity scaling")
    reduction_pct: float = Field(30.0, description="Intervention reduction percentage (0 to 100)")
    capacity_increase_pct: Optional[float] = Field(None, description="Optional capacity addition percentage")


def _resolve_event_log(project_id: str, run_id: Optional[str]) -> tuple[Optional[Path], bool]:
    """Resolve event log path respecting strict workspace and run isolation with fallback tracking."""
    return storage_svc.resolve_artifact_path(project_id, run_id, "event_log")


@router.get("/api/simulation/baseline")
def get_baseline(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """
    Return baseline operational metrics and candidate activities/bottlenecks
    derived from the active event log.
    """
    event_log_path, is_fallback = _resolve_event_log(project_id, run_id)

    if not event_log_path or not event_log_path.exists() or event_log_path.stat().st_size == 0:
        return JSONResponse(
            status_code=202,
            content={
                "available": False,
                "message": "Simulation requires a completed process analysis. Run the pipeline first.",
                "fallback": False,
            },
        )

    try:
        baseline = compute_simulation_baseline(event_log_path)
        if not baseline.get("available"):
            baseline["fallback"] = False
            return JSONResponse(status_code=202, content=baseline)
        baseline["fallback"] = is_fallback
        if is_fallback:
            baseline["warning"] = storage_svc.FALLBACK_WARNING
        return JSONResponse(status_code=200, content=baseline)
    except Exception as exc:
        logger.exception(f"Failed to fetch simulation baseline: {exc}")
        return JSONResponse(
            status_code=500,
            content={"available": False, "error": f"Failed to compute baseline: {str(exc)}"},
        )


@router.post("/api/simulation/run")
def run_simulation(req: SimulationRunRequest):
    """
    Execute a deterministic What-If simulation scenario.
    Compares simulated cycle-time outcomes against the observed baseline.
    """
    event_log_path, is_fallback = _resolve_event_log(req.project_id, req.run_id)

    if not event_log_path or not event_log_path.exists() or event_log_path.stat().st_size == 0:
        return JSONResponse(
            status_code=202,
            content={
                "available": False,
                "message": "Simulation requires a completed process analysis. Run the pipeline first.",
                "fallback": False,
            },
        )

    # Input validation
    if req.reduction_pct <= 0.0 or req.reduction_pct > 100.0:
        return JSONResponse(
            status_code=422,
            content={
                "available": False,
                "error": "Reduction percentage must be between 0% (exclusive) and 100% (inclusive).",
            },
        )

    if req.capacity_increase_pct is not None:
        if req.capacity_increase_pct <= 0.0 or req.capacity_increase_pct > 500.0:
            return JSONResponse(
                status_code=422,
                content={
                    "available": False,
                    "error": "Capacity increase percentage must be between 0% (exclusive) and 500% (inclusive).",
                },
            )

    try:
        results = simulate_scenario(
            event_log_path=event_log_path,
            scenario_type=req.scenario_type,
            target_activity=req.target_activity,
            target_resource=req.target_resource,
            reduction_pct=req.reduction_pct,
            capacity_increase_pct=req.capacity_increase_pct,
        )
        if not results.get("available"):
            results["fallback"] = False
            return JSONResponse(status_code=202, content=results)
        results["fallback"] = is_fallback
        if is_fallback:
            results["warning"] = storage_svc.FALLBACK_WARNING
        return JSONResponse(status_code=200, content=results)
    except ValueError as val_err:
        logger.warning(f"Validation error in simulation scenario: {val_err}")
        return JSONResponse(
            status_code=422,
            content={"available": False, "error": str(val_err)},
        )
    except Exception as exc:
        logger.exception(f"Unexpected error during simulation run: {exc}")
        return JSONResponse(
            status_code=500,
            content={"available": False, "error": f"Failed to run simulation: {str(exc)}"},
        )
