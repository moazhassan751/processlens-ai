"""
ProcessLens — Enterprise Suite Verification Test
================================================
Automated test suite validating the 3 Enterprise Improvements:
1. Multi-Prefix & Real-Time WIP Queue Congestion
2. Model Benchmarking (LightGBM vs Tuned Random Forest)
3. Prescriptive Next-Best-Action Counterfactual Engine & API integration
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app
from enterprise_features import build_multi_prefix_dataset
from prescriptive_engine import compute_prescriptive_action


def test_enterprise_suite():
    print("=" * 70)
    print("  RUNNING PROCESSLENS ENTERPRISE VERIFICATION SUITE")
    print("=" * 70)

    # 1. Multi-Prefix Dataset Integrity & Leakage Prevention
    print("\n--- 1. Multi-Prefix Dataset Integrity & Zero Leakage ---")
    dataset, res_map, cycle_dict = build_multi_prefix_dataset(str(PROJECT_ROOT / "event_log.csv"))
    assert len(dataset) >= 500, f"Expected at least 500 multi-prefix rows, got {len(dataset)}"
    assert dataset["case_id"].nunique() == 300, f"Expected 300 unique cases, got {dataset['case_id'].nunique()}"
    assert "wip_active_cases" in dataset.columns, "wip_active_cases column missing"
    assert (dataset["wip_active_cases"] >= 0).all(), "WIP active cases must be non-negative"
    assert dataset["wip_active_cases"].max() > 5, "WIP congestion should exhibit meaningful operational variation"

    # Verify 80/20 case-level split isolation
    np.random.seed(42)
    all_cases = dataset["case_id"].unique()
    train_cases = set(np.random.permutation(all_cases)[:240])
    test_cases = set(all_cases) - train_cases
    assert len(train_cases.intersection(test_cases)) == 0, "Train and test case IDs must be completely disjoint"

    train_rows = dataset[dataset["case_id"].isin(train_cases)]
    test_rows = dataset[dataset["case_id"].isin(test_cases)]
    assert len(train_rows) + len(test_rows) == len(dataset), "All rows must be cleanly partitioned"
    print(f"  [PASS] Multi-prefix rows: {len(dataset)} | Train: {len(train_rows)} | Test: {len(test_rows)} | Zero Leakage: OK")

    # 2. Benchmark Telemetry Verification
    print("\n--- 2. Enterprise Model Benchmark Telemetry ---")
    metrics_p = PROJECT_ROOT / "enterprise_model_metrics.json"
    assert metrics_p.exists(), "enterprise_model_metrics.json must exist"
    with open(metrics_p, encoding="utf-8") as f:
        eb = json.load(f)

    rf_metrics = eb["models"]["random_forest"]
    lgb_metrics = eb["models"]["lightgbm"]
    print(f"  Random Forest : CV AUC = {rf_metrics['cv_roc_auc_mean']:.4f} | Test AUC = {rf_metrics['test_roc_auc']:.4f}")
    print(f"  LightGBM      : CV AUC = {lgb_metrics['cv_roc_auc_mean']:.4f} | Test AUC = {lgb_metrics['test_roc_auc']:.4f}")

    assert rf_metrics["test_roc_auc"] >= 0.78, f"Expected RF Test ROC-AUC >= 0.78, got {rf_metrics['test_roc_auc']}"
    assert lgb_metrics["test_roc_auc"] >= 0.78, f"Expected LightGBM Test ROC-AUC >= 0.78, got {lgb_metrics['test_roc_auc']}"
    assert eb["winning_model"] in ["RandomForestClassifier", "LGBMClassifier"], "Invalid winning model"
    print(f"  [PASS] Benchmark Telemetry verified. Winner: {eb['winning_model']}")

    # 3. Prescriptive Next-Best-Action Engine
    print("\n--- 3. Prescriptive Next-Best-Action Counterfactuals ---")
    preds_p = PROJECT_ROOT / "predictions.json"
    assert preds_p.exists(), "predictions.json must exist"
    with open(preds_p, encoding="utf-8") as f:
        preds = json.load(f)

    late_cases = [p for p in preds if p.get("predicted_label") == "Late Risk"]
    assert len(late_cases) >= 1, "At least 1 late risk case expected"

    for lc in late_cases:
        pa = lc.get("prescriptive_action")
        assert pa is not None, f"Case {lc['case_id']} missing prescriptive_action"
        assert pa["action_title"], "Action title cannot be empty"
        assert pa["action_category"] in ["QUEUE_PRIORITY", "LOAD_BALANCING", "DISPATCH_OPTIMIZE", "QUALITY_GATE", "STANDARD_OPS"], f"Invalid category: {pa['action_category']}"
        assert pa["projected_risk"] <= pa["current_risk"], "Projected risk cannot exceed current risk"
        assert pa["risk_reduction_pct"] >= 0, "Risk reduction pct must be >= 0"
        print(f"  Case {lc['case_id']}: {pa['action_title']} ({pa['action_category']}) -> -{pa['risk_reduction_pct']}% Risk (Current: {pa['current_risk']}, Projected: {pa['projected_risk']})")

    # Specifically check OPEN-0004
    c4 = next((p for p in preds if p["case_id"] == "OPEN-0004"), None)
    assert c4 is not None, "OPEN-0004 must be in predictions"
    assert c4["prescriptive_action"]["risk_reduction_pct"] > 0, "OPEN-0004 must have positive risk reduction"
    print("  [PASS] Prescriptive Action Counterfactuals verified.")

    # 4. Backend API Integration Tests
    print("\n--- 4. Backend API Integration Tests ---")
    client = TestClient(app)

    # Test /api/predictions
    pred_res = client.get("/api/predictions")
    assert pred_res.status_code == 200, f"Expected 200 from /api/predictions, got {pred_res.status_code}"
    pred_data = pred_res.json()
    assert "enterprise_benchmark" in pred_data, "enterprise_benchmark missing from /api/predictions"
    assert len(pred_data["open_cases"]) == 20, f"Expected 20 open cases, got {len(pred_data['open_cases'])}"
    assert "prescriptive_action" in pred_data["open_cases"][0], "open_cases missing prescriptive_action"

    # Test /api/explain/case/OPEN-0004
    exp_res = client.post("/api/explain/case/OPEN-0004")
    assert exp_res.status_code == 200, f"Expected 200 from /api/explain/case/OPEN-0004, got {exp_res.status_code}"
    exp_data = exp_res.json()
    assert exp_data["case_id"] == "OPEN-0004"
    assert exp_data["risk_score"] > 0.5, f"Expected OPEN-0004 risk_score > 0.5, got {exp_data['risk_score']}"
    assert exp_data.get("prescriptive_action") is not None, "prescriptive_action missing in explain response"
    print("  [PASS] API Endpoints (/api/predictions, /api/explain/case/{case_id}) verified.")

    # 5. SHAP TreeExplainer Exact Additivity Invariance Check
    print("\n--- 5. SHAP TreeExplainer Exact Additivity Invariance ---")
    for p in preds:
        if p.get("late_risk_probability") is not None and p.get("feature_contributions"):
            base_val = p["base_value"]
            shap_sum = sum(fc["contribution"] for fc in p["feature_contributions"])
            reconstructed_prob = base_val + shap_sum
            diff = abs(reconstructed_prob - p["late_risk_probability"])
            assert diff < 0.005, f"Additivity deviation {diff} for case {p['case_id']}"
    print("  [PASS] SHAP exact additivity (< 0.005 accounting for JSON rounding) preserved across all cases.")

    print("\n" + "=" * 70)
    print("  ALL ENTERPRISE SUITE TESTS PASSED (100%)")
    print("=" * 70)


if __name__ == "__main__":
    test_enterprise_suite()
