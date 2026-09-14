"""
ProcessLens — Connectors Package
=================================
Exposes connector factory and standard connector classes.
"""

from __future__ import annotations

from typing import Optional

from backend.services.connectors.base import BaseConnector
from backend.services.connectors.postgres import PostgreSQLConnector
from backend.services.connectors.stubs import (
    MySQLConnector,
    SQLServerConnector,
    JiraConnector,
    SalesforceConnector,
    SAPConnector,
)

CONNECTOR_REGISTRY = {
    "postgresql": PostgreSQLConnector,
    "postgres": PostgreSQLConnector,
    "mysql": MySQLConnector,
    "sqlserver": SQLServerConnector,
    "jira": JiraConnector,
    "salesforce": SalesforceConnector,
    "sap": SAPConnector,
}


def get_connector(source_type: str, config: dict) -> BaseConnector:
    """Factory function returning the appropriate BaseConnector instance."""
    normalized_type = source_type.strip().lower()
    connector_cls = CONNECTOR_REGISTRY.get(normalized_type)
    if not connector_cls:
        raise ValueError(
            f"Unsupported connector source type '{source_type}'. "
            f"Supported connectors: {sorted(list(set(CONNECTOR_REGISTRY.keys())))}"
        )
    return connector_cls(config)


__all__ = [
    "BaseConnector",
    "PostgreSQLConnector",
    "MySQLConnector",
    "SQLServerConnector",
    "JiraConnector",
    "SalesforceConnector",
    "SAPConnector",
    "get_connector",
    "CONNECTOR_REGISTRY",
]
