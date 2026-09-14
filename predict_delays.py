"""
Phase 2, Step 6 -- Predict delay risk and anomaly flag for open cases.

For cases that have reached Reviewed: builds the same feature set as
training, predicts late-risk probability and anomaly flag.
For cases only at Submitted: outputs "Insufficient Data".
"""

import json
import sys
import joblib
import numpy as np
import pandas as pd
import shap
from ml_config import DEFAULT_RISK_THRESHOLD, classify_risk_probability
from prescriptive_engine import compute_prescriptive_action

OPEN_CASES_FILE = "open_cases.csv"
DELAY_MODEL_FILE = "delay_model.joblib"
ANOMALY_MODEL_FILE = "anomaly_model.joblib"
RESOURCE_MAPPING_FILE = "resource_mapping.json"
PREDICTIONS_FILE = "predictions.json"

FEATURE_COLS = [
    # Original 5 baseline features
    "elapsed_hours_so_far",
    "wait_before_reviewed_hours",
    "resource_at_reviewed",
    "hour_of_day_submitted",
    "has_been_reworked_yet",
    # Process progress
    "events_seen_so_far",
    "unique_activities_so_far",
    "transition_count_so_far",
    "activity_repetition_count",
    # Waiting behavior
    "total_wait_hours_so_far",
    "average_wait_hours_so_far",
    "max_wait_hours_so_far",
    "min_wait_hours_so_far",
    "number_of_long_waits_so_far",
    "time_since_previous_activity",
    # Timing & Calendar
    "hour_of_day_at_snapshot",
    "day_of_week_submitted",
    "day_of_week_at_snapshot",
    "is_weekend_submitted",
    # Resource context
    "resource_at_submitted",
]


def main():
    print("=" * 60)
    print("  PHASE 2, STEP 6 -- Predict Delays for Open Cases")
    print("=" * 60)

    # Load models
    try:
        clf = joblib.load(DELAY_MODEL_FILE)
        iso = joblib.load(ANOMALY_MODEL_FILE)
    except FileNotFoundError as e:
        print(f"  [ERROR] Model file not found: {e}")
        print("  Run train_model.py and detect_anomalies.py first.")
        sys.exit(1)

    # Initialize real SHAP TreeExplainer for the trained Random Forest classifier
    try:
        explainer = shap.TreeExplainer(clf)
    except Exception as e:
        print(f"  [ERROR] Failed to initialize shap.TreeExplainer: {e}")
        sys.exit(1)

    # Load resource mapping
    try:
        with open(RESOURCE_MAPPING_FILE, "r") as f:
            resource_map = json.load(f)
    except FileNotFoundError:
        print(f"  [ERROR] {RESOURCE_MAPPING_FILE} not found.")
        print("  Run build_training_data.py first.")
        sys.exit(1)

    # Load open cases
    df = pd.read_csv(OPEN_CASES_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Detect milestone activity (default to Reviewed if present)
    all_open_acts = set(df["activity"].unique())
    if "Reviewed" in all_open_acts:
        snapshot_act = "Reviewed"
    else:
        second_acts = df.groupby("case_id")["activity"].nth(1).value_counts()
        snapshot_act = second_acts.index[0] if not second_acts.empty else list(all_open_acts)[-1]

    predictions = []

    for case_id, group in df.groupby("case_id"):
        group = group.sort_values("timestamp")
        activities = group["activity"].tolist()
        current_step = activities[-1]

        if snapshot_act not in activities:
            # Not enough data to predict
            predictions.append({
                "case_id": case_id,
                "current_step": current_step,
                "late_risk_probability": None,
                "predicted_label": "Insufficient Data",
                "risk_label": "Insufficient Data",
                "risk_threshold": DEFAULT_RISK_THRESHOLD,
                "anomaly_flag": False,
                "elapsed_hours_so_far": 0.0,
                "risk_drivers": [],
                "feature_contributions": [],
                "base_value": None,
                "explanation": "Awaiting subsequent process milestones to evaluate delay risk.",
                "prescriptive_action": compute_prescriptive_action(
                    model=clf,
                    feature_row=pd.DataFrame(),
                    current_probability=None,
                    risk_label="Insufficient Data",
                    risk_drivers=[],
                    feature_cols=FEATURE_COLS,
                ),
            })
            continue

        # Build features at the snapshot
        start_ts = group.iloc[0]["timestamp"]
        submitted_events = group[group["activity"] == "Submitted"]
        submitted_ts = submitted_events.iloc[0]["timestamp"] if not submitted_events.empty else start_ts
        snapshot_events = group[group["activity"] == snapshot_act]
        snapshot_row = snapshot_events.iloc[0]
        snapshot_ts = snapshot_row["timestamp"]

        events_so_far = group[group["timestamp"] <= snapshot_ts]

        # 1. Baseline features
        elapsed = (snapshot_ts - start_ts).total_seconds() / 3600.0
        wait_before_snapshot = (snapshot_ts - submitted_ts).total_seconds() / 3600.0
        res_str = str(snapshot_row["resource"])
        resource_encoded = resource_map.get(res_str, -1)
        hour_submitted = submitted_ts.hour
        has_rework = 1 if len(events_so_far["activity"]) > len(set(events_so_far["activity"])) else 0

        # 2. Process progress features
        events_seen_so_far = len(events_so_far)
        unique_activities_so_far = events_so_far["activity"].nunique()
        transition_count_so_far = max(0, events_seen_so_far - 1)
        activity_repetition_count = events_seen_so_far - unique_activities_so_far

        # 3. Waiting behavior features
        if events_seen_so_far > 1:
            waits = events_so_far["timestamp"].diff().dropna().dt.total_seconds() / 3600.0
            total_wait_hours_so_far = float(waits.sum())
            average_wait_hours_so_far = float(waits.mean())
            max_wait_hours_so_far = float(waits.max())
            min_wait_hours_so_far = float(waits.min())
            number_of_long_waits_so_far = int((waits > 3.0).sum())
            time_since_previous_activity = float(waits.iloc[-1])
        else:
            total_wait_hours_so_far = average_wait_hours_so_far = 0.0
            max_wait_hours_so_far = min_wait_hours_so_far = 0.0
            number_of_long_waits_so_far = 0
            time_since_previous_activity = 0.0

        # 4. Timing & Calendar features
        hour_of_day_at_snapshot = snapshot_ts.hour
        day_of_week_submitted = submitted_ts.dayofweek
        day_of_week_at_snapshot = snapshot_ts.dayofweek
        is_weekend_submitted = 1 if day_of_week_submitted >= 5 else 0

        # 5. Resource context features
        start_res_str = str(group.iloc[0]["resource"])
        resource_at_submitted = resource_map.get(start_res_str, -1)

        features = pd.DataFrame([{
            "elapsed_hours_so_far": round(elapsed, 4),
            "wait_before_reviewed_hours": round(wait_before_snapshot, 4),
            "resource_at_reviewed": resource_encoded,
            "hour_of_day_submitted": hour_submitted,
            "has_been_reworked_yet": has_rework,
            "events_seen_so_far": events_seen_so_far,
            "unique_activities_so_far": unique_activities_so_far,
            "transition_count_so_far": transition_count_so_far,
            "activity_repetition_count": activity_repetition_count,
            "total_wait_hours_so_far": round(total_wait_hours_so_far, 4),
            "average_wait_hours_so_far": round(average_wait_hours_so_far, 4),
            "max_wait_hours_so_far": round(max_wait_hours_so_far, 4),
            "min_wait_hours_so_far": round(min_wait_hours_so_far, 4),
            "number_of_long_waits_so_far": number_of_long_waits_so_far,
            "time_since_previous_activity": round(time_since_previous_activity, 4),
            "hour_of_day_at_snapshot": hour_of_day_at_snapshot,
            "day_of_week_submitted": day_of_week_submitted,
            "day_of_week_at_snapshot": day_of_week_at_snapshot,
            "is_weekend_submitted": is_weekend_submitted,
            "resource_at_submitted": resource_at_submitted,
        }])

        prob = clf.predict_proba(features[FEATURE_COLS])[0][1]
        label = classify_risk_probability(prob, DEFAULT_RISK_THRESHOLD)
        anomaly_pred = iso.predict(features[FEATURE_COLS])[0]
        is_anomaly = bool(anomaly_pred == -1)

        # Compute model-derived feature contributions using real shap.TreeExplainer
        X_case = features[FEATURE_COLS]
        shap_exp = explainer(X_case)

        # Robust extraction of Class 1 (Late Risk) SHAP values
        raw_vals = getattr(shap_exp, "values", shap_exp)
        if isinstance(raw_vals, list):
            c1_vals = raw_vals[1] if len(raw_vals) > 1 else raw_vals[0]
        elif hasattr(raw_vals, "ndim"):
            if raw_vals.ndim == 3:
                c1_vals = raw_vals[0, :, 1] if raw_vals.shape[2] > 1 else raw_vals[0, :, 0]
            elif raw_vals.ndim == 2:
                if raw_vals.shape[0] == 1:
                    c1_vals = raw_vals[0]
                elif raw_vals.shape[1] > 1:
                    c1_vals = raw_vals[:, 1]
                else:
                    c1_vals = raw_vals[:, 0]
            else:
                c1_vals = raw_vals
        else:
            c1_vals = raw_vals

        shap_vals = [float(v) for v in np.asarray(c1_vals, dtype=float).flatten()]

        # Robust base value extraction
        if hasattr(shap_exp, "base_values"):
            bv = shap_exp.base_values
            if hasattr(bv, "ndim") and bv.ndim >= 2:
                base_val = float(bv[0, 1] if bv.shape[1] > 1 else bv[0, 0])
            elif hasattr(bv, "__len__") and len(bv) > 1:
                base_val = float(bv[1])
            else:
                base_val = float(bv)
        else:
            ev = getattr(explainer, "expected_value", 0.0)
            if isinstance(ev, (list, np.ndarray)) and len(ev) > 1:
                base_val = float(ev[1])
            else:
                base_val = float(ev)

        # Preserved feature ordering matching Random Forest feature order
        feature_contributions = [
            {
                "feature": col,
                "contribution": round(val, 4),
            }
            for col, val in zip(FEATURE_COLS, shap_vals)
        ]

        # Top risk drivers: features pushing most strongly towards Late Risk (highest positive SHAP)
        sorted_drivers = sorted(zip(FEATURE_COLS, shap_vals), key=lambda x: x[1], reverse=True)
        top_drivers = [d[0] for d in sorted_drivers[:2]]

        if label == "Late Risk":
            explanation = f"This case is flagged mainly because of {top_drivers[0]} and {top_drivers[1]}."
        else:
            explanation = f"Case is on track with low risk contribution across {top_drivers[0]} and {top_drivers[1]}."

        predictions.append({
            "case_id": case_id,
            "current_step": current_step,
            "late_risk_probability": round(float(prob), 4),
            "predicted_label": label,
            "risk_label": label,
            "risk_threshold": DEFAULT_RISK_THRESHOLD,
            "anomaly_flag": is_anomaly,
            "elapsed_hours_so_far": round(elapsed, 4),
            "risk_drivers": top_drivers,
            "feature_contributions": feature_contributions,
            "base_value": round(base_val, 4),
            "explanation": explanation,
            "prescriptive_action": compute_prescriptive_action(
                model=clf,
                feature_row=features,
                current_probability=round(float(prob), 4),
                risk_label=label,
                risk_drivers=top_drivers,
                feature_cols=FEATURE_COLS,
            ),
        })

    # Print table
    print()
    header = (
        f"  {'Case ID':<12} {'Step':<12} {'Risk Prob':>10} "
        f"{'Label':<20} {'Anomaly':<8} {'Elapsed (h)':>12}"
    )
    print(header)
    print("  " + "-" * 78)
    for p in predictions:
        prob_str = (
            f"{p['late_risk_probability']:.4f}"
            if p["late_risk_probability"] is not None
            else "    --    "
        )
        elapsed_str = f"{p['elapsed_hours_so_far']:.2f}"
        anomaly_str = "Yes" if p["anomaly_flag"] else "No"
        print(
            f"  {p['case_id']:<12} {p['current_step']:<12} {prob_str:>10} "
            f"{p['predicted_label']:<20} {anomaly_str:<8} {elapsed_str:>12}"
        )

    # Save predictions.json
    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2)

    print()
    print(f"  Predictions saved to: {PREDICTIONS_FILE}")

    # Summary counts
    n_late_risk = sum(1 for p in predictions if p["predicted_label"] == "Late Risk")
    n_on_track = sum(1 for p in predictions if p["predicted_label"] == "On Track")
    n_insufficient = sum(
        1 for p in predictions if p["predicted_label"] == "Insufficient Data"
    )
    n_anomalies = sum(1 for p in predictions if p["anomaly_flag"])

    print(
        f"  Late Risk: {n_late_risk}, On Track: {n_on_track}, "
        f"Insufficient Data: {n_insufficient}"
    )
    print(f"  Anomalies flagged: {n_anomalies}")
    print("=" * 60)

    return predictions


if __name__ == "__main__":
    main()
