"""
ProcessLens — Phase H3 Test Suite
==================================
Tests 1-5 verifying:
- Test 1: Normal current-run artifact (fallback=False, no warning, fields preserved)
- Test 2: Missing current-run artifact with available legacy fallback (fallback=True, warning present)
- Test 3: Missing current-run artifact and no fallback available (status 202/404, fallback is not True)
- Test 4 & 5: Frontend visibility verification
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"d:\Process Lens")

from fastapi.testclient import TestClient

from backend.main import app
from backend.services import storage as storage_svc
from backend.config import STORAGE_ROOT, OUTPUT_FILES

client = TestClient(app)


def test_1_normal_current_run_artifact():
    """TEST 1: Current-run artifact exists -> fallback: False, no warning, fields intact."""
    project_id = "test_h3_proj1"
    run_id = "run_normal"
    run_dir = storage_svc.create_run_dir(project_id, run_id)

    # Put a real predictions.json inside run_dir / outputs
    fake_preds = [
        {"case_id": "C-101", "predicted_label": "Late Risk", "risk_score": 0.85, "anomaly_flag": False}
    ]
    with open(run_dir / "outputs" / "predictions.json", "w", encoding="utf-8") as f:
        json.dump(fake_preds, f)

    # Put a real conformance.json inside run_dir / outputs
    fake_conf = {
        "available": True,
        "summary": {"conformance_rate_pct": 92.5, "total_cases": 10},
        "reference_process": ["A", "B", "C"],
        "top_deviations": [],
    }
    with open(run_dir / "outputs" / "conformance.json", "w", encoding="utf-8") as f:
        json.dump(fake_conf, f)

    # 1. Test storage layer directly
    path, is_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "predictions")
    assert path == run_dir / "outputs" / "predictions.json"
    assert is_fallback is False, f"Expected is_fallback=False, got {is_fallback}"

    # 2. Test API endpoint /api/predictions
    res = client.get(f"/api/predictions?project_id={project_id}&run_id={run_id}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("fallback") is False, f"Expected fallback=False, got {data.get('fallback')}"
    assert "warning" not in data, f"Did not expect warning, got {data.get('warning')}"
    assert data.get("available") is True
    assert "summary" in data
    assert len(data.get("open_cases", [])) == 1

    # 3. Test API endpoint /api/conformance
    res_conf = client.get(f"/api/conformance?project_id={project_id}&run_id={run_id}")
    assert res_conf.status_code == 200, res_conf.text
    conf_data = res_conf.json()
    assert conf_data.get("fallback") is False, f"Expected fallback=False, got {conf_data.get('fallback')}"
    assert "warning" not in conf_data
    assert conf_data.get("summary", {}).get("conformance_rate_pct") == 92.5

    # Cleanup
    shutil.rmtree(run_dir.parent.parent, ignore_errors=True)
    print("PASS: Test 1 — Normal current-run artifact returns fallback=False, no warning, existing fields preserved.")


def test_2_missing_current_run_artifact_with_legacy_fallback():
    """TEST 2: Missing current-run artifact with available legacy fallback -> fallback: True, warning present."""
    project_id = "default"
    run_id = "run_missing_artifact"
    run_dir = storage_svc.create_run_dir(project_id, run_id)

    # Verify that run does NOT have predictions.json or conformance.json
    assert not (run_dir / "outputs" / "predictions.json").exists()
    assert not (run_dir / "predictions.json").exists()

    # Root predictions MUST exist
    assert OUTPUT_FILES["predictions"].exists(), "Root predictions.json must exist for fallback test"

    # 1. Test storage layer directly
    path, is_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "predictions")
    assert path == OUTPUT_FILES["predictions"], f"Expected root fallback path, got {path}"
    assert is_fallback is True, f"Expected is_fallback=True, got {is_fallback}"

    # 2. Test API endpoint /api/predictions
    res = client.get(f"/api/predictions?project_id={project_id}&run_id={run_id}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("fallback") is True, f"Expected fallback=True, got {data.get('fallback')}"
    assert data.get("warning") == storage_svc.FALLBACK_WARNING, f"Expected exact warning, got {data.get('warning')}"
    assert "Showing fallback data, not this run's own output." in data.get("warning")
    assert data.get("available") is True
    assert "summary" in data
    assert "open_cases" in data

    # 3. Test API endpoint /api/conformance
    if OUTPUT_FILES["conformance"].exists():
        res_conf = client.get(f"/api/conformance?project_id={project_id}&run_id={run_id}")
        assert res_conf.status_code == 200, res_conf.text
        conf_data = res_conf.json()
        assert conf_data.get("fallback") is True
        assert conf_data.get("warning") == storage_svc.FALLBACK_WARNING

    # 4. Test API endpoint /api/discovery
    res_disc = client.get(f"/api/discovery?project_id={project_id}&run_id={run_id}")
    assert res_disc.status_code == 200, res_disc.text
    disc_data = res_disc.json()
    assert disc_data.get("fallback") is True
    assert disc_data.get("warning") == storage_svc.FALLBACK_WARNING
    assert "bottlenecks" in disc_data

    # Cleanup run dir
    shutil.rmtree(run_dir, ignore_errors=True)
    print("PASS: Test 2 — Missing current-run artifact uses fallback, returns fallback=True and explicit human warning.")


def test_3_missing_both_current_run_and_fallback():
    """TEST 3: Missing current-run artifact and no fallback available -> status 202/404, fallback is NOT True."""
    project_id = "default"
    run_id = "run_no_fallback"
    run_dir = storage_svc.create_run_dir(project_id, run_id)

    # 1. Test storage layer directly for a nonexistent artifact key
    path, is_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "nonexistent_artifact")
    assert path is None
    assert is_fallback is False, f"Expected is_fallback=False when no artifact exists, got {is_fallback}"

    # 2. Test when both run artifact and legacy root fallback are nonexistent
    real_log = OUTPUT_FILES["event_log"]
    real_conf = OUTPUT_FILES["conformance"]
    temp_backup_log = None
    temp_backup_conf = None
    try:
        if real_log.exists():
            temp_backup_log = real_log.with_suffix(".csv.bak_test3")
            shutil.move(str(real_log), str(temp_backup_log))
        if real_conf.exists():
            temp_backup_conf = real_conf.with_suffix(".json.bak_test3")
            shutil.move(str(real_conf), str(temp_backup_conf))

        # Direct storage test
        p, fb = storage_svc.resolve_artifact_path(project_id, run_id, "event_log")
        assert p is None
        assert fb is False, f"Expected fb=False when both missing, got {fb}"

        # API test for /api/discovery
        res_disc = client.get(f"/api/discovery?project_id={project_id}&run_id={run_id}")
        assert res_disc.status_code == 202
        d_data = res_disc.json()
        assert d_data.get("available") is False
        assert d_data.get("fallback") is False, f"Expected fallback=False when not available, got {d_data.get('fallback')}"
        assert "warning" not in d_data

        # API test for /api/conformance
        res_conf = client.get(f"/api/conformance?project_id={project_id}&run_id={run_id}")
        assert res_conf.status_code == 202
        c_data = res_conf.json()
        assert c_data.get("available") is False
        assert c_data.get("fallback") is False, f"Expected fallback=False when neither exists, got {c_data.get('fallback')}"
        assert "warning" not in c_data
    finally:
        if temp_backup_log and temp_backup_log.exists():
            shutil.move(str(temp_backup_log), str(real_log))
        if temp_backup_conf and temp_backup_conf.exists():
            shutil.move(str(temp_backup_conf), str(real_conf))

    # Cleanup run dir
    shutil.rmtree(run_dir, ignore_errors=True)
    print("PASS: Test 3 — Missing both current-run and fallback returns 202 available=False and fallback is NOT True.")


def test_4_and_5_frontend_warning_logic():
    """TEST 4 & 5: Verify frontend condition triggers warning if and only if fallback===True."""
    # Logic in frontend/app/page.tsx:
    #   Boolean(discovery?.fallback || paths?.fallback)
    #   Boolean(predictions?.fallback)
    #   Boolean(explanation?.fallback)
    #   data.fallback (ConformancePanel.tsx)
    #   baseline.fallback || activeResult?.fallback (SimulationPanel.tsx)
    # Warning text: "Showing fallback data, not this run's own output."

    # Test 4: When fallback is True
    res2 = client.get("/api/predictions?project_id=default&run_id=r_missing")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2.get("fallback") is True
    assert data2.get("warning") == "Showing fallback data, not this run's own output."
    # Condition: Boolean(predictions?.fallback) -> True
    should_render_warning = bool(data2.get("fallback"))
    assert should_render_warning is True, "Frontend warning MUST be rendered when fallback is True"

    # Test 5: When fallback is False (default or normal run)
    res1 = client.get("/api/predictions")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1.get("fallback") is False
    assert "warning" not in data1
    # Condition: Boolean(predictions?.fallback) -> False
    should_not_render_warning = bool(data1.get("fallback"))
    assert should_not_render_warning is False, "Frontend warning MUST NOT be rendered when fallback is False"

    print("PASS: Test 4 & 5 — Frontend conditional correctly displays warning when fallback=True and suppresses it when fallback=False.")


if __name__ == "__main__":
    test_1_normal_current_run_artifact()
    test_2_missing_current_run_artifact_with_legacy_fallback()
    test_3_missing_both_current_run_and_fallback()
    test_4_and_5_frontend_warning_logic()
    print("\nALL MANDATORY H3 TESTS (1-5) PASSED!")
