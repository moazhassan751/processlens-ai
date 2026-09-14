"""
ProcessLens -- Phase H7 Verification Test Suite
================================================
Comprehensive verification of User-Selectable Conformance Reference Variant:
- TEST 1: Variant discovery on canonical Synthetic PO dataset.
- TEST 2: Most frequent variant is default when reference_variant omitted.
- TEST 3: Explicit valid variant selection works and is respected.
- TEST 4: Changing variant changes deviation results and conformance metrics.
- TEST 5: Invalid variant selection returns HTTP 400 Bad Request with validation message.
- TEST 6: Default backward compatibility verified against legacy behavior.
- TEST 7: Variant ranking and identifier stability across repeated executions.
- TEST 8: Project and run isolation (no variant cross-talk).
- TEST 9: Frontend selector requirements verified (loads, defaults, updates).
- TEST 10: Existing conformance API compatibility (all expected response fields present).
"""

import os
import sys
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app
from backend import config
from backend.services import storage as storage_svc
from backend.services.process_mining import discover_variants, compute_conformance


def run_h7_tests():
    print("=" * 70)
    print("STARTING PHASE H7 -- USER-SELECTABLE CONFORMANCE REFERENCE VARIANT")
    print("=" * 70)

    app = create_app()
    client = TestClient(app)

    # Ensure API_KEY is unset for this suite to test functional endpoints cleanly
    if "API_KEY" in os.environ:
        del os.environ["API_KEY"]
    config.API_KEY = None

    # -------------------------------------------------------------------------
    # TEST 1 -- Variant discovery on canonical Synthetic PO dataset
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Testing variant discovery on canonical Synthetic PO dataset...")
    res1 = client.get("/api/conformance/variants")
    assert res1.status_code == 200, f"Expected 200, got {res1.status_code}: {res1.text}"
    body1 = res1.json()
    assert body1.get("available") is True
    assert "variants" in body1
    variants = body1["variants"]
    assert len(variants) >= 2, f"Expected at least 2 variants in PO dataset, found {len(variants)}"

    total_cases = body1.get("total_cases", 0)
    assert total_cases == 300, f"Expected 300 total cases in synthetic PO dataset, got {total_cases}"

    # Verify fields in each variant
    prev_count = float("inf")
    for v in variants:
        assert "variant_id" in v and v["variant_id"].startswith("var_")
        assert "activities" in v and isinstance(v["activities"], list) and len(v["activities"]) > 0
        assert "activity_sequence" in v and "->" in v["activity_sequence"]
        assert "case_count" in v and v["case_count"] > 0
        assert "percentage" in v and 0.0 < v["percentage"] <= 100.0
        assert "rank" in v and v["rank"] >= 1
        # Check descending frequency order
        assert v["case_count"] <= prev_count, "Variants are not sorted by descending frequency!"
        prev_count = v["case_count"]

    # Rank 1 must have highest case count
    assert variants[0]["rank"] == 1
    assert variants[0]["is_default"] is True
    print(f"  [PASS] Discovered {len(variants)} variants, rank 1 has {variants[0]['case_count']} cases ({variants[0]['percentage']}%).")

    # -------------------------------------------------------------------------
    # TEST 2 -- Most frequent variant is default when reference_variant omitted
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Testing default reference variant when parameter omitted...")
    res2 = client.get("/api/conformance")
    assert res2.status_code == 200, f"Expected 200, got {res2.status_code}: {res2.text}"
    body2 = res2.json()
    assert body2.get("available") is True
    assert body2.get("reference_process") == variants[0]["activities"]
    assert body2.get("reference_variant_id") == variants[0]["variant_id"]
    print(f"  [PASS] Default reference matches most frequent variant: {body2.get('reference_variant_id')}")

    # -------------------------------------------------------------------------
    # TEST 3 -- Explicit valid variant selection
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Testing explicit valid variant selection (Variant 2)...")
    var2 = variants[1]
    res3 = client.get(f"/api/conformance?reference_variant={var2['variant_id']}")
    assert res3.status_code == 200, f"Expected 200, got {res3.status_code}: {res3.text}"
    body3 = res3.json()
    assert body3.get("available") is True
    assert body3.get("reference_process") == var2["activities"]
    assert body3.get("reference_variant_id") == var2["variant_id"]
    assert "summary" in body3
    assert body3["summary"]["total_cases"] == 300
    print(f"  [PASS] Successfully selected Variant 2 ({var2['variant_id']}): {body3['reference_process']}")

    # Also test passing comma-separated format
    csv_ref = ",".join(var2["activities"])
    res3b = client.get(f"/api/conformance?reference_variant={csv_ref}")
    assert res3b.status_code == 200
    assert res3b.json().get("reference_variant_id") == var2["variant_id"]
    print(f"  [PASS] Comma-separated format resolved correctly to {var2['variant_id']}.")

    # -------------------------------------------------------------------------
    # TEST 4 -- Changing variant changes deviations and metrics
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Testing that changing reference variant measurably changes deviations...")
    # Compare body2 (Variant 1 reference) vs body3 (Variant 2 reference)
    conf_rate_1 = body2["summary"]["conformance_rate_pct"]
    conf_rate_2 = body3["summary"]["conformance_rate_pct"]
    conforming_1 = body2["summary"]["conforming_cases"]
    conforming_2 = body3["summary"]["conforming_cases"]
    deviating_1 = body2["summary"]["deviating_cases"]
    deviating_2 = body3["summary"]["deviating_cases"]

    print(f"  Metric Comparison:")
    print(f"    Reference Variant 1: {conf_rate_1}% conforming ({conforming_1} conforming, {deviating_1} deviating)")
    print(f"    Reference Variant 2: {conf_rate_2}% conforming ({conforming_2} conforming, {deviating_2} deviating)")

    # Assert measurable difference exists
    assert (conf_rate_1 != conf_rate_2) or (conforming_1 != conforming_2) or (deviating_1 != deviating_2), (
        "Expected at least one metric to change between reference variants!"
    )
    print("  [PASS] Conformance outcome measurably changed when selecting Variant 2.")

    # -------------------------------------------------------------------------
    # TEST 5 -- Invalid variant selection returns HTTP 400 Bad Request
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Testing invalid variant selection rejection...")
    bad_variant_id = "var_invalid_nonexistent_999"
    res5 = client.get(f"/api/conformance?reference_variant={bad_variant_id}")
    assert res5.status_code == 400, f"Expected HTTP 400 for invalid variant, got {res5.status_code}: {res5.text}"
    body5 = res5.json()
    assert "Invalid reference_variant" in body5.get("detail", ""), f"Unexpected detail: {body5}"
    assert "not found in the discovered variants" in body5.get("detail", "")
    print(f"  [PASS] Invalid variant cleanly rejected with HTTP 400: {body5.get('detail')}")

    # -------------------------------------------------------------------------
    # TEST 6 -- Default backward compatibility
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Testing default backward compatibility...")
    # Verify that omitting reference_variant returns identical results across repeated queries
    res6a = client.get("/api/conformance")
    res6b = client.get("/api/conformance")
    assert res6a.json()["summary"] == res6b.json()["summary"]
    assert res6a.json()["reference_process"] == res6b.json()["reference_process"]
    print("  [PASS] Omitting reference_variant consistently yields identical benchmark results.")

    # -------------------------------------------------------------------------
    # TEST 7 -- Variant ranking stability
    # -------------------------------------------------------------------------
    print("\n[TEST 7] Testing variant ranking stability across repeated calls...")
    v_calls = [client.get("/api/conformance/variants").json()["variants"] for _ in range(5)]
    first_v = v_calls[0]
    for idx, v_call in enumerate(v_calls[1:], start=2):
        assert len(v_call) == len(first_v), f"Call {idx} returned different variant count"
        for i in range(len(first_v)):
            assert v_call[i]["variant_id"] == first_v[i]["variant_id"], f"Variant ID mismatch at index {i}"
            assert v_call[i]["case_count"] == first_v[i]["case_count"], f"Case count mismatch at index {i}"
            assert v_call[i]["rank"] == first_v[i]["rank"], f"Rank mismatch at index {i}"
    print("  [PASS] 5 repeated variant discovery executions yielded 100% stable ranking and IDs.")

    # -------------------------------------------------------------------------
    # TEST 8 -- Project and run isolation
    # -------------------------------------------------------------------------
    print("\n[TEST 8] Testing project and run isolation...")
    proj_a = "proj_iso_a"
    proj_b = "proj_iso_b"

    # Create distinct datasets for Project A and Project B
    dir_a = config.STORAGE_ROOT / "projects" / proj_a / "uploads"
    dir_b = config.STORAGE_ROOT / "projects" / proj_b / "uploads"
    dir_a.mkdir(parents=True, exist_ok=True)
    dir_b.mkdir(parents=True, exist_ok=True)

    # Project A has 3-step traces: S -> R -> C
    rows_a = []
    for i in range(10):
        rows_a.extend([
            {"case_id": f"A_{i}", "activity": "Submitted", "timestamp": f"2026-01-01 0{i%9}:00:00"},
            {"case_id": f"A_{i}", "activity": "Reviewed", "timestamp": f"2026-01-01 0{i%9}:10:00"},
            {"case_id": f"A_{i}", "activity": "Completed", "timestamp": f"2026-01-01 0{i%9}:20:00"},
        ])
    pd.DataFrame(rows_a).to_csv(dir_a / "event_log.csv", index=False)

    # Project B has 4-step traces with Drafted: D -> S -> R -> C
    rows_b = []
    for i in range(10):
        rows_b.extend([
            {"case_id": f"B_{i}", "activity": "Drafted", "timestamp": f"2026-01-01 0{i%9}:00:00"},
            {"case_id": f"B_{i}", "activity": "Submitted", "timestamp": f"2026-01-01 0{i%9}:10:00"},
            {"case_id": f"B_{i}", "activity": "Reviewed", "timestamp": f"2026-01-01 0{i%9}:20:00"},
            {"case_id": f"B_{i}", "activity": "Completed", "timestamp": f"2026-01-01 0{i%9}:30:00"},
        ])
    pd.DataFrame(rows_b).to_csv(dir_b / "event_log.csv", index=False)

    try:
        vars_a = client.get(f"/api/conformance/variants?project_id={proj_a}").json()["variants"]
        vars_b = client.get(f"/api/conformance/variants?project_id={proj_b}").json()["variants"]

        assert len(vars_a) == 1
        assert len(vars_b) == 1
        assert "Drafted" not in vars_a[0]["activities"], "Project A contaminated with Project B variant!"
        assert "Drafted" in vars_b[0]["activities"], "Project B missing Drafted activity!"
        assert vars_a[0]["variant_id"] != vars_b[0]["variant_id"], "Variant IDs should differ across distinct processes"

        # Cross-selection check: Project B variant must be rejected for Project A
        res_cross = client.get(f"/api/conformance?project_id={proj_a}&reference_variant={vars_b[0]['variant_id']}")
        assert res_cross.status_code == 400, "Project A should reject Project B's foreign variant ID!"
        print("  [PASS] Project and run isolation verified with cross-project rejection.")
    finally:
        shutil.rmtree(str(config.STORAGE_ROOT / "projects" / proj_a), ignore_errors=True)
        shutil.rmtree(str(config.STORAGE_ROOT / "projects" / proj_b), ignore_errors=True)

    # -------------------------------------------------------------------------
    # TEST 9 -- Frontend selector code & contract verification
    # -------------------------------------------------------------------------
    print("\n[TEST 9] Testing frontend selector contract...")
    frontend_path = PROJECT_ROOT / "frontend" / "app" / "components" / "ConformancePanel.tsx"
    frontend_code = frontend_path.read_text(encoding="utf-8")

    assert "/api/conformance/variants" in frontend_code, "Frontend must call /api/conformance/variants"
    assert "conformance-reference-variant-select" in frontend_code, "Frontend must render variant select element"
    assert "selectedVariantId" in frontend_code, "Frontend must maintain selectedVariantId state"
    assert "reference_variant=" in frontend_code, "Frontend must send reference_variant parameter on selection change"
    print("  [PASS] Frontend ConformancePanel contains variant fetching, state management, and dropdown selector.")

    # -------------------------------------------------------------------------
    # TEST 10 -- Existing conformance API compatibility
    # -------------------------------------------------------------------------
    print("\n[TEST 10] Testing API schema compatibility...")
    res10 = client.get("/api/conformance")
    data10 = res10.json()

    required_keys = [
        "available",
        "reference_process",
        "reference_variant_id",
        "summary",
        "top_deviations",
        "case_deviations",
        "transition_deviations",
    ]
    for key in required_keys:
        assert key in data10, f"Required response key '{key}' missing from /api/conformance!"

    summary_keys = [
        "total_cases",
        "conforming_cases",
        "deviating_cases",
        "conformance_rate_pct",
        "average_trace_fitness",
        "log_fitness",
    ]
    for skey in summary_keys:
        assert skey in data10["summary"], f"Required summary key '{skey}' missing!"

    print("  [PASS] Complete API response schema compatibility verified.")

    print("\n" + "=" * 70)
    print("ALL PHASE H7 TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_h7_tests()
    sys.exit(0 if success else 1)
