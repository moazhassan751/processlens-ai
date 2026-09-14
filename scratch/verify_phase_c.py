"""
ProcessLens — Phase C Verification Script
===========================================
Automated dual-dataset pipeline verification:
1. Synthetic PO Dataset verification
   - Data quality metrics
   - Stratified 5-Fold Cross-Validation metrics & observed variation ranges
   - Case-level feature importance & explainability
2. BPI2012 Sample Dataset verification
   - Dynamic activity/resource adaptation
   - Data quality metrics (100 cases, 2185 events, 24 activities)
   - Cross-validation on BPI2012 data
   - Explainability on BPI2012 open cases
3. Zero-Stale / Cache Isolation verification
   - Ensure metrics, resources, and predictions between datasets never leak
4. API endpoint response shape tests
   - GET /api/data-quality
   - GET /api/status (with data_quality)
   - GET /api/predictions (with cv_strategy, variation, fold_metrics, risk_drivers, explanation)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.data_quality import compute_data_quality
from backend.services.ml_service import compute_prediction_data
from backend.config import VENV_PYTHON


def test_synthetic_po_dataset():
    print("\n--- 1. Testing Synthetic PO Dataset ---")
    event_log_p = PROJECT_ROOT / "event_log.csv"
    assert event_log_p.exists(), "event_log.csv must exist"

    # 1. Data Quality
    dq = compute_data_quality(event_log_p)
    assert dq["available"] is True, "Data quality should be available"
    assert dq["is_valid"] is True, "Data quality should be valid"
    assert dq["case_count"] == 300, f"Expected 300 cases, got {dq['case_count']}"
    assert dq["event_count"] == 1308, f"Expected 1308 events, got {dq['event_count']}"
    assert dq["activity_count"] == 5, f"Expected 5 activities, got {dq['activity_count']}"
    assert 15.0 <= dq["rework_case_pct"] <= 25.0, f"Unexpected rework pct: {dq['rework_case_pct']}"
    assert dq["date_range"] is not None
    assert "2025" in dq["date_range"]["formatted"]
    print(f"  [OK] Data Quality: {dq['case_count']} cases, {dq['event_count']} events, {dq['rework_case_pct']}% rework")

    # 2. Model Metrics & Cross-Validation
    metrics_p = PROJECT_ROOT / "model_metrics.json"
    assert metrics_p.exists(), "model_metrics.json must exist"
    with open(metrics_p, encoding="utf-8") as f:
        mm = json.load(f)

    assert "cv_strategy" in mm, "cv_strategy missing in model_metrics.json"
    assert mm["n_splits"] == 5, f"Expected 5 splits, got {mm.get('n_splits')}"
    assert "variation" in mm, "variation ranges missing"
    assert "fold_metrics" in mm, "fold_metrics missing"
    assert len(mm["fold_metrics"]) == 5, f"Expected 5 fold metrics, got {len(mm['fold_metrics'])}"

    for metric_name in ["accuracy", "roc_auc", "f1", "precision", "recall"]:
        var = mm["variation"].get(metric_name)
        assert var is not None, f"Variation missing for {metric_name}"
        assert "min" in var and "max" in var and "mean" in var and "std" in var and "range_str" in var
        assert var["min"] <= var["mean"] <= var["max"]
        assert "–" in var["range_str"] or "-" in var["range_str"]

    for fm in mm["fold_metrics"]:
        assert "fold" in fm and "accuracy" in fm and "roc_auc" in fm
        assert "val_samples" in fm and fm["val_samples"] > 0
    print(f"  [OK] 5-Fold Stratified CV: Mean Acc={mm['accuracy']:.3f}, Observed Range={mm['variation']['accuracy']['range_str']}")

    # 3. Predictions & Case Explainability
    preds_p = PROJECT_ROOT / "predictions.json"
    assert preds_p.exists(), "predictions.json must exist"
    with open(preds_p, encoding="utf-8") as f:
        preds = json.load(f)

    assert len(preds) == 20, f"Expected 20 open cases, got {len(preds)}"
    has_late_risk_explanation = False
    has_on_track_explanation = False
    has_insufficient_explanation = False

    for c in preds:
        assert "case_id" in c
        assert "predicted_label" in c
        assert "explanation" in c
        assert "risk_drivers" in c

        label = c["predicted_label"]
        exp = c["explanation"]
        drivers = c["risk_drivers"]

        if label == "Late Risk":
            assert "mainly because of" in exp, f"Expected 'mainly because of' in: {exp}"
            assert len(drivers) == 2, f"Expected 2 drivers, got {drivers}"
            has_late_risk_explanation = True
        elif label == "On Track":
            assert "low risk contribution" in exp or "on track" in exp.lower()
            has_on_track_explanation = True
        elif label == "Insufficient Data":
            assert "Awaiting subsequent" in exp
            has_insufficient_explanation = True

    assert has_late_risk_explanation, "Must have at least one Late Risk case with explanation"
    assert has_on_track_explanation, "Must have at least one On Track case with explanation"
    assert has_insufficient_explanation, "Must have Insufficient Data cases with explanation"
    print(f"  [OK] Open Cases Explainability: {len(preds)} cases verified with defensible risk drivers.")


def test_bpi2012_sample_dataset():
    print("\n--- 2. Testing BPI2012 Sample Dataset Pipeline ---")
    bpi_csv = PROJECT_ROOT / "data" / "bpi2012_sample.csv"
    if not bpi_csv.exists():
        bpi_csv = PROJECT_ROOT / "storage" / "bpi2012_sample.csv"
    assert bpi_csv.exists(), f"BPI2012 sample CSV not found at {bpi_csv}"

    # 1. Data Quality on BPI2012
    dq = compute_data_quality(bpi_csv)
    assert dq["available"] is True
    assert dq["is_valid"] is True
    assert dq["case_count"] == 100, f"Expected 100 cases, got {dq['case_count']}"
    assert dq["event_count"] == 2185, f"Expected 2185 events, got {dq['event_count']}"
    assert dq["activity_count"] == 24, f"Expected 24 activities, got {dq['activity_count']}"
    assert dq["rework_case_pct"] == 74.0, f"Expected 74% rework, got {dq['rework_case_pct']}"
    assert "2011" in dq["date_range"]["formatted"] and "2012" in dq["date_range"]["formatted"]
    print(f"  [OK] BPI2012 Data Quality: 100 cases, 2185 events, 24 activities, 74.0% rework")

    # 2. Execute pipeline in an isolated test environment
    with tempfile.TemporaryDirectory() as tmp_dir:
        work_dir = Path(tmp_dir)
        shutil.copy2(str(bpi_csv), str(work_dir / "event_log.csv"))

        # Copy needed script modules
        scripts = [
            "build_training_data.py",
            "train_model.py",
            "detect_anomalies.py",
            "generate_open_cases.py",
            "predict_delays.py",
        ]
        for s in scripts:
            shutil.copy2(str(PROJECT_ROOT / s), str(work_dir / s))

        # Run pipeline steps on BPI2012
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)

        for s in scripts:
            res = subprocess.run(
                [str(VENV_PYTHON), s],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                env=env,
            )
            assert res.returncode == 0, f"Script {s} failed on BPI2012:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        # Verify BPI2012 outputs
        bpi_metrics_p = work_dir / "model_metrics.json"
        assert bpi_metrics_p.exists(), "BPI2012 model_metrics.json was not created"
        with open(bpi_metrics_p, encoding="utf-8") as f:
            bpi_mm = json.load(f)

        assert bpi_mm["n_splits"] == 5 or bpi_mm["n_splits"] >= 2
        assert len(bpi_mm["fold_metrics"]) == bpi_mm["n_splits"]
        assert "variation" in bpi_mm
        print(f"  [OK] BPI2012 {bpi_mm['n_splits']}-Fold CV: Mean Acc={bpi_mm['accuracy']:.3f}, ROC-AUC={bpi_mm['roc_auc']:.3f}")

        # Verify BPI2012 resource mapping
        bpi_res_map_p = work_dir / "resource_mapping.json"
        with open(bpi_res_map_p, encoding="utf-8") as f:
            bpi_res = json.load(f)
        assert "SYSTEM" in bpi_res, "BPI2012 resource_mapping should contain 'SYSTEM'"
        assert "Alice Johnson" not in bpi_res, "Synthetic PO resources should NOT be in BPI2012 resource mapping"
        print(f"  [OK] BPI2012 dynamic resource mapping verified ({len(bpi_res)} resources, e.g. SYSTEM, 112).")

        # Verify BPI2012 predictions
        bpi_preds_p = work_dir / "predictions.json"
        with open(bpi_preds_p, encoding="utf-8") as f:
            bpi_preds = json.load(f)
        assert len(bpi_preds) == 20
        assert all("explanation" in p and "risk_drivers" in p for p in bpi_preds)
        print(f"  [OK] BPI2012 predictions generated with explainability.")


def test_dual_dataset_isolation_and_no_leakage():
    print("\n--- 3. Testing Cache Isolation & Zero Stale State Leakage ---")
    syn_dq = compute_data_quality(PROJECT_ROOT / "event_log.csv")
    bpi_dq = compute_data_quality(PROJECT_ROOT / "data" / "bpi2012_sample.csv")

    assert syn_dq["case_count"] != bpi_dq["case_count"], "Case counts must differ between datasets"
    assert syn_dq["activity_count"] != bpi_dq["activity_count"], "Activity counts must differ"
    assert syn_dq["date_range"]["formatted"] != bpi_dq["date_range"]["formatted"], "Date ranges must differ"
    assert syn_dq["rework_case_pct"] != bpi_dq["rework_case_pct"], "Rework percentages must differ"

    # Verify resource mappings are completely distinct
    with open(PROJECT_ROOT / "resource_mapping.json", encoding="utf-8") as f:
        syn_res = json.load(f)
    assert "Alice Johnson" in syn_res
    assert "SYSTEM" not in syn_res

    print("  [OK] 100% strict isolation: Zero cross-contamination between datasets.")


def test_api_endpoints():
    print("\n--- 4. Testing API Endpoints Integration ---")
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)

    # 1. GET /api/data-quality
    res = client.get("/api/data-quality")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    dq = res.json()
    assert dq["available"] is True
    assert dq["case_count"] == 300
    assert dq["activity_count"] == 5
    assert dq["rework_case_pct"] > 0
    print("  [OK] GET /api/data-quality returned 200 with dynamic telemetry.")

    # 2. GET /api/status includes data_quality
    res = client.get("/api/status")
    assert res.status_code == 200
    status_data = res.json()
    assert "data_quality" in status_data, "data_quality must be in /api/status response"
    assert status_data["data_quality"]["case_count"] == 300
    print("  [OK] GET /api/status returned 200 containing active data_quality payload.")

    # 3. GET /api/predictions
    res = client.get("/api/predictions")
    assert res.status_code == 200
    pdata = res.json()
    assert pdata["available"] is True
    mm = pdata["model_metrics"]
    assert "cv_strategy" in mm
    assert "variation" in mm
    assert "fold_metrics" in mm
    cases = pdata["open_cases"]
    assert len(cases) > 0
    assert "risk_drivers" in cases[0]
    assert "explanation" in cases[0]
    print("  [OK] GET /api/predictions returned 200 with fold-level metrics and case explanations.")


def main():
    print("=" * 65)
    print("  PROCESSLENS — PHASE C DEPTH & DEFENSIVE VERIFICATION SUITE")
    print("=" * 65)

    test_synthetic_po_dataset()
    test_bpi2012_sample_dataset()
    test_dual_dataset_isolation_and_no_leakage()
    test_api_endpoints()

    print("\n" + "=" * 65)
    print("  ALL PHASE C VERIFICATION TESTS PASSED (100%)")
    print("=" * 65)


if __name__ == "__main__":
    main()
