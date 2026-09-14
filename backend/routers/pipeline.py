"""
ProcessLens — Pipeline Router
================================
Async pipeline execution with SSE streaming.
POST /api/run/* endpoints are now non-blocking by default.
Pass ?sync=true for legacy synchronous behavior.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from backend.models import RunStatusEnum, RunAllRequest
from backend.services import pipeline_runner as runner
from backend.security import require_api_key

router = APIRouter()


# ---------------------------------------------------------------------------
# Pipeline execution endpoints
# ---------------------------------------------------------------------------

@router.post("/api/run/all", dependencies=[Depends(require_api_key)])
async def run_all(
    request: Request,
    sync: bool = Query(False, description="If true, block until completion (legacy mode)"),
    snapshot_activity: str = Query("Reviewed", description="Activity to snapshot at"),
    project_id: str = Query("default", description="Project to run pipeline for"),
):
    """
    Run all three phases. By default, returns immediately with run_id (async).
    Use ?sync=true for legacy blocking behavior.
    """
    run, conflict_run_id = runner.create_run_guarded(project_id, snapshot_activity)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A run is already in progress for this project: {conflict_run_id}",
        )

    if sync:
        # Legacy synchronous mode
        await runner.run_all_phases(run)
        if run.status == RunStatusEnum.COMPLETED:
            return {
                "success": True,
                "run_id": run.run_id,
                "failed_at": None,
                "message": "All three phases completed successfully.",
                "phases": [],  # Legacy compat
            }
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "run_id": run.run_id,
                    "failed_at": run.error_message,
                    "message": f"Pipeline stopped: {run.error_message}",
                    "phases": [],
                },
            )

    # Async mode — fire and forget
    asyncio.create_task(runner.run_all_phases(run))
    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "message": "Pipeline started. Use /api/run/{run_id}/stream for live logs.",
    }


@router.post("/api/run/phase1", dependencies=[Depends(require_api_key)])
async def run_phase1(
    sync: bool = Query(False),
    project_id: str = Query("default"),
):
    """Run Phase 1 only."""
    run, conflict_run_id = runner.create_run_guarded(project_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A run is already in progress for this project: {conflict_run_id}",
        )

    if sync:
        await runner.run_single_phase(run, "phase1")
        return _sync_response(run, "phase1")
    asyncio.create_task(runner.run_single_phase(run, "phase1"))
    return {"run_id": run.run_id, "status": run.status.value, "phase": "phase1"}


@router.post("/api/run/phase2", dependencies=[Depends(require_api_key)])
async def run_phase2(
    sync: bool = Query(False),
    project_id: str = Query("default"),
):
    """Run Phase 2 only."""
    run, conflict_run_id = runner.create_run_guarded(project_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A run is already in progress for this project: {conflict_run_id}",
        )

    if sync:
        await runner.run_single_phase(run, "phase2")
        return _sync_response(run, "phase2")
    asyncio.create_task(runner.run_single_phase(run, "phase2"))
    return {"run_id": run.run_id, "status": run.status.value, "phase": "phase2"}


@router.post("/api/run/phase3", dependencies=[Depends(require_api_key)])
async def run_phase3(
    sync: bool = Query(False),
    project_id: str = Query("default"),
):
    """Run Phase 3 only."""
    run, conflict_run_id = runner.create_run_guarded(project_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A run is already in progress for this project: {conflict_run_id}",
        )

    if sync:
        await runner.run_single_phase(run, "phase3")
        return _sync_response(run, "phase3")
    asyncio.create_task(runner.run_single_phase(run, "phase3"))
    return {"run_id": run.run_id, "status": run.status.value, "phase": "phase3"}


# ---------------------------------------------------------------------------
# Status & Logs
# ---------------------------------------------------------------------------

@router.get("/api/run/{run_id}/status")
def get_run_status(run_id: str):
    """Check the current status of a background pipeline run."""
    run = runner.get_run(run_id)
    if not run:
        return JSONResponse(status_code=404, content={"error": f"Run '{run_id}' not found."})
    return run.to_dict()


@router.get("/api/run/{run_id}/logs")
def get_run_logs(run_id: str, offset: int = 0):
    """Return accumulated log lines (polling fallback)."""
    run = runner.get_run(run_id)
    if not run:
        return JSONResponse(status_code=404, content={"error": f"Run '{run_id}' not found."})
    all_logs = list(run.log_lines)
    return {
        "run_id": run_id,
        "status": run.status.value,
        "logs": all_logs[offset:],
        "total": len(all_logs),
    }


@router.get("/api/run/{run_id}/stream")
async def stream_run_logs(run_id: str):
    """
    SSE endpoint for real-time log streaming.
    Events: log, progress, status
    """
    run = runner.get_run(run_id)
    if not run:
        return JSONResponse(status_code=404, content={"error": f"Run '{run_id}' not found."})

    async def event_generator():
        q = run.subscribe()
        try:
            # First, send all existing logs as initial burst
            for entry in list(run.log_lines):
                yield f"event: log\ndata: {json.dumps(entry)}\n\n"

            # Send current status
            yield f"event: status\ndata: {json.dumps(run.to_dict())}\n\n"

            # Stream new events
            while True:
                try:
                    event_type, data = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

                    # If we got a terminal status, close the stream
                    if event_type == "status" and data.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f"event: keepalive\ndata: {json.dumps({'ts': 'ping'})}\n\n"

                    # Check if run is done
                    if run.status in (RunStatusEnum.COMPLETED, RunStatusEnum.FAILED, RunStatusEnum.CANCELLED):
                        yield f"event: status\ndata: {json.dumps(run.to_dict())}\n\n"
                        break
        finally:
            run.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sync_response(run, phase: str) -> dict:
    """Build a synchronous response compatible with legacy API."""
    logs = list(run.log_lines)
    stdout = "\n".join(e["line"] for e in logs if e["level"] == "info")
    stderr = "\n".join(e["line"] for e in logs if e["level"] == "error")
    return {
        "phase": phase,
        "run_id": run.pipeline_run_id or run.run_id,
        "success": run.status == RunStatusEnum.COMPLETED,
        "returncode": 0 if run.status == RunStatusEnum.COMPLETED else 1,
        "stdout": stdout,
        "stderr": stderr,
    }
