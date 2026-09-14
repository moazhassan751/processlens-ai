"""
ProcessLens — Projects Router
================================
Multi-project workspace isolation (Phase 7 Feature 4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.security import require_api_key
from backend.services import storage as storage_svc

router = APIRouter()


@router.get("/api/projects")
def list_projects():
    """List all projects with run counts."""
    projects = storage_svc.list_projects()
    return {"projects": projects}


@router.post("/api/projects", dependencies=[Depends(require_api_key)])
def create_project(project_id: str = "default"):
    """Create a new project workspace."""
    storage_svc.ensure_project(project_id)
    return {"project_id": project_id, "message": f"Project '{project_id}' created."}


@router.get("/api/projects/{project_id}/runs")
def list_project_runs(project_id: str):
    """List all runs for a specific project."""
    runs = storage_svc.list_runs(project_id)
    return {"project_id": project_id, "runs": runs}
