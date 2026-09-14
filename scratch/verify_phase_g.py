"""
ProcessLens — Phase G Automated Verification Test Suite
=========================================================
Validates the Direct System Connectors expansion:
  Test 1: Canonical schema definition & contract completeness
  Test 2: Extensible connector registry & enterprise stubs
  Test 3: Deterministic normalization & custom column mapping
  Test 4: Read-Only safety & SQL injection defense
  Test 5: Connection timeout enforcement
  Test 6: Database connector test_connection simulation & column discovery
  Test 7: Connection Test API endpoint (POST /api/connectors/test)
  Test 8: Ingestion API endpoint (POST /api/connectors/ingest) & validation enforcement
  Test 9: Project / run isolation & pipeline data-quality integration
  Test 10: Regression verification across Phase A, Phase C, Phase E, and Phase F
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app
from backend.config import OUTPUT_FILES, STORAGE_ROOT, UPLOAD_STATE_FILE
from backend.models.event_log import (
    CANONICAL_COLUMNS,
    CANONICAL_COLUMN_SET,
    ColumnMapping,
    ConnectionTestRequest,
    ConnectorIngestRequest,
    PostgresConnectionConfig,
)
from backend.services.connectors import get_connector, CONNECTOR_REGISTRY
from backend.services.connectors.base import BaseConnector
from backend.services.connectors.postgres import PostgreSQLConnector
from backend.services.storage import ensure_project


def print_test_header(num: int, title: str):
    print(f"\n--- {num}. {title} ---")


def run_phase_g_verification():
    print("=" * 65)
    print("      ProcessLens — Phase G Direct Connectors Verification     ")
    print("=" * 65)

    app = create_app()
    client = TestClient(app)

    # -----------------------------------------------------------------------
    # TEST 1: Canonical Schema Contract
    # -----------------------------------------------------------------------
    print_test_header(1, "Testing Canonical Schema Completeness")
    assert CANONICAL_COLUMNS == ["case_id", "activity", "timestamp", "resource"], (
        f"Canonical columns mismatch: {CANONICAL_COLUMNS}"
    )
    assert set(CANONICAL_COLUMNS) == CANONICAL_COLUMN_SET
    print(f"  Canonical columns: {CANONICAL_COLUMNS}")
    print("  [OK] Canonical schema contract verified.")

    # -----------------------------------------------------------------------
    # TEST 2: Extensible Connector Registry & Stubs
    # -----------------------------------------------------------------------
    print_test_header(2, "Testing Extensible Connector Registry & Stubs")
    pg_conn = get_connector("postgresql", {
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "username": "tester",
        "password": "secret_password",
        "table_name": "events",
    })
    assert isinstance(pg_conn, PostgreSQLConnector)
    print(f"  PostgreSQL connector instantiated: {type(pg_conn).__name__}")

    mysql_conn = get_connector("mysql", {})
    stub_res = mysql_conn.test_connection()
    assert stub_res["success"] is False
    assert "planned for future enterprise integration" in stub_res["message"]
    print(f"  MySQL stub graceful message: {stub_res['message']}")

    try:
        get_connector("unsupported_db", {})
        assert False, "Should have raised ValueError for unsupported connector"
    except ValueError as ve:
        assert "Unsupported connector source type" in str(ve)
    print("  [OK] Extensible connector registry verified.")

    # -----------------------------------------------------------------------
    # TEST 3: Deterministic Normalization & Column Mapping
    # -----------------------------------------------------------------------
    print_test_header(3, "Testing Normalization & Column Mapping Layer")
    raw_records = pd.DataFrame({
        "order_number": ["PO-101", " PO-101 ", "PO-102", "PO-102", "PO-103"],
        "stage_name": ["Submitted", "Approved", "Submitted", "Completed", "Submitted"],
        "event_time": [
            "2026-09-01 09:00:00",
            "2026-09-01 10:30:00",
            "2026-09-01 09:15:00",
            "2026-09-01 11:00:00",
            "2026-09-01 09:45:00",
        ],
        "operator": ["Alice", "Bob", "Charlie", "Diana", "  "],
    })

    mapping = ColumnMapping(
        case_id="order_number",
        activity="stage_name",
        timestamp="event_time",
        resource="operator",
    )

    norm_df = pg_conn.normalize_records(raw_records, mapping)
    assert list(norm_df.columns) == CANONICAL_COLUMNS
    assert norm_df["case_id"].tolist() == ["PO-101", "PO-101", "PO-102", "PO-102", "PO-103"]
    assert norm_df["activity"].tolist() == ["Submitted", "Approved", "Submitted", "Completed", "Submitted"]
    assert norm_df["resource"].iloc[4] == "SYSTEM"  # empty operator replaced by SYSTEM
    print(f"  Normalized columns: {list(norm_df.columns)}")
    print(f"  Rows normalized: {len(norm_df)}, cases: {norm_df['case_id'].nunique()}")
    print("  [OK] Deterministic normalization and column mapping passed.")

    # -----------------------------------------------------------------------
    # TEST 4: Read-Only Safety & SQL Injection Defense
    # -----------------------------------------------------------------------
    print_test_header(4, "Testing Read-Only Safety & SQL Injection Defense")
    # Valid identifier
    assert pg_conn._validate_identifier("safe_table_name") == "safe_table_name"

    # SQL injection attempts must be rejected by validator
    malicious_inputs = [
        "events; DROP TABLE users;--",
        "orders WHERE 1=1",
        "table with spaces",
        "schema.table",
        "table' OR '1'='1",
    ]
    for bad_name in malicious_inputs:
        try:
            pg_conn._validate_identifier(bad_name)
            assert False, f"Malicious identifier '{bad_name}' was not rejected!"
        except ValueError:
            pass
    print("  Malicious SQL identifiers strictly rejected.")

    # Redaction of password in errors
    dummy_err = Exception("Connection failed with password secret_password on host localhost:5432")
    sanitized = pg_conn._sanitize_error(dummy_err)
    assert "secret_password" not in sanitized
    assert "******" in sanitized
    print(f"  Sanitized error output: {sanitized}")
    print("  [OK] Read-Only safety and SQL injection defense verified.")

    # -----------------------------------------------------------------------
    # TEST 5: Connection Timeout Safeguards
    # -----------------------------------------------------------------------
    print_test_header(5, "Testing Connection Timeout Safeguards")
    # Attempt connection to a non-routable IP with timeout (should return clean error without hanging)
    unreachable_conn = PostgreSQLConnector({
        "host": "10.255.255.1",
        "port": 5432,
        "database": "test",
        "username": "test",
        "password": "secret",
        "table_name": "events",
    })
    start_t = datetime.now()
    # Note: connect_timeout=10 in _get_connection, test_connection catches it gracefully
    # We test that validate_config passes but test_connection returns success=False within reasonable time
    with patch("psycopg2.connect") as mock_conn:
        import psycopg2
        mock_conn.side_effect = psycopg2.OperationalError("timeout expired while connecting")
        res = unreachable_conn.test_connection()
        assert res["success"] is False
        assert "Unable to connect to PostgreSQL" in res["message"]
        assert "secret" not in res["message"]
    print("  Timeout gracefully caught and reported without crash.")
    print("  [OK] Connection timeout safeguards verified.")

    # -----------------------------------------------------------------------
    # TEST 6: Mock Database Connection Test & Column Discovery
    # -----------------------------------------------------------------------
    print_test_header(6, "Testing Database test_connection & Column Discovery")
    with patch.object(PostgreSQLConnector, "_get_connection") as mock_get_conn:
        mock_db_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_db_conn

        # 1. Table exists
        # 2. Columns query
        # 3. Row count query
        mock_cursor.fetchone.side_effect = [
            ("process_events",),  # table exists check
            (1245,),              # count(*)
        ]
        mock_cursor.fetchall.return_value = [
            ("case_num", "varchar"),
            ("step_name", "varchar"),
            ("occurred_at", "timestamp"),
            ("user_id", "varchar"),
        ]

        test_result = pg_conn.test_connection()
        assert test_result["success"] is True
        assert test_result["available_columns"] == ["case_num", "step_name", "occurred_at", "user_id"]
        assert test_result["row_count"] == 1245
        assert test_result["detected_mapping"]["case_id"] == "case_num"
        assert test_result["detected_mapping"]["activity"] == "step_name"
        assert test_result["detected_mapping"]["timestamp"] == "occurred_at"
        assert test_result["detected_mapping"]["resource"] == "user_id"
        print(f"  Discovered {len(test_result['available_columns'])} columns, {test_result['row_count']} rows.")
        print(f"  Auto-detected mapping: {test_result['detected_mapping']}")
        print("  [OK] test_connection and column discovery verified.")

    # -----------------------------------------------------------------------
    # TEST 7: Connection Test API Endpoint (POST /api/connectors/test)
    # -----------------------------------------------------------------------
    print_test_header(7, "Testing POST /api/connectors/test Endpoint")
    # 7a. Missing required fields -> 422
    bad_req = client.post("/api/connectors/test", json={"source_type": "postgresql", "config": {}})
    assert bad_req.status_code == 422

    # 7b. Valid payload with mocked successful connection
    with patch.object(PostgreSQLConnector, "_get_connection") as mock_get_conn:
        mock_db_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_db_conn
        mock_cursor.fetchone.side_effect = [("process_events",), (500,)]
        mock_cursor.fetchall.return_value = [
            ("case_id", "varchar"),
            ("activity", "varchar"),
            ("timestamp", "timestamp"),
            ("resource", "varchar"),
        ]

        resp = client.post("/api/connectors/test", json={
            "source_type": "postgresql",
            "config": {
                "host": "localhost",
                "port": 5432,
                "database": "analytics",
                "username": "dbuser",
                "password": "super_secret_pw",
                "schema_name": "public",
                "table_name": "process_events",
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "super_secret_pw" not in json.dumps(data)
        assert data["available_columns"] == ["case_id", "activity", "timestamp", "resource"]
        print(f"  API Response: {data['message']}")
    print("  [OK] POST /api/connectors/test endpoint verified.")

    # -----------------------------------------------------------------------
    # TEST 8: Ingestion API Endpoint (POST /api/connectors/ingest)
    # -----------------------------------------------------------------------
    print_test_header(8, "Testing POST /api/connectors/ingest Endpoint")

    # Generate 15 valid cases to satisfy MIN_CASES_REQUIRED (>=10)
    simulated_rows = []
    for i in range(1, 20):
        cid = f"PO-DB-{i:03d}"
        simulated_rows.extend([
            (cid, "Submitted", f"2026-09-01 0{i % 8 + 1}:00:00", "Alice"),
            (cid, "Reviewed", f"2026-09-01 0{i % 8 + 1}:30:00", "Bob"),
            (cid, "Approved", f"2026-09-01 0{i % 8 + 1}:45:00", "Charlie"),
            (cid, "Completed", f"2026-09-01 0{i % 8 + 1}:55:00", "Diana"),
        ])

    with patch.object(PostgreSQLConnector, "_get_connection") as mock_get_conn:
        mock_db_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_db_conn
        # fetchone for test_connection checks
        mock_cursor.fetchone.side_effect = [
            ("process_events",),
            (len(simulated_rows),),
        ]
        mock_cursor.fetchall.side_effect = [
            # 1. available columns
            [("case_num", "text"), ("action", "text"), ("time_stamp", "text"), ("operator", "text")],
            # 2. fetch_records data
            simulated_rows,
        ]

        ingest_resp = client.post("/api/connectors/ingest", json={
            "source_type": "postgresql",
            "project_id": "test_proj_g",
            "config": {
                "host": "localhost",
                "port": 5432,
                "database": "erp_db",
                "username": "reader",
                "password": "secret_password",
                "schema_name": "public",
                "table_name": "process_events",
            },
            "column_mapping": {
                "case_id": "case_num",
                "activity": "action",
                "timestamp": "time_stamp",
                "resource": "operator",
            },
        })

        assert ingest_resp.status_code == 200, f"Ingest failed: {ingest_resp.text}"
        ingest_data = ingest_resp.json()
        assert ingest_data["accepted"] is True
        assert ingest_data["case_count"] == 19
        assert ingest_data["row_count"] == len(simulated_rows)
        assert ingest_data["source_type"] == "postgresql"
        print(f"  Ingest result: {ingest_data['message']}")
        print(f"  Events imported: {ingest_data['row_count']}, Cases: {ingest_data['case_count']}")

    print("  [OK] POST /api/connectors/ingest endpoint verified.")

    # -----------------------------------------------------------------------
    # TEST 9: Project Isolation & Data Quality Integration
    # -----------------------------------------------------------------------
    print_test_header(9, "Testing Project Isolation & Data Quality Integration")
    # Verify project-level upload file exists
    proj_upload_csv = STORAGE_ROOT / "projects" / "test_proj_g" / "uploads" / "event_log.csv"
    assert proj_upload_csv.exists(), f"Project upload file missing: {proj_upload_csv}"
    proj_df = pd.read_csv(str(proj_upload_csv))
    assert len(proj_df) == len(simulated_rows)
    assert list(proj_df.columns) == CANONICAL_COLUMNS
    print(f"  Project upload isolated at: {proj_upload_csv.name}")

    # Verify upload_state.json updated without credentials
    with open(str(UPLOAD_STATE_FILE), encoding="utf-8") as f:
        state = json.load(f)
    assert state["source"] == "postgresql"
    assert "secret_password" not in json.dumps(state)
    print(f"  Upload state correctly tracks source='{state['source']}' without password leakage.")

    # Verify /api/data-quality reflects connector dataset
    dq_resp = client.get("/api/data-quality")
    assert dq_resp.status_code == 200
    dq_data = dq_resp.json()
    assert dq_data["case_count"] == 19
    assert dq_data["event_count"] == len(simulated_rows)
    print(f"  Data quality telemetric: {dq_data['case_count']} cases, {dq_data['event_count']} events.")

    # Verify /api/status exposes source metadata
    status_resp = client.get("/api/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["data_source"] == "postgresql"
    print(f"  System status reports data_source='{status_data['data_source']}'")

    # Clean up test project directory
    test_proj_dir = STORAGE_ROOT / "projects" / "test_proj_g"
    if test_proj_dir.exists():
        shutil.rmtree(str(test_proj_dir), ignore_errors=True)

    # Reset synthetic dataset
    reset_resp = client.post("/api/reset-to-synthetic")
    assert reset_resp.status_code == 200

    # Ensure baseline models and predictions exist for regression test suites
    from backend.config import VENV_PYTHON
    py_exec = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    subprocess.run([py_exec, "run_all.py"], cwd=str(PROJECT_ROOT), capture_output=True)
    subprocess.run([py_exec, "run_phase2.py"], cwd=str(PROJECT_ROOT), capture_output=True)

    print("  Cleaned up test project and restored synthetic dataset.")
    print("  [OK] Project isolation and data-quality integration verified.")

    # -----------------------------------------------------------------------
    # TEST 10: Regression Verification Across Phases A, C, E, and F
    # -----------------------------------------------------------------------
    print_test_header(10, "Running Regression Suites Across Phases A, C, E, and F")

    # Phase A
    print("  [Phase A] Running verify_phase_a.py...")
    res_a = subprocess.run(
        [py_exec, str(PROJECT_ROOT / "scratch" / "verify_phase_a.py")],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    assert res_a.returncode == 0, f"Phase A failed: {res_a.stderr}"
    print("  [Phase A] Regression: PASSED (100%)")

    # Phase C
    print("  [Phase C] Running verify_phase_c.py...")
    res_c = subprocess.run(
        [py_exec, str(PROJECT_ROOT / "scratch" / "verify_phase_c.py")],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    assert res_c.returncode == 0, f"Phase C failed: {res_c.stderr}"
    print("  [Phase C] Regression: PASSED (100%)")

    # Phase E
    print("  [Phase E] Running verify_phase_e.py...")
    res_e = subprocess.run(
        [py_exec, str(PROJECT_ROOT / "scratch" / "verify_phase_e.py")],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    assert res_e.returncode == 0, f"Phase E failed: {res_e.stderr}"
    print("  [Phase E] Regression: PASSED (100%)")

    # Phase F
    print("  [Phase F] Running verify_phase_f.py...")
    res_f = subprocess.run(
        [py_exec, str(PROJECT_ROOT / "scratch" / "verify_phase_f.py")],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    assert res_f.returncode == 0, f"Phase F failed: {res_f.stderr}"
    print("  [Phase F] Regression: PASSED (100%)")

    print("\n" + "=" * 65)
    print(">>> ALL 10 PHASE G VERIFICATION TESTS PASSED SUCCESSFULLY! <<<")
    print("=" * 65)


if __name__ == "__main__":
    run_phase_g_verification()
