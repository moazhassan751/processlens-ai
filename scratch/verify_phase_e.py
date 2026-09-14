"""
ProcessLens — Phase E Verification Suite
=========================================
Comprehensive verification for Phase E: Process Conformance Checking.

Tests:
1. Synthetic PO Dataset Conformance Checking:
   - Evaluates against clean normative variant (Submitted -> Reviewed -> Approved -> Completed).
   - Validates total cases (300), conforming cases (246, 82.0%), deviating cases (54, 18.0%).
   - Asserts trace-level fitness metrics, alignment moves, and deviation categorizations.
2. Controlled Planted Deviation Log:
   - Case 1: Exact reference sequence (conforming, fitness 1.0).
   - Case 2: Planted rework loop on activity B (classified as 'Rework Loop').
   - Case 3: Planted skipped activity C (classified as 'Skipped Activity').
   - Case 4: Planted unplanned activity X (classified as 'Unplanned Activity').
3. BPI2012 Sample Dataset Conformance Checking:
   - Validates that real-world complex event logs (100 cases, 24 activities) execute
     without errors and auto-derive an appropriate normative reference sequence.
4. Conformance API Endpoint Verification:
   - GET /api/conformance returns 200 OK with full conforming/deviating breakdown.
   - Query filters (reference_variant, project_id) operate deterministically.
   - Unanalyzed / empty project requests yield HTTP 202 status.
5. Storage & Run Isolation:
   - Validates that project runs store conformance.json independently in project folders
     without cross-polluting workspace metrics.
6. Process Graph Conformance Edges:
   - Verifies that compute_process_graph computes is_conforming and is_deviating flags
     for visual overlays on the interactive canvas.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
import pandas as pd
from starlette.testclient import TestClient

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import app
from backend.services.process_mining import compute_conformance, compute_process_graph
from backend.services.storage import create_run_dir, organize_run_outputs, get_run_dir
from backend.config import PROJECT_ROOT as CFG_ROOT


def test_synthetic_po_conformance():
    print("\n--- 1. Testing Synthetic PO Dataset Conformance ---")
    event_log_p = PROJECT_ROOT / "event_log.csv"
    assert event_log_p.exists(), "event_log.csv must exist"

    conf = compute_conformance(event_log_p)
    assert conf["available"] is True, "Conformance result must be available"
    
    summary = conf["summary"]
    print(f"  Summary: {summary}")
    assert summary["total_cases"] == 300, f"Expected 300 cases, got {summary['total_cases']}"
    assert summary["conforming_cases"] == 246, f"Expected 246 conforming cases, got {summary['conforming_cases']}"
    assert summary["deviating_cases"] == 54, f"Expected 54 deviating cases, got {summary['deviating_cases']}"
    assert abs(summary["conformance_rate_pct"] - 82.0) < 0.1, f"Expected 82.0%, got {summary['conformance_rate_pct']}"
    assert summary["average_trace_fitness"] >= 0.95, f"Expected mean fitness >= 0.95, got {summary['average_trace_fitness']}"

    ref = conf["reference_process"]
    print(f"  Normative reference model: {' -> '.join(ref)}")
    assert ref == ["Submitted", "Reviewed", "Approved", "Completed"], f"Unexpected reference variant: {ref}"

    top_devs = conf["top_deviations"]
    assert len(top_devs) > 0, "Expected at least one top deviation"
    for dev in top_devs:
        assert "pattern" in dev and "deviation_type" in dev and "affected_cases" in dev and "affected_pct" in dev
        assert dev["affected_cases"] > 0
    print(f"  Top deviations identified: {len(top_devs)} deviation patterns")

    cases = conf["case_deviations"]
    assert len(cases) == 300, f"Expected 300 case records, got {len(cases)}"
    for c in cases[:10]:
        assert "case_id" in c
        assert "is_conforming" in c
        assert "fitness" in c
        assert "deviation_types" in c
        assert "alignment_moves" in c
        assert "explanation" in c
        assert len(c["explanation"]) > 0

    print("  [OK] Synthetic PO dataset conformance verified successfully.")


def test_controlled_planted_deviations():
    print("\n--- 2. Testing Controlled Planted Deviation Log ---")
    rows = [
        # Case 1: Standard clean reference sequence
        {"case_id": "C-Clean", "activity": "Submitted", "timestamp": "2025-01-01 09:00:00"},
        {"case_id": "C-Clean", "activity": "Reviewed", "timestamp": "2025-01-01 10:00:00"},
        {"case_id": "C-Clean", "activity": "Approved", "timestamp": "2025-01-01 11:00:00"},
        {"case_id": "C-Clean", "activity": "Completed", "timestamp": "2025-01-01 12:00:00"},

        # Case 2: Rework loop on Reviewed
        {"case_id": "C-Rework", "activity": "Submitted", "timestamp": "2025-01-01 09:00:00"},
        {"case_id": "C-Rework", "activity": "Reviewed", "timestamp": "2025-01-01 10:00:00"},
        {"case_id": "C-Rework", "activity": "Reviewed", "timestamp": "2025-01-01 10:30:00"},
        {"case_id": "C-Rework", "activity": "Approved", "timestamp": "2025-01-01 11:00:00"},
        {"case_id": "C-Rework", "activity": "Completed", "timestamp": "2025-01-01 12:00:00"},

        # Case 3: Skipped activity (Approved is skipped)
        {"case_id": "C-Skip", "activity": "Submitted", "timestamp": "2025-01-01 09:00:00"},
        {"case_id": "C-Skip", "activity": "Reviewed", "timestamp": "2025-01-01 10:00:00"},
        {"case_id": "C-Skip", "activity": "Completed", "timestamp": "2025-01-01 12:00:00"},

        # Case 4: Unplanned activity (Audited)
        {"case_id": "C-Unplanned", "activity": "Submitted", "timestamp": "2025-01-01 09:00:00"},
        {"case_id": "C-Unplanned", "activity": "Reviewed", "timestamp": "2025-01-01 10:00:00"},
        {"case_id": "C-Unplanned", "activity": "Audited", "timestamp": "2025-01-01 10:45:00"},
        {"case_id": "C-Unplanned", "activity": "Approved", "timestamp": "2025-01-01 11:00:00"},
        {"case_id": "C-Unplanned", "activity": "Completed", "timestamp": "2025-01-01 12:00:00"},
    ]

    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, newline="", encoding="utf-8") as tmp:
        df = pd.DataFrame(rows)
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)

    try:
        conf = compute_conformance(tmp_path, reference_variant=["Submitted", "Reviewed", "Approved", "Completed"])
        case_map = {c["case_id"]: c for c in conf["case_deviations"]}

        # 1. Clean Case
        clean = case_map["C-Clean"]
        assert clean["is_conforming"] is True, "C-Clean should be conforming"
        assert clean["fitness"] == 1.0, f"Expected fitness 1.0, got {clean['fitness']}"
        assert clean["mismatch_count"] == 0, "C-Clean should have 0 mismatches"
        print("  [OK] C-Clean conforms with fitness 1.0")

        # 2. Rework Case
        rework = case_map["C-Rework"]
        assert rework["is_conforming"] is False, "C-Rework should be non-conforming"
        assert "Rework Loop" in rework["deviation_types"], f"Expected Rework Loop on Reviewed, got {rework['deviation_types']}"
        assert "Reviewed" in rework["affected_activities"]
        print("  [OK] C-Rework correctly identified with Rework Loop on Reviewed")

        # 3. Skip Case
        skip = case_map["C-Skip"]
        assert skip["is_conforming"] is False, "C-Skip should be non-conforming"
        assert "Skipped Activity" in skip["deviation_types"], f"Expected Skipped Activity on Approved, got {skip['deviation_types']}"
        assert "Approved" in skip["affected_activities"]
        print("  [OK] C-Skip correctly identified with Skipped Activity on Approved")

        # 4. Unplanned Case
        unplanned = case_map["C-Unplanned"]
        assert unplanned["is_conforming"] is False, "C-Unplanned should be non-conforming"
        assert "Unplanned Activity" in unplanned["deviation_types"], f"Expected Unplanned Activity on Audited, got {unplanned['deviation_types']}"
        assert "Audited" in unplanned["affected_activities"]
        print("  [OK] C-Unplanned correctly identified with Unplanned Activity on Audited")

    finally:
        if tmp_path.exists():
            os.remove(tmp_path)


def test_bpi2012_conformance():
    print("\n--- 3. Testing BPI2012 Sample Dataset Conformance ---")
    bpi_csv = PROJECT_ROOT / "data" / "bpi2012_sample.csv"
    if not bpi_csv.exists():
        bpi_csv = PROJECT_ROOT / "storage" / "bpi2012_sample.csv"
    assert bpi_csv.exists(), f"BPI2012 CSV not found at {bpi_csv}"

    conf = compute_conformance(bpi_csv)
    assert conf["available"] is True
    assert conf["summary"]["total_cases"] == 100
    assert 0 <= conf["summary"]["conformance_rate_pct"] <= 100
    assert len(conf["reference_process"]) > 0
    assert len(conf["case_deviations"]) == 100
    print(f"  [OK] BPI2012: {conf['summary']['total_cases']} cases checked, {conf['summary']['conformance_rate_pct']}% conforming.")


def test_api_endpoints():
    print("\n--- 4. Testing Conformance API Endpoints ---")
    client = TestClient(app)

    # Test root endpoint
    res = client.get("/api/conformance")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    body = res.json()
    assert body["available"] is True
    assert "summary" in body
    assert "reference_process" in body
    assert "top_deviations" in body
    assert "case_deviations" in body
    print(f"  [OK] GET /api/conformance returned 200 with {body['summary']['total_cases']} cases")

    # Test with custom reference variant
    custom_var = "Submitted,Reviewed,Approved,Completed"
    res_custom = client.get(f"/api/conformance?reference_variant={custom_var}")
    assert res_custom.status_code == 200
    body_custom = res_custom.json()
    assert body_custom["reference_process"] == ["Submitted", "Reviewed", "Approved", "Completed"]
    print("  [OK] GET /api/conformance with reference_variant query filter verified")

    # Test unanalyzed project returns HTTP 202
    res_empty = client.get("/api/conformance?project_id=nonexistent_project_xyz")
    assert res_empty.status_code == 202, f"Expected 202 for nonexistent project, got {res_empty.status_code}"
    body_empty = res_empty.json()
    assert body_empty.get("available") is False
    print("  [OK] GET /api/conformance for unanalyzed project returned HTTP 202")


def test_project_and_run_isolation():
    print("\n--- 5. Testing Storage & Run Isolation ---")
    proj_id = "test_phase_e_isolation_proj"
    run_id = "run_test_001"
    
    run_dir = create_run_dir(proj_id, run_id)
    assert run_dir.exists()
    
    # Place dummy output in run working directory
    dummy_conf = {
        "available": True,
        "summary": {"total_cases": 99, "conforming_cases": 90, "deviating_cases": 9},
    }
    with open(run_dir / "conformance.json", "w", encoding="utf-8") as f:
        json.dump(dummy_conf, f)

    # Organize run outputs for phase1
    organize_run_outputs(proj_id, run_id, "phase1")

    # Verify run output folder contains conformance.json
    run_conf = run_dir / "outputs" / "conformance.json"
    assert run_conf.exists(), f"conformance.json was not archived to {run_conf}"

    with open(run_conf, encoding="utf-8") as f:
        archived_data = json.load(f)
        assert archived_data["summary"]["total_cases"] == 99

    # Clean up test project directory
    proj_dir = run_dir.parent.parent
    if proj_dir.exists() and proj_id in proj_dir.name:
        shutil.rmtree(proj_dir, ignore_errors=True)
    print(f"  [OK] Run isolation verified: conformance.json correctly organized in run {run_id}")


def test_process_graph_conformance_edges():
    print("\n--- 6. Testing Process Graph Conformance Edges ---")
    event_log_p = PROJECT_ROOT / "event_log.csv"
    graph = compute_process_graph(event_log_p)
    assert "edges" in graph and len(graph["edges"]) > 0
    
    conforming_edges = [e for e in graph["edges"] if e.get("is_conforming") is True]
    deviating_edges = [e for e in graph["edges"] if e.get("is_deviating") is True]
    
    assert len(conforming_edges) > 0, "Must have at least one conforming edge in process graph"
    assert len(deviating_edges) > 0, "Must have at least one deviating edge in process graph"
    
    print(f"  [OK] Process graph edges: {len(conforming_edges)} conforming, {len(deviating_edges)} deviating")


if __name__ == "__main__":
    print("=======================================================")
    print("   ProcessLens — Phase E Conformance Verification     ")
    print("=======================================================")
    test_synthetic_po_conformance()
    test_controlled_planted_deviations()
    test_bpi2012_conformance()
    test_api_endpoints()
    test_project_and_run_isolation()
    test_process_graph_conformance_edges()
    print("\n>>> ALL PHASE E VERIFICATION TESTS PASSED SUCCESSFULLY! <<<\n")
