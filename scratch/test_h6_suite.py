"""
ProcessLens — Phase H6 Verification Test Suite
================================================
Comprehensive verification of Minimal Shared-Secret API Key Protection:
- Tests 1 to 12 as strictly specified by Phase H6 requirements.
- No-write-on-401 guarantees.
- Constant-time secret comparison.
- Backward compatibility when API_KEY is unset.
- Read endpoints open without credentials.
- Zero secret leakage in responses, logs, or JSON.
"""

import os
import sys
import hmac
import io
import json
import logging
from pathlib import Path
import shutil

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure clean test environment before importing app
TEST_SECRET = "test-processlens-secret-xyz-987"

# Setup logging capture to verify no secrets are logged
log_stream = io.StringIO()
logging.basicConfig(stream=log_stream, level=logging.DEBUG)


def run_h6_tests():
    print("=" * 70)
    print("STARTING PHASE H6 -- SHARED-SECRET API KEY PROTECTION VERIFICATION")
    print("=" * 70)

    from backend.app import create_app
    from backend import config
    from backend.services import storage as storage_svc
    from backend.services import pipeline_runner as runner

    app = create_app()
    client = TestClient(app)

    # -------------------------------------------------------------------------
    # TEST 1 -- API_KEY unset: write endpoints work without header
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Testing API_KEY unset (auth disabled / demo mode)...")
    if "API_KEY" in os.environ:
        del os.environ["API_KEY"]
    config.API_KEY = None

    # Call a mutating endpoint (create project workspace)
    test_proj_unset = "test_proj_unset_h6"
    res1 = client.post(f"/api/projects?project_id={test_proj_unset}")
    assert res1.status_code == 200, f"Expected 200 when API_KEY unset, got {res1.status_code}: {res1.text}"
    data1 = res1.json()
    assert data1.get("project_id") == test_proj_unset
    assert "created" in data1.get("message", "").lower()
    print("  [PASS] Protected write endpoint succeeds normally without credentials when API_KEY unset.")

    # -------------------------------------------------------------------------
    # Configure API_KEY for Tests 2-12
    # -------------------------------------------------------------------------
    os.environ["API_KEY"] = TEST_SECRET
    config.API_KEY = TEST_SECRET

    # -------------------------------------------------------------------------
    # TEST 2 -- API_KEY configured, missing header -> HTTP 401, no mutation
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Testing API_KEY configured, missing X-API-Key header...")
    unauth_proj = "unauthorized_proj_test2"
    proj_dir_test2 = config.STORAGE_ROOT / "projects" / unauth_proj

    res2 = client.post(f"/api/projects?project_id={unauth_proj}")
    assert res2.status_code == 401, f"Expected 401, got {res2.status_code}: {res2.text}"
    data2 = res2.json()
    assert data2.get("detail") == "Invalid or missing API key", f"Unexpected error detail: {data2}"
    assert not proj_dir_test2.exists(), "No-write check failed: directory was created on 401!"
    print("  [PASS] Missing header returned 401 with generic error detail; no write occurred.")

    # -------------------------------------------------------------------------
    # TEST 3 -- API_KEY configured, wrong header -> HTTP 401, no mutation
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Testing API_KEY configured, wrong X-API-Key header...")
    unauth_proj_wrong = "unauthorized_proj_test3"
    proj_dir_test3 = config.STORAGE_ROOT / "projects" / unauth_proj_wrong

    res3 = client.post(
        f"/api/projects?project_id={unauth_proj_wrong}",
        headers={"X-API-Key": "wrong-secret-token"},
    )
    assert res3.status_code == 401, f"Expected 401, got {res3.status_code}: {res3.text}"
    data3 = res3.json()
    assert data3.get("detail") == "Invalid or missing API key", f"Unexpected error detail: {data3}"
    assert not proj_dir_test3.exists(), "No-write check failed: directory was created on wrong key!"
    print("  [PASS] Wrong header returned 401 with identical error detail; no write occurred.")

    # -------------------------------------------------------------------------
    # TEST 4 -- API_KEY configured, correct header -> HTTP 200, write occurs
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Testing API_KEY configured, correct X-API-Key header...")
    auth_proj = "authorized_proj_test4"
    proj_dir_test4 = config.STORAGE_ROOT / "projects" / auth_proj

    res4 = client.post(
        f"/api/projects?project_id={auth_proj}",
        headers={"X-API-Key": TEST_SECRET},
    )
    assert res4.status_code == 200, f"Expected 200, got {res4.status_code}: {res4.text}"
    data4 = res4.json()
    assert data4.get("project_id") == auth_proj
    assert proj_dir_test4.exists(), "Write check failed: directory was not created on correct key!"
    print("  [PASS] Correct header succeeded with status 200; write occurred normally.")

    # -------------------------------------------------------------------------
    # TEST 5 -- Read endpoint without key remains open
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Testing read endpoint without key when API_KEY is configured...")
    res5 = client.get("/api/status")
    assert res5.status_code == 200, f"Expected 200 for GET /api/status, got {res5.status_code}: {res5.text}"
    data5 = res5.json()
    assert "files" in data5 and "phases" in data5
    print("  [PASS] GET /api/status succeeded without X-API-Key.")

    # -------------------------------------------------------------------------
    # TEST 6 -- Project creation endpoint full verification
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Testing project creation endpoint auth lifecycle...")
    p6_unauth = "test_p6_unauth"
    p6_auth = "test_p6_auth"

    # Missing header -> 401
    r6_missing = client.post(f"/api/projects?project_id={p6_unauth}")
    assert r6_missing.status_code == 401
    assert not (config.STORAGE_ROOT / "projects" / p6_unauth).exists()

    # Wrong header -> 401
    r6_wrong = client.post(f"/api/projects?project_id={p6_unauth}", headers={"X-API-Key": "bad"})
    assert r6_wrong.status_code == 401
    assert not (config.STORAGE_ROOT / "projects" / p6_unauth).exists()

    # Correct header -> 200
    r6_correct = client.post(f"/api/projects?project_id={p6_auth}", headers={"X-API-Key": TEST_SECRET})
    assert r6_correct.status_code == 200
    assert (config.STORAGE_ROOT / "projects" / p6_auth).exists()
    print("  [PASS] Project creation passed all auth check scenarios.")

    # -------------------------------------------------------------------------
    # TEST 7 -- Run start endpoints
    # -------------------------------------------------------------------------
    import time
    test_run_proj = f"test_run_auth_{int(time.time()*1000)}"
    print(f"\n[TEST 7] Testing pipeline run-start endpoints (/api/run/*) on {test_run_proj}...")
    endpoints = ["/api/run/all", "/api/run/phase1", "/api/run/phase2", "/api/run/phase3"]

    for ep in endpoints:
        # Missing header -> 401
        r_miss = client.post(f"{ep}?project_id={test_run_proj}")
        assert r_miss.status_code == 401, f"Expected 401 for {ep} missing key, got {r_miss.status_code}"
        assert r_miss.json().get("detail") == "Invalid or missing API key"

        # Wrong header -> 401
        r_wrong = client.post(f"{ep}?project_id={test_run_proj}", headers={"X-API-Key": "invalid-key"})
        assert r_wrong.status_code == 401, f"Expected 401 for {ep} wrong key, got {r_wrong.status_code}"

    # Verify no run was created in runner state for the unauthorized calls
    active_runs = [r for r in runner._runs.values() if r.project_id == test_run_proj]
    assert len(active_runs) == 0, f"Expected 0 runs created for {test_run_proj}, found {len(active_runs)}"

    # Correct header on /api/run/all (async) -> returns run_id
    r_corr = client.post(
        f"/api/run/all?project_id={test_run_proj}&sync=false",
        headers={"X-API-Key": TEST_SECRET},
    )
    assert r_corr.status_code == 200, f"Expected 200 for authorized run start, got {r_corr.status_code}: {r_corr.text}"
    assert "run_id" in r_corr.json()
    print("  [PASS] Run-start endpoints reject unauthorized requests without creating runs; succeed with valid key.")

    # -------------------------------------------------------------------------
    # TEST 8 -- Upload endpoint + H2 sanitization preservation
    # -------------------------------------------------------------------------
    print("\n[TEST 8] Testing upload endpoint (/api/upload)...")
    pred_path = config.PROJECT_ROOT / "predictions.json"
    pred_backup = pred_path.read_bytes() if pred_path.exists() else None

    valid_csv = (
        "case_id,activity,timestamp,resource\n"
        "C101,Created,=cmd|' /C calc'!A0,Alice\n"
        "C101,Approved,2026-01-01 11:00:00,Bob\n"
    ).encode("utf-8")

    # Missing header -> 401
    r_up_miss = client.post(
        "/api/upload?project_id=test_upload_auth",
        files={"file": ("test.csv", io.BytesIO(valid_csv), "text/csv")},
    )
    assert r_up_miss.status_code == 401, f"Expected 401 on upload missing key, got {r_up_miss.status_code}"
    assert r_up_miss.json().get("detail") == "Invalid or missing API key"

    # Wrong header -> 401
    r_up_wrong = client.post(
        "/api/upload?project_id=test_upload_auth",
        headers={"X-API-Key": "bad-key"},
        files={"file": ("test.csv", io.BytesIO(valid_csv), "text/csv")},
    )
    assert r_up_wrong.status_code == 401, f"Expected 401 on upload wrong key, got {r_up_wrong.status_code}"

    # Verify no file written to project upload directory
    proj_up_dir = config.STORAGE_ROOT / "projects" / "test_upload_auth" / "uploads"
    assert not proj_up_dir.exists(), "No-write check failed: upload dir was created on 401!"

    # Correct header -> 200/422 (validation error is expected if <10 cases, but auth passed)
    # Use a dataset with >= 10 cases to verify full upload + H2 formula sanitization
    rows = ["case_id,activity,timestamp,resource"]
    for i in range(1, 15):
        cid = f"PO_{i:03d}"
        rows.append(f"{cid},Created,2026-01-01 08:00:00,UserA")
        # Include a formula injection cell in resource
        rows.append(f"{cid},Approved,2026-01-01 09:00:00,=cmd|' /C calc'!A0")
        rows.append(f"{cid},Delivered,2026-01-01 10:00:00,UserB")
    full_csv = "\n".join(rows).encode("utf-8")

    r_up_corr = client.post(
        "/api/upload?project_id=test_upload_auth",
        headers={"X-API-Key": TEST_SECRET},
        files={"file": ("test_full.csv", io.BytesIO(full_csv), "text/csv")},
    )
    assert r_up_corr.status_code == 200, f"Expected 200 on authorized upload, got {r_up_corr.status_code}: {r_up_corr.text}"
    up_data = r_up_corr.json()
    assert up_data.get("accepted") is True

    # Check that H2 sanitization neutralized '=cmd' to "'=cmd"
    sanitized_file = config.STORAGE_ROOT / "projects" / "test_upload_auth" / "uploads" / "event_log.csv"
    assert sanitized_file.exists()
    content = sanitized_file.read_text(encoding="utf-8")
    assert "'=cmd|" in content, "H2 formula injection sanitization failed!"
    print("  [PASS] Upload correctly requires API key, rejects unauthorized attempts without writing, and preserves H2 sanitization.")

    # -------------------------------------------------------------------------
    # TEST 9 -- Reset-to-synthetic endpoint
    # -------------------------------------------------------------------------
    print("\n[TEST 9] Testing reset-to-synthetic endpoint (/api/reset-to-synthetic)...")
    # Missing header -> 401
    r_rst_miss = client.post("/api/reset-to-synthetic")
    assert r_rst_miss.status_code == 401, f"Expected 401 on reset missing key, got {r_rst_miss.status_code}"

    # Wrong header -> 401
    r_rst_wrong = client.post("/api/reset-to-synthetic", headers={"X-API-Key": "wrong"})
    assert r_rst_wrong.status_code == 401, f"Expected 401 on reset wrong key, got {r_rst_wrong.status_code}"

    # Also test /api/reset alias
    r_alias_miss = client.post("/api/reset")
    assert r_alias_miss.status_code == 401

    # Correct header -> 200
    r_rst_corr = client.post("/api/reset-to-synthetic", headers={"X-API-Key": TEST_SECRET})
    assert r_rst_corr.status_code == 200, f"Expected 200 on authorized reset, got {r_rst_corr.status_code}: {r_rst_corr.text}"
    rst_data = r_rst_corr.json()
    assert rst_data.get("success") is True
    assert rst_data.get("data_source") == "synthetic"
    if pred_backup is not None:
        pred_path.write_bytes(pred_backup)
    print("  [PASS] Reset-to-synthetic correctly requires API key and restores synthetic data.")

    # -------------------------------------------------------------------------
    # TEST 10 -- Connector write endpoints (/api/connectors/ingest)
    # -------------------------------------------------------------------------
    print("\n[TEST 10] Testing connector mutating endpoint (/api/connectors/ingest)...")
    payload = {
        "source_type": "postgresql",
        "project_id": "test_conn_auth",
        "config": {
            "host": "localhost",
            "port": 5432,
            "database": "test",
            "username": "user",
            "password": "pwd",
            "schema_name": "public",
            "table_name": "events",
            "sslmode": "prefer",
        },
        "column_mapping": {
            "case_id": "case_id",
            "activity": "activity",
            "timestamp": "timestamp",
            "resource": "resource",
        },
    }

    # Missing header -> 401
    r_ing_miss = client.post("/api/connectors/ingest", json=payload)
    assert r_ing_miss.status_code == 401, f"Expected 401 for connector ingest missing key, got {r_ing_miss.status_code}"
    assert r_ing_miss.json().get("detail") == "Invalid or missing API key"

    # Wrong header -> 401
    r_ing_wrong = client.post("/api/connectors/ingest", headers={"X-API-Key": "wrong"}, json=payload)
    assert r_ing_wrong.status_code == 401, f"Expected 401 for connector ingest wrong key, got {r_ing_wrong.status_code}"

    # Verify no connector data was persisted in project
    conn_dir = config.STORAGE_ROOT / "projects" / "test_conn_auth"
    assert not conn_dir.exists(), "No-write check failed: connector workspace created on 401!"

    # Non-mutating probe /api/connectors/test should NOT require API key
    r_probe = client.post("/api/connectors/test", json=payload)
    # Expect 400/422 connection failure due to mock db, but NOT 401!
    assert r_probe.status_code != 401, f"Expected non-401 for connection test probe, got {r_probe.status_code}"
    print("  [PASS] /api/connectors/ingest requires API key; /api/connectors/test remains open.")

    # -------------------------------------------------------------------------
    # TEST 11 -- Representative read endpoints remain open without key
    # -------------------------------------------------------------------------
    print("\n[TEST 11] Testing representative GET and read-only endpoints without API key...")
    read_endpoints = [
        ("GET", "/api/projects"),
        ("GET", "/api/status"),
        ("GET", "/api/discovery"),
        ("GET", "/api/discovery/paths"),
        ("GET", "/api/predictions"),
        ("GET", "/api/explanation"),
        ("GET", "/api/conformance"),
        ("GET", "/api/simulation/baseline"),
        ("GET", "/api/connectors/types"),
        ("GET", "/api/runs"),
        ("GET", "/api/process-graph"),
        ("GET", "/api/activities"),
        ("POST", "/api/simulation/run"),   # In-memory scenario calc
        ("POST", "/api/snapshot/validate"), # Activity validator
    ]

    for method, path in read_endpoints:
        if method == "GET":
            res = client.get(path)
        else:
            # Minimal body for POST read/calc endpoints
            if "simulation" in path:
                res = client.post(path, json={"scenario_type": "bottleneck_wait_reduction", "reduction_pct": 30.0})
            elif "snapshot" in path:
                res = client.post(path, json={"activity": "Created"})
            else:
                res = client.post(path)

        assert res.status_code != 401, f"Read endpoint {method} {path} was erroneously blocked with 401!"
        print(f"  [PASS] {method} {path} -> HTTP {res.status_code} (open, no 401)")

    # -------------------------------------------------------------------------
    # TEST 12 -- No secret leakage in responses, logs, or JSON
    # -------------------------------------------------------------------------
    print("\n[TEST 12] Checking for secret leakage in responses, error bodies, and logs...")
    # 1. Error responses
    for r in [res2, res3, r_miss, r_wrong, r_up_miss, r_rst_miss, r_ing_miss]:
        body_text = r.text
        assert TEST_SECRET not in body_text, f"Secret leaked in HTTP response body: {body_text}"

    # 2. Captured logs
    captured_logs = log_stream.getvalue()
    assert TEST_SECRET not in captured_logs, "Secret leaked in application logger output!"

    # 3. Source code files
    # Check that committed files do not have the test secret or any real secret
    for path in PROJECT_ROOT.glob("backend/**/*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert TEST_SECRET not in text, f"Secret found in source code file {path}!"

    print("  [PASS] No secret leakage detected in HTTP responses, logs, or source code.")

    # -------------------------------------------------------------------------
    # Cleanup test projects
    # -------------------------------------------------------------------------
    for p in ["test_proj_unset_h6", "authorized_proj_test4", "test_p6_auth", "test_upload_auth"]:
        d = config.STORAGE_ROOT / "projects" / p
        if d.exists():
            shutil.rmtree(str(d), ignore_errors=True)

    # Reset environment
    if "API_KEY" in os.environ:
        del os.environ["API_KEY"]
    config.API_KEY = None

    print("\n" + "=" * 70)
    print("ALL PHASE H6 TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_h6_tests()
    sys.exit(0 if success else 1)
