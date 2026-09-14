"""
ProcessLens — Snapshot Router
================================
Dynamic snapshot selection for feature engineering (Phase 7 Feature 3).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.services.snapshot_service import get_available_activities, validate_snapshot_activity
from backend.models import SnapshotRequest

router = APIRouter()


@router.get("/api/activities")
@router.get("/api/snapshot/activities")
def get_activities():
    """Return available activities from the current event_log.csv."""
    activities = get_available_activities()
    if not activities:
        return JSONResponse(
            status_code=202,
            content={
                "available": False,
                "message": "No event log found. Run the pipeline or upload data first.",
            },
        )
    return {"available": True, "activities": activities}


@router.post("/api/snapshot/validate")
def validate_snapshot(body: SnapshotRequest):
    """Validate that an activity is suitable as a snapshot milestone."""
    result = validate_snapshot_activity(body.activity)
    if not result.get("valid"):
        return JSONResponse(status_code=422, content=result)
    return result
