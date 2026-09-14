"""
Phase 2, Step 4 -- Anomaly detection using IsolationForest.

Trains on the snapshot features from all 300 completed cases.
Flags ~5% as anomalies and reports their total cycle time vs the average.
"""

import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib

TRAINING_DATA_FILE = "training_data.csv"
ANOMALY_MODEL_FILE = "anomaly_model.joblib"

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
    print("  PHASE 2, STEP 4 -- Anomaly Detection (IsolationForest)")
    print("=" * 60)

    df = pd.read_csv(TRAINING_DATA_FILE)
    X = df[FEATURE_COLS]

    iso = IsolationForest(contamination=0.05, random_state=42)
    iso.fit(X)

    df["anomaly"] = iso.predict(X)
    anomalies = df[df["anomaly"] == -1]

    avg_cycle = df["total_cycle_hours"].mean()

    print(f"  Total cases analyzed: {len(df)}")
    print(f"  Anomalies detected : {len(anomalies)}")
    print(f"  Average cycle time : {avg_cycle:.2f} hours")
    print()

    if len(anomalies) > 0:
        print(f"  {'Case ID':<15} {'Cycle Time (h)':>15} {'vs Average':>12}")
        print("  " + "-" * 45)
        for _, row in anomalies.iterrows():
            diff = row["total_cycle_hours"] - avg_cycle
            sign = "+" if diff >= 0 else ""
            print(
                f"  {row['case_id']:<15} {row['total_cycle_hours']:>15.2f} "
                f"{sign}{diff:>11.2f}"
            )
    else:
        print("  No anomalies detected.")

    # Save model
    joblib.dump(iso, ANOMALY_MODEL_FILE)
    print()
    print(f"  Anomaly model saved to: {ANOMALY_MODEL_FILE}")
    print("=" * 60)

    return len(anomalies)


if __name__ == "__main__":
    main()
