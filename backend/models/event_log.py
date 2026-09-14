"""
ProcessLens — Canonical Event Log Schema & Connector Models
===========================================================
Defines the standard canonical event-log schema and request/response models
for direct system connectors (PostgreSQL, CSV, and future enterprise connectors).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Canonical Event Log Schema
# ---------------------------------------------------------------------------

CANONICAL_COLUMNS: list[str] = ["case_id", "activity", "timestamp", "resource"]
CANONICAL_COLUMN_SET: set[str] = set(CANONICAL_COLUMNS)

SCHEMA_DESCRIPTIONS = {
    "case_id": "Unique identifier of the process instance (e.g. 'PO-1001', 'INV-204').",
    "activity": "Name of the executed activity step (e.g. 'Submitted', 'Approved').",
    "timestamp": "ISO-8601 formatted datetime string indicating when the step occurred.",
    "resource": "Person, role, system, or department that performed the activity.",
}


class ConnectorTypeEnum(str, Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLSERVER = "sqlserver"
    JIRA = "jira"
    SALESFORCE = "salesforce"
    SAP = "sap"
    CSV = "csv"


class ColumnMapping(BaseModel):
    """
    Maps source database column names to canonical ProcessLens fields.
    Each value represents the column name in the source table.
    """
    case_id: str = Field(..., description="Source column mapped to canonical case_id")
    activity: str = Field(..., description="Source column mapped to canonical activity")
    timestamp: str = Field(..., description="Source column mapped to canonical timestamp")
    resource: str = Field(..., description="Source column mapped to canonical resource")


class PostgresConnectionConfig(BaseModel):
    """Configuration parameters for connecting to a read-only PostgreSQL database."""
    host: str = Field(..., description="PostgreSQL server hostname or IP address")
    port: int = Field(5432, description="PostgreSQL server port (default 5432)")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Database user role")
    password: str = Field(..., description="Database password (never logged or persisted in metadata)")
    schema_name: str = Field("public", description="Database schema name (default 'public')")
    table_name: str = Field(..., description="Table or view name containing process event records")
    sslmode: str = Field("prefer", description="SSL mode (disable, allow, prefer, require, verify-ca, verify-full)")
    query_limit: Optional[int] = Field(50000, description="Maximum number of rows to retrieve (safeguard against memory overflow)")


class ConnectionTestRequest(BaseModel):
    source_type: str = Field("postgresql", description="Source connector type")
    config: PostgresConnectionConfig
    column_mapping: Optional[ColumnMapping] = None


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    source_type: str = "postgresql"
    available_columns: list[str] = []
    row_count: Optional[int] = None
    detected_mapping: Optional[dict[str, str]] = None


class ConnectorIngestRequest(BaseModel):
    source_type: str = Field("postgresql", description="Source connector type")
    project_id: str = Field("default", description="Workspace project ID")
    config: PostgresConnectionConfig
    column_mapping: ColumnMapping
    run_id: Optional[str] = None


class ConnectorIngestResponse(BaseModel):
    accepted: bool
    source_type: str
    project_id: str
    table_name: str
    row_count: int
    case_count: int
    activity_count: int
    date_range: Optional[dict] = None
    import_time: str
    backup_created: bool = False
    deleted_stale: list[str] = []
    message: str
