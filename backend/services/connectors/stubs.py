"""
ProcessLens — Future Enterprise Connector Stubs
================================================
Provides extensible connector implementations for planned direct system integrations
(MySQL, SQL Server, Jira, Salesforce, SAP).
Follows the same BaseConnector lifecycle to demonstrate extensibility without fake buttons.
"""

from __future__ import annotations

from typing import Optional, Tuple
import pandas as pd

from backend.models.event_log import ColumnMapping
from backend.services.connectors.base import BaseConnector


class UnsupportedConnector(BaseConnector):
    """Base stub for connectors awaiting future driver configuration."""

    connector_name: str = "Enterprise Connector"

    def validate_config(self) -> Tuple[bool, Optional[str]]:
        return False, f"{self.connector_name} driver is not configured in current environment."

    def test_connection(self, column_mapping: Optional[ColumnMapping] = None) -> dict:
        return {
            "success": False,
            "message": (
                f"{self.connector_name} connector is planned for future enterprise integration. "
                "Contact administrator to configure system adapter."
            ),
            "source_type": self.connector_name.lower().replace(" ", "_"),
            "available_columns": [],
            "row_count": None,
        }

    def fetch_records(self, mapping: ColumnMapping, limit: Optional[int] = None) -> pd.DataFrame:
        raise NotImplementedError(f"{self.connector_name} ingestion is not yet supported.")


class MySQLConnector(UnsupportedConnector):
    connector_name = "MySQL Database"


class SQLServerConnector(UnsupportedConnector):
    connector_name = "Microsoft SQL Server"


class JiraConnector(UnsupportedConnector):
    connector_name = "Atlassian Jira"


class SalesforceConnector(UnsupportedConnector):
    connector_name = "Salesforce Service Cloud"


class SAPConnector(UnsupportedConnector):
    connector_name = "SAP ERP"
