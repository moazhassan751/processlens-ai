"""
ProcessLens — Read-Only PostgreSQL Connector
============================================
Production-grade read-only connector for PostgreSQL databases.
Enforces:
  - Strictly read-only transactions (conn.set_session(readonly=True))
  - Connection timeout (10s) and SQL statement timeout (30s)
  - SQL identifier whitelisting and psycopg2.sql.Identifier escaping
  - Complete redaction of credentials in error reporting and logs
  - Parameterized queries to prevent SQL injection
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2 import sql

from backend.models.event_log import ColumnMapping, PostgresConnectionConfig
from backend.services.connectors.base import BaseConnector

logger = logging.getLogger("processlens.connectors.postgres")

IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PostgreSQLConnector(BaseConnector):
    """
    Read-only connector for extracting process event records from PostgreSQL.
    """

    def __init__(self, config: dict | PostgresConnectionConfig):
        if isinstance(config, PostgresConnectionConfig):
            self.cfg = config
        else:
            self.cfg = PostgresConnectionConfig(**config)
        super().__init__(self.cfg.model_dump())

    def _sanitize_error(self, exc: Exception) -> str:
        """Strip passwords and internal credentials from exception strings."""
        msg = str(exc)
        if self.cfg.password and self.cfg.password in msg:
            msg = msg.replace(self.cfg.password, "******")
        # Strip common postgres DSN password patterns
        msg = re.sub(r":([^:@]+)@", ":******@", msg)
        return msg.strip()

    def _validate_identifier(self, name: str, field_desc: str = "identifier") -> str:
        """Validate that SQL identifiers conform to safe alphanumeric/underscore names."""
        clean = name.strip()
        if not IDENTIFIER_REGEX.match(clean):
            raise ValueError(
                f"Invalid {field_desc} '{clean}'. "
                "Identifiers must begin with a letter or underscore and contain only alphanumeric characters and underscores."
            )
        return clean

    def validate_config(self) -> Tuple[bool, Optional[str]]:
        """Validate connection parameters and identifier names."""
        try:
            if not self.cfg.host:
                return False, "Database host is required."
            if not (1 <= self.cfg.port <= 65535):
                return False, f"Invalid port {self.cfg.port}. Must be between 1 and 65535."
            if not self.cfg.database:
                return False, "Database name is required."
            if not self.cfg.username:
                return False, "Username is required."
            if not self.cfg.table_name:
                return False, "Table name is required."

            self._validate_identifier(self.cfg.schema_name, "schema name")
            self._validate_identifier(self.cfg.table_name, "table name")
            return True, None
        except ValueError as ve:
            return False, str(ve)
        except Exception as exc:
            return False, f"Invalid configuration: {self._sanitize_error(exc)}"

    def _get_connection(self):
        """
        Creates a read-only PostgreSQL connection with strict timeout safeguards:
          - connect_timeout: 10s (prevents indefinite TCP hang on unreachable host)
          - statement_timeout: 30000ms (prevents runaway long-running queries)
        """
        return psycopg2.connect(
            host=self.cfg.host,
            port=self.cfg.port,
            dbname=self.cfg.database,
            user=self.cfg.username,
            password=self.cfg.password,
            sslmode=self.cfg.sslmode,
            connect_timeout=10,
            options="-c statement_timeout=30000",
        )

    def test_connection(self, column_mapping: Optional[ColumnMapping] = None) -> dict:
        """
        Tests connectivity, verifies table existence in information_schema,
        and retrieves accessible column names and total row count.
        """
        valid, err = self.validate_config()
        if not valid:
            return {
                "success": False,
                "message": f"Configuration error: {err}",
                "source_type": "postgresql",
                "available_columns": [],
                "row_count": None,
            }

        conn = None
        try:
            conn = self._get_connection()
            conn.set_session(readonly=True, autocommit=True)

            schema_clean = self._validate_identifier(self.cfg.schema_name, "schema name")
            table_clean = self._validate_identifier(self.cfg.table_name, "table name")

            with conn.cursor() as cur:
                # 1. Verify table exists in schema
                check_table_sql = """
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s AND table_name = %s;
                """
                cur.execute(check_table_sql, (schema_clean, table_clean))
                if not cur.fetchone():
                    return {
                        "success": False,
                        "message": (
                            f"Connection successful, but table '{schema_clean}.{table_clean}' "
                            "was not found in database."
                        ),
                        "source_type": "postgresql",
                        "available_columns": [],
                        "row_count": None,
                    }

                # 2. Query available columns
                cols_sql = """
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position;
                """
                cur.execute(cols_sql, (schema_clean, table_clean))
                cols_data = cur.fetchall()
                available_cols = [c[0] for c in cols_data]

                if not available_cols:
                    return {
                        "success": False,
                        "message": f"Table '{schema_clean}.{table_clean}' has no accessible columns.",
                        "source_type": "postgresql",
                        "available_columns": [],
                        "row_count": 0,
                    }

                # 3. Retrieve row count safely using identifier escaping
                count_query = sql.SQL("SELECT count(*) FROM {schema}.{table};").format(
                    schema=sql.Identifier(schema_clean),
                    table=sql.Identifier(table_clean),
                )
                cur.execute(count_query)
                row_count_row = cur.fetchone()
                row_count = int(row_count_row[0]) if row_count_row else 0

                # 4. Check column mapping if provided
                if column_mapping:
                    mapped_fields = {
                        "case_id": column_mapping.case_id.strip(),
                        "activity": column_mapping.activity.strip(),
                        "timestamp": column_mapping.timestamp.strip(),
                        "resource": column_mapping.resource.strip(),
                    }
                    missing = [
                        f"{canon} -> '{col}'"
                        for canon, col in mapped_fields.items()
                        if col not in available_cols
                    ]
                    if missing:
                        return {
                            "success": False,
                            "message": (
                                f"Connection successful, but mapped column(s) not found in table: {', '.join(missing)}. "
                                f"Available columns: {', '.join(available_cols)}"
                            ),
                            "source_type": "postgresql",
                            "available_columns": available_cols,
                            "row_count": row_count,
                        }

                # 5. Smart auto-detect mapping for UI helper
                detected: dict[str, str] = {}
                lower_cols = {c.lower(): c for c in available_cols}
                for candidate in ["case_id", "caseid", "case_num", "casenum", "order_id", "order_num", "claim_id", "ticket_id", "id"]:
                    if candidate in lower_cols:
                        detected["case_id"] = lower_cols[candidate]
                        break
                for candidate in ["activity", "step", "step_name", "event", "status", "action", "task"]:
                    if candidate in lower_cols:
                        detected["activity"] = lower_cols[candidate]
                        break
                for candidate in ["timestamp", "time", "created_at", "occurred_at", "event_time", "date"]:
                    if candidate in lower_cols:
                        detected["timestamp"] = lower_cols[candidate]
                        break
                for candidate in ["resource", "user", "user_id", "agent", "actor", "operator", "assigned_to"]:
                    if candidate in lower_cols:
                        detected["resource"] = lower_cols[candidate]
                        break

                return {
                    "success": True,
                    "message": (
                        f"Connection successful. Table '{schema_clean}.{table_clean}' accessible "
                        f"({row_count:,} rows, {len(available_cols)} columns)."
                    ),
                    "source_type": "postgresql",
                    "available_columns": available_cols,
                    "row_count": row_count,
                    "detected_mapping": detected,
                }

        except psycopg2.OperationalError as op_err:
            sanitized = self._sanitize_error(op_err)
            logger.warning(f"PostgreSQL connection operational error: {sanitized}")
            return {
                "success": False,
                "message": f"Unable to connect to PostgreSQL: {sanitized}",
                "source_type": "postgresql",
                "available_columns": [],
                "row_count": None,
            }
        except Exception as exc:
            sanitized = self._sanitize_error(exc)
            logger.error(f"PostgreSQL test connection error: {sanitized}")
            return {
                "success": False,
                "message": f"PostgreSQL test failed: {sanitized}",
                "source_type": "postgresql",
                "available_columns": [],
                "row_count": None,
            }
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def fetch_records(self, mapping: ColumnMapping, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Executes a read-only parameterized SELECT query to retrieve the mapped columns.
        Uses psycopg2.sql.Identifier to prevent SQL injection.
        """
        schema_clean = self._validate_identifier(self.cfg.schema_name, "schema name")
        table_clean = self._validate_identifier(self.cfg.table_name, "table name")

        col_case = self._validate_identifier(mapping.case_id, "case_id column")
        col_act = self._validate_identifier(mapping.activity, "activity column")
        col_ts = self._validate_identifier(mapping.timestamp, "timestamp column")
        col_res = self._validate_identifier(mapping.resource, "resource column")

        max_rows = limit or self.cfg.query_limit or 50000

        query = sql.SQL(
            "SELECT {case_col}, {act_col}, {ts_col}, {res_col} FROM {schema}.{table} LIMIT %s;"
        ).format(
            case_col=sql.Identifier(col_case),
            act_col=sql.Identifier(col_act),
            ts_col=sql.Identifier(col_ts),
            res_col=sql.Identifier(col_res),
            schema=sql.Identifier(schema_clean),
            table=sql.Identifier(table_clean),
        )

        conn = None
        try:
            conn = self._get_connection()
            conn.set_session(readonly=True, autocommit=True)

            with conn.cursor() as cur:
                cur.execute(query, (max_rows,))
                rows = cur.fetchall()
                col_names = [col_case, col_act, col_ts, col_res]
                df = pd.DataFrame(rows, columns=col_names)
                return df

        except psycopg2.Error as db_err:
            sanitized = self._sanitize_error(db_err)
            logger.error(f"Database query error during fetch_records: {sanitized}")
            raise RuntimeError(f"Database query failed: {sanitized}") from None
        except Exception as exc:
            sanitized = self._sanitize_error(exc)
            logger.error(f"Error fetching records from PostgreSQL: {sanitized}")
            raise RuntimeError(f"Failed to fetch records: {sanitized}") from None
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
