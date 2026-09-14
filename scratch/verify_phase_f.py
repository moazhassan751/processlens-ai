"""
ProcessLens — Phase F Verification Suite
=========================================
Comprehensive verification for Phase F: What-If Simulation.

Mandatory Verification Tests:
1. TEST 1 — Synthetic PO Baseline
2. TEST 2 — Controlled Calculation (exact arithmetic: 20h -> 14h at 30% reduction)
3. TEST 3 — Bottleneck Scenario (interventions on actual primary bottleneck)
4. TEST 4 — BPI2012 Sample Test (dataset-specific baseline & dynamic levers)
5. TEST 5 — Invalid Scenarios (negative, >100%, nonexistent activity)
6. TEST 6 — No Pipeline State (HTTP 202 handling)
7. TEST 7 — Storage & Run Isolation
8. TEST 8 — LLM Independence (zero dependency on language models)
9. TEST 9 — Multi-Scenario Stacking (differential comparisons)
10. TEST 10 — Regressions (Phases A, C, and E)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import pandas as pd
from starlette.testclient import TestClient

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import app
from backend.services.simulation_service import compute_simulation_baseline, simulate_scenario
from backend.services.storage import create_run_dir, get_run_dir
from backend.config import PROJECT_ROOT as CFG_ROOT, VENV_PYTHON


def test_synthetic_po_baseline():
    print("\n--- 1. Testing Synthetic PO Baseline ---")
    event_log_p = PROJECT_ROOT / "event_log.csv"
    assert event_log_p.exists(), "event_log.csv must exist"

    baseline = compute_simulation_baseline(event_log_p)
    assert baseline["available"] is True
    assert baseline["case_count"] == 300, f"Expected 300 cases, got {baseline['case_count']}"
    assert baseline["avg_cycle_time_hours"] > 0
    assert baseline["median_cycle_time_hours"] > 0
    assert baseline["primary_bottleneck"] is not None
    assert baseline["primary_bottleneck"]["activity"] == "Approved"
    assert baseline["primary_bottleneck"]["avg_wait_hours"] > 25.0
    assert len(baseline["activities"]) == 5
    print(f"  [OK] Baseline verified: {baseline['case_count']} cases, {baseline['avg_cycle_time_hours']}h avg cycle time, Primary Bottleneck: {baseline['primary_bottleneck']['activity']} ({baseline['primary_bottleneck']['avg_wait_hours']}h)")


def test_controlled_calculation():
    print("\n--- 2. Testing Controlled Planted Calculation ---")
    # Case with exact 20-hour wait interval leading into activity B
    # Case start at 09:00, B at 29:00 (20h wait), C at 39:00 (10h wait)
    # Total cycle time = 30 hours.
    rows = [
        {"case_id": "CTRL-01", "activity": "A", "timestamp": "2025-01-01 09:00:00", "resource": "R1"},
        {"case_id": "CTRL-01", "activity": "B", "timestamp": "2025-01-02 05:00:00", "resource": "R1"}, # +20h
        {"case_id": "CTRL-01", "activity": "C", "timestamp": "2025-01-02 15:00:00", "resource": "R1"}, # +10h
    ]

    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, newline="", encoding="utf-8") as tmp:
        df = pd.DataFrame(rows)
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)

    try:
        # Run 30% reduction on activity B
        result = simulate_scenario(
            event_log_path=tmp_path,
            scenario_type="bottleneck_wait_reduction",
            target_activity="B",
            reduction_pct=30.0,
        )
        assert result["available"] is True
        # Component check: 20h baseline -> 14h simulated (6h savings)
        assert result["baseline"]["component_value"] == 20.0, f"Expected 20.0h, got {result['baseline']['component_value']}"
        assert result["simulated"]["component_value"] == 14.0, f"Expected 14.0h, got {result['simulated']['component_value']}"
        assert result["impact"]["component_reduction_hours"] == 6.0, f"Expected 6.0h saved, got {result['impact']['component_reduction_hours']}"
        assert result["impact"]["component_reduction_pct"] == 30.0

        # Cycle time check: 30h baseline -> 24h simulated (6h savings = 20% improvement)
        assert result["baseline"]["avg_cycle_time_hours"] == 30.0, f"Expected 30.0h baseline cycle, got {result['baseline']['avg_cycle_time_hours']}"
        assert result["simulated"]["avg_cycle_time_hours"] == 24.0, f"Expected 24.0h simulated cycle, got {result['simulated']['avg_cycle_time_hours']}"
        assert result["impact"]["absolute_reduction_hours"] == 6.0
        assert abs(result["impact"]["cycle_time_improvement_pct"] - 20.0) < 0.1
        print(f"  [OK] Exact arithmetic passed: 20.0h -> 14.0h (-6.0h), cycle time 30.0h -> 24.0h (-20.0%)")
    finally:
        if tmp_path.exists():
            os.remove(tmp_path)


def test_bottleneck_scenario():
    print("\n--- 3. Testing Bottleneck Scenario on Synthetic PO ---")
    event_log_p = PROJECT_ROOT / "event_log.csv"
    result = simulate_scenario(
        event_log_path=event_log_p,
        scenario_type="bottleneck_wait_reduction",
        target_activity="Approved",
        reduction_pct=30.0,
    )
    assert result["available"] is True
    assert result["scenario"]["target_activity"] == "Approved"
    assert result["baseline"]["avg_cycle_time_hours"] > result["simulated"]["avg_cycle_time_hours"]
    assert result["impact"]["absolute_reduction_hours"] > 0
    assert result["impact"]["cycle_time_improvement_pct"] > 15.0
    assert result["simulated"]["affected_cases_count"] == 300
    print(f"  [OK] Approved -30% simulation: {result['baseline']['avg_cycle_time_hours']}h -> {result['simulated']['avg_cycle_time_hours']}h (saved {result['impact']['absolute_reduction_hours']}h / {result['impact']['cycle_time_improvement_pct']}%)")


def test_bpi2012_sample():
    print("\n--- 4. Testing BPI2012 Sample Simulation ---")
    bpi_csv = PROJECT_ROOT / "data" / "bpi2012_sample.csv"
    if not bpi_csv.exists():
        bpi_csv = PROJECT_ROOT / "storage" / "bpi2012_sample.csv"
    assert bpi_csv.exists(), f"BPI2012 CSV not found at {bpi_csv}"

    bpi_baseline = compute_simulation_baseline(bpi_csv)
    assert bpi_baseline["available"] is True
    assert bpi_baseline["case_count"] == 100
    assert len(bpi_baseline["activities"]) == 24
    
    # Pick first activity from BPI2012
    act_target = bpi_baseline["activities"][0]["activity"]
    bpi_sim = simulate_scenario(
        event_log_path=bpi_csv,
        scenario_type="bottleneck_wait_reduction",
        target_activity=act_target,
        reduction_pct=25.0,
    )
    assert bpi_sim["available"] is True
    assert bpi_sim["baseline"]["case_count"] == 100
    assert bpi_sim["scenario"]["target_activity"] == act_target
    print(f"  [OK] BPI2012 simulation: 100 cases, activity '{act_target}', baseline {bpi_sim['baseline']['avg_cycle_time_hours']}h -> {bpi_sim['simulated']['avg_cycle_time_hours']}h")


def test_invalid_scenarios():
    print("\n--- 5. Testing Invalid Scenario Bounds & Safety Checks ---")
    client = TestClient(app)

    # 1. Negative reduction
    res_neg = client.post("/api/simulation/run", json={
        "scenario_type": "bottleneck_wait_reduction",
        "target_activity": "Approved",
        "reduction_pct": -15.0,
    })
    assert res_neg.status_code == 422, f"Expected 422 for negative reduction, got {res_neg.status_code}"
    assert "Reduction percentage must be between" in res_neg.json()["error"]
    print("  [OK] Negative reduction rejected with clean 422")

    # 2. Reduction > 100%
    res_high = client.post("/api/simulation/run", json={
        "scenario_type": "bottleneck_wait_reduction",
        "target_activity": "Approved",
        "reduction_pct": 150.0,
    })
    assert res_high.status_code == 422, f"Expected 422 for >100% reduction, got {res_high.status_code}"
    assert "Reduction percentage must be between" in res_high.json()["error"]
    print("  [OK] >100% reduction rejected with clean 422")

    # 3. Nonexistent activity
    res_nonexistent = client.post("/api/simulation/run", json={
        "scenario_type": "bottleneck_wait_reduction",
        "target_activity": "Activity_Does_Not_Exist_XYZ",
        "reduction_pct": 30.0,
    })
    assert res_nonexistent.status_code == 422, f"Expected 422 for nonexistent activity, got {res_nonexistent.status_code}"
    assert "does not exist in the active event log" in res_nonexistent.json()["error"]
    print("  [OK] Nonexistent activity rejected with clean 422")


def test_no_pipeline_state():
    print("\n--- 6. Testing No Pipeline State Handling ---")
    client = TestClient(app)

    res_base = client.get("/api/simulation/baseline?project_id=nonexistent_project_xyz")
    assert res_base.status_code == 202, f"Expected 202, got {res_base.status_code}"
    assert res_base.json()["available"] is False

    res_run = client.post("/api/simulation/run", json={
        "project_id": "nonexistent_project_xyz",
        "scenario_type": "bottleneck_wait_reduction",
        "target_activity": "Approved",
        "reduction_pct": 30.0,
    })
    assert res_run.status_code == 202, f"Expected 202, got {res_run.status_code}"
    assert res_run.json()["available"] is False
    print("  [OK] Missing project / unanalyzed state cleanly returns HTTP 202 without crashes")


def test_run_isolation():
    print("\n--- 7. Testing Storage & Run Isolation ---")
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_a = "proj_iso_a"
        proj_b = "proj_iso_b"

        # Create isolated run for proj_a with 2 cases
        run_a = create_run_dir(proj_a, "run_01")
        df_a = pd.DataFrame([
            {"case_id": "A1", "activity": "Start", "timestamp": "2025-01-01 10:00:00", "resource": "R1"},
            {"case_id": "A1", "activity": "End", "timestamp": "2025-01-01 12:00:00", "resource": "R1"},
            {"case_id": "A2", "activity": "Start", "timestamp": "2025-01-01 10:00:00", "resource": "R1"},
            {"case_id": "A2", "activity": "End", "timestamp": "2025-01-01 14:00:00", "resource": "R1"},
        ])
        df_a.to_csv(run_a / "event_log.csv", index=False)

        client = TestClient(app)
        res_a = client.get(f"/api/simulation/baseline?project_id={proj_a}&run_id=run_01")
        assert res_a.status_code == 200
        assert res_a.json()["case_count"] == 2

        # proj_b has no run, must return 202
        res_b = client.get(f"/api/simulation/baseline?project_id={proj_b}&run_id=run_01")
        assert res_b.status_code == 202
        print("  [OK] Run isolation verified: Project A and Project B cannot cross-read simulation state")


def test_llm_independence():
    print("\n--- 8. Testing LLM Independence ---")
    event_log_p = PROJECT_ROOT / "event_log.csv"

    # Save original env var and unset
    old_groq = os.environ.get("GROQ_API_KEY")
    old_gemini = os.environ.get("GEMINI_API_KEY")
    old_enabled = os.environ.get("LLM_ENABLED")

    try:
        os.environ["LLM_ENABLED"] = "false"
        os.environ.pop("GROQ_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)

        res = simulate_scenario(
            event_log_path=event_log_p,
            scenario_type="rework_reduction",
            target_activity="all",
            reduction_pct=50.0,
        )
        assert res["available"] is True
        assert res["impact"]["absolute_reduction_hours"] >= 0
        assert "Under the selected assumption" in res["explanation"]
        print("  [OK] LLM-independent simulation succeeded: 100% deterministic calculation and text generation")
    finally:
        if old_groq:
            os.environ["GROQ_API_KEY"] = old_groq
        if old_gemini:
            os.environ["GEMINI_API_KEY"] = old_gemini
        if old_enabled:
            os.environ["LLM_ENABLED"] = old_enabled


def test_multi_scenario_stacking():
    print("\n--- 9. Testing Multi-Scenario Stacking ---")
    event_log_p = PROJECT_ROOT / "event_log.csv"

    # Scenario A: Bottleneck wait reduction -30%
    sim_a = simulate_scenario(event_log_p, scenario_type="bottleneck_wait_reduction", target_activity="Approved", reduction_pct=30.0)
    # Scenario B: Rework reduction -50%
    sim_b = simulate_scenario(event_log_p, scenario_type="rework_reduction", target_activity="all", reduction_pct=50.0)
    # Scenario C: Step duration -25%
    sim_c = simulate_scenario(event_log_p, scenario_type="activity_duration_reduction", target_activity="Approved", reduction_pct=25.0)

    assert sim_a["impact"]["cycle_time_improvement_pct"] > 0
    assert sim_b["impact"]["cycle_time_improvement_pct"] > 0
    assert sim_c["impact"]["cycle_time_improvement_pct"] > 0

    # Ensure scenarios produce distinct values reflecting their specific levers
    assert sim_a["simulated"]["avg_cycle_time_hours"] != sim_b["simulated"]["avg_cycle_time_hours"]
    print(f"  [OK] Multi-scenario comparison matrix: A(-30% Bn)={sim_a['impact']['cycle_time_improvement_pct']}%, B(-50% Rework)={sim_b['impact']['cycle_time_improvement_pct']}%, C(-25% Dur)={sim_c['impact']['cycle_time_improvement_pct']}%")


def test_regressions():
    print("\n--- 10. Running Regression Suites (Phases A, C, E) ---")
    # Phase A
    res_a = subprocess.run([VENV_PYTHON, str(PROJECT_ROOT / "scratch" / "verify_phase_a.py")], capture_output=True, text=True)
    assert res_a.returncode == 0, f"Phase A verification failed: {res_a.stderr}"
    print("  [OK] Phase A Regression: PASSED (100%)")

    # Phase C
    res_c = subprocess.run([VENV_PYTHON, str(PROJECT_ROOT / "scratch" / "verify_phase_c.py")], capture_output=True, text=True)
    assert res_c.returncode == 0, f"Phase C verification failed: {res_c.stderr}"
    print("  [OK] Phase C Regression: PASSED (100%)")

    # Phase E
    res_e = subprocess.run([VENV_PYTHON, str(PROJECT_ROOT / "scratch" / "verify_phase_e.py")], capture_output=True, text=True)
    assert res_e.returncode == 0, f"Phase E verification failed: {res_e.stderr}"
    print("  [OK] Phase E Regression: PASSED (100%)")


if __name__ == "__main__":
    print("=============================================================")
    print("   ProcessLens — Phase F What-If Simulation Verification     ")
    print("=============================================================")
    test_synthetic_po_baseline()
    test_controlled_calculation()
    test_bottleneck_scenario()
    test_bpi2012_sample()
    test_invalid_scenarios()
    test_no_pipeline_state()
    test_run_isolation()
    test_llm_independence()
    test_multi_scenario_stacking()
    test_regressions()
    print("\n>>> ALL PHASE F VERIFICATION TESTS PASSED SUCCESSFULLY! <<<\n")
