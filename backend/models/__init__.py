"""
ProcessLens — Pydantic Models & Schemas
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RunStatusEnum(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AsyncRunResponse(BaseModel):
    run_id: str
    status: RunStatusEnum
    message: str = ""


class RunStatusResponse(BaseModel):
    run_id: str
    status: RunStatusEnum
    progress: int = 0
    current_stage: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class RunLogEntry(BaseModel):
    timestamp: str
    line: str
    level: str = "info"  # info, warning, error


class ProcessGraphNode(BaseModel):
    id: str
    label: str
    frequency: int = 0
    avg_duration_hours: float = 0.0
    median_duration_hours: float = 0.0
    is_bottleneck: bool = False


class ProcessGraphEdge(BaseModel):
    source: str
    target: str
    frequency: int = 0
    avg_duration_hours: float = 0.0
    median_duration_hours: float = 0.0
    is_bottleneck: bool = False


class ProcessGraph(BaseModel):
    nodes: list[ProcessGraphNode] = []
    edges: list[ProcessGraphEdge] = []


class SnapshotRequest(BaseModel):
    activity: str


class SnapshotValidation(BaseModel):
    valid: bool
    activity: str
    case_coverage_pct: float = 0.0
    total_cases: int = 0
    cases_with_activity: int = 0
    warnings: list[str] = []
    error: Optional[str] = None


class CaseExplanation(BaseModel):
    summary: str
    evidence: list[str] = []
    recommendation: str = ""


class CaseExplanationResponse(BaseModel):
    case_id: str
    risk_level: str
    risk_score: Optional[float] = None
    anomaly: bool = False
    explanation: CaseExplanation
    source: str = "fallback"  # "llm" or "fallback"
    cached: bool = False


class ProjectInfo(BaseModel):
    project_id: str
    created_at: Optional[str] = None
    run_count: int = 0


class RunAllRequest(BaseModel):
    snapshot_activity: str = "Reviewed"
    project_id: str = "default"
    sync: bool = False


# Re-export canonical event log and connector schemas
from backend.models.event_log import (
    CANONICAL_COLUMNS,
    CANONICAL_COLUMN_SET,
    SCHEMA_DESCRIPTIONS,
    ConnectorTypeEnum,
    ColumnMapping,
    PostgresConnectionConfig,
    ConnectionTestRequest,
    ConnectionTestResponse,
    ConnectorIngestRequest,
    ConnectorIngestResponse,
)
