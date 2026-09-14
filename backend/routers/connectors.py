"""
ProcessLens — Connectors Router
================================
REST API endpoints for direct system connectors:
  - POST /api/connectors/test: Test database/source connectivity & discover columns
  - POST /api/connectors/ingest: Read-only extraction, deterministic normalization,
                                 canonical validation, and isolated workspace persistence
  - GET  /api/connectors/types: Available and upcoming connector integrations
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from backend.security import require_api_key

from backend.models.event_log import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    ConnectorIngestRequest,
    ConnectorIngestResponse,
)
from backend.services.connectors import get_connector

logger = logging.getLogger("processlens.connectors.router")
router = APIRouter(prefix="/api/connectors", tags=["Connectors"])


@router.get("/types")
def list_connector_types():
    """Returns available direct system connectors and upcoming integrations."""
    return {
        "connectors": [
            {
                "id": "postgresql",
                "name": "PostgreSQL Database",
                "status": "active",
                "description": "Direct read-only extraction from PostgreSQL tables or views.",
                "category": "database",
            },
            {
                "id": "csv",
                "name": "CSV File Upload",
                "status": "active",
                "description": "Standard drag-and-drop event log file ingestion.",
                "category": "file",
            },
            {
                "id": "mysql",
                "name": "MySQL Database",
                "status": "coming_soon",
                "description": "Read-only ingestion from MySQL / MariaDB instances.",
                "category": "database",
            },
            {
                "id": "sqlserver",
                "name": "Microsoft SQL Server",
                "status": "coming_soon",
                "description": "Direct query extraction from MS SQL Server database tables.",
                "category": "database",
            },
            {
                "id": "jira",
                "name": "Atlassian Jira",
                "status": "coming_soon",
                "description": "Extract issue lifecycle history and workflow transition logs.",
                "category": "service_desk",
            },
            {
                "id": "salesforce",
                "name": "Salesforce Service Cloud",
                "status": "coming_soon",
                "description": "Ingest case history, lead conversion, and order progression events.",
                "category": "crm",
            },
            {
                "id": "sap",
                "name": "SAP ERP",
                "status": "coming_soon",
                "description": "Ingest Purchase-to-Pay (P2P) and Order-to-Cash (O2C) document tables.",
                "category": "erp",
            },
        ]
    }


@router.post("/test", response_model=ConnectionTestResponse)
def test_connector_connection(req: ConnectionTestRequest):
    """
    Test connectivity, inspect available columns, and verify table existence.
    Credentials are strictly redacted and never returned or exposed in logs.
    """
    try:
        connector = get_connector(req.source_type, req.config.model_dump())
        result = connector.test_connection(req.column_mapping)
        return ConnectionTestResponse(
            success=result.get("success", False),
            message=result.get("message", "Connection test completed."),
            source_type=req.source_type,
            available_columns=result.get("available_columns", []),
            row_count=result.get("row_count"),
            detected_mapping=result.get("detected_mapping"),
        )
    except ValueError as ve:
        logger.warning(f"Connector test validation failure: {ve}")
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": str(ve),
                "source_type": req.source_type,
                "available_columns": [],
                "row_count": None,
            },
        )
    except Exception as exc:
        logger.error(f"Unexpected connector test error: {exc}")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"Connection test failed: {str(exc)}",
                "source_type": req.source_type,
                "available_columns": [],
                "row_count": None,
            },
        )


@router.post("/ingest", dependencies=[Depends(require_api_key)])
def ingest_from_connector(req: ConnectorIngestRequest):
    """
    Ingests event records from a direct system connector:
      1. Connects & executes read-only parameterized query
      2. Deterministically normalizes fields and parses timestamps
      3. Validates canonical DataFrame with Phase A validation rules (>=10 cases, ISO-8601)
      4. Rejects invalid data with clean HTTP 422
      5. Persists canonical event log in project workspace and active root environment
    """
    source_type = req.source_type.strip().lower()
    project_id = req.project_id.strip() or "default"

    try:
        connector = get_connector(source_type, req.config.model_dump())

        # 1. Connection check
        test_res = connector.test_connection(req.column_mapping)
        if not test_res.get("success"):
            return JSONResponse(
                status_code=422,
                content={
                    "accepted": False,
                    "message": f"Source connection failed: {test_res.get('message')}",
                    "errors": [test_res.get("message")],
                },
            )

        # 2. Read-only fetch
        raw_df = connector.fetch_records(req.column_mapping)
        if raw_df is None or raw_df.empty:
            return JSONResponse(
                status_code=422,
                content={
                    "accepted": False,
                    "message": "Source query returned zero records. Cannot ingest empty dataset.",
                    "errors": ["Dataset contains no records."],
                },
            )

        # 3. Deterministic normalization & column mapping
        try:
            norm_df = connector.normalize_records(raw_df, req.column_mapping)
        except ValueError as map_err:
            return JSONResponse(
                status_code=422,
                content={
                    "accepted": False,
                    "message": f"Normalization failed: {str(map_err)}",
                    "errors": [str(map_err)],
                },
            )

        # 4. Strict validation using existing Phase A validation layer
        is_valid, validation_errors = connector.validate_canonical_df(norm_df)
        if not is_valid:
            logger.warning(
                f"Connector ingestion rejected for project '{project_id}' ({source_type}): {validation_errors}"
            )
            return JSONResponse(
                status_code=422,
                content={
                    "accepted": False,
                    "source_type": source_type,
                    "message": "Import rejected: dataset failed canonical validation standards.",
                    "errors": validation_errors,
                },
            )

        # 5. Persist normalized log in isolated project workspace
        table_name = getattr(req.config, "table_name", "connector_data")
        persisted = connector.persist_normalized_log(
            df=norm_df,
            project_id=project_id,
            source_type=source_type,
            table_or_source_name=f"{source_type}:{table_name}",
        )

        logger.info(
            f"Successfully ingested {persisted['row_count']} events across {persisted['case_count']} cases "
            f"from {source_type} into project '{project_id}'"
        )

        return ConnectorIngestResponse(**persisted)

    except ValueError as ve:
        logger.warning(f"Connector ingestion validation error: {ve}")
        return JSONResponse(
            status_code=422,
            content={
                "accepted": False,
                "message": str(ve),
                "errors": [str(ve)],
            },
        )
    except RuntimeError as re:
        logger.error(f"Connector runtime error: {re}")
        return JSONResponse(
            status_code=502,
            content={
                "accepted": False,
                "message": f"External data source error: {str(re)}",
                "errors": [str(re)],
            },
        )
    except Exception as exc:
        logger.error(f"Unhandled error during connector ingestion: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "accepted": False,
                "message": "Internal error occurred while processing connector ingestion.",
                "errors": [str(exc)],
            },
        )
