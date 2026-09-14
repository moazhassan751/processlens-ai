"""
Phase 2, Steps 1 & 2 -- Build training data from event_log.csv.

Step 1: Define lateness threshold (75th percentile of total cycle time).
Step 2: Build features from partial case progress at the Reviewed snapshot.
"""

import json
import sys
import pandas as pd
from sklearn.model_selection import train_test_split

EVENT_LOG_FILE = "event_log.csv"
TRAINING_DATA_FILE = "training_data.csv"
RESOURCE_MAPPING_FILE = "resource_mapping.json"

# Same resource list as Phase 1's generate_data.py
RESOURCES = [
    "Alice Johnson", "Bob Smith", "Carol Lee",
    "David Kim", "Eva Martinez", "Frank Chen",
]
# Sorted for deterministic label encoding
RESOURCE_MAP = {name: i for i, name in enumerate(sorted(RESOURCES))}


def main():
    df = pd.read_csv(EVENT_LOG_FILE)
    if df["case_id"].nunique() < 10:
        print("ERROR: Dataset contains fewer than 10 cases. Minimum 10 cases required for training.")
        sys.exit(1)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    # Dynamic resource encoding from actual dataset
    unique_resources = sorted([str(r) for r in df["resource"].dropna().unique()])
    resource_map = {name: i for i, name in enumerate(unique_resources)}

    case_times = df.groupby("case_id")["timestamp"].agg(["min", "max"])
    case_times["total_cycle_hours"] = (
        (case_times["max"] - case_times["min"]).dt.total_seconds() / 3600.0
    )

    # Determine snapshot activity: default to Reviewed if present, else 2nd most common step
    all_acts = set(df["activity"].unique())
    if "Reviewed" in all_acts:
        snapshot_act = "Reviewed"
    else:
        second_acts = df.groupby("case_id")["activity"].nth(1).value_counts()
        snapshot_act = second_acts.index[0] if not second_acts.empty else list(all_acts)[1]

    print()
    print("=" * 60)
    print(f"  PHASE 2, STEP 2 -- Build Features ({snapshot_act} Snapshot)")
    print("=" * 60)

    rows = []
    for case_id, group in df.groupby("case_id"):
        group = group.sort_values("timestamp")

        # Find case start (first event)
        start_ts = group.iloc[0]["timestamp"]
        submitted_events = group[group["activity"] == "Submitted"]
        submitted_ts = submitted_events.iloc[0]["timestamp"] if not submitted_events.empty else start_ts

        # Find first snapshot event
        snapshot_events = group[group["activity"] == snapshot_act]
        if snapshot_events.empty:
            continue
        first_snapshot = snapshot_events.iloc[0]
        snapshot_ts = first_snapshot["timestamp"]

        # Filter strictly to events up to first snapshot timestamp (Leakage Boundary Guard)
        events_so_far = group[group["timestamp"] <= snapshot_ts]
        assert not events_so_far.empty, f"Prefix cannot be empty for case {case_id}"
        assert events_so_far["timestamp"].max() <= snapshot_ts, f"Temporal boundary violation in case {case_id}"

        # 1. Baseline features
        elapsed_hours_so_far = (snapshot_ts - start_ts).total_seconds() / 3600.0
        wait_before_reviewed = (snapshot_ts - submitted_ts).total_seconds() / 3600.0
        res_str = str(first_snapshot["resource"])
        resource_at_reviewed = resource_map.get(res_str, -1)
        hour_of_day_submitted = submitted_ts.hour
        has_been_reworked_yet = 1 if len(events_so_far["activity"]) > len(set(events_so_far["activity"])) else 0

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

        rows.append({
            "case_id": case_id,
            # Original 5 baseline features
            "elapsed_hours_so_far": round(elapsed_hours_so_far, 4),
            "wait_before_reviewed_hours": round(wait_before_reviewed, 4),
            "resource_at_reviewed": resource_at_reviewed,
            "hour_of_day_submitted": hour_of_day_submitted,
            "has_been_reworked_yet": has_been_reworked_yet,
            # Progress features
            "events_seen_so_far": events_seen_so_far,
            "unique_activities_so_far": unique_activities_so_far,
            "transition_count_so_far": transition_count_so_far,
            "activity_repetition_count": activity_repetition_count,
            # Waiting behavior features
            "total_wait_hours_so_far": round(total_wait_hours_so_far, 4),
            "average_wait_hours_so_far": round(average_wait_hours_so_far, 4),
            "max_wait_hours_so_far": round(max_wait_hours_so_far, 4),
            "min_wait_hours_so_far": round(min_wait_hours_so_far, 4),
            "number_of_long_waits_so_far": number_of_long_waits_so_far,
            "time_since_previous_activity": round(time_since_previous_activity, 4),
            # Timing & Calendar features
            "hour_of_day_at_snapshot": hour_of_day_at_snapshot,
            "day_of_week_submitted": day_of_week_submitted,
            "day_of_week_at_snapshot": day_of_week_at_snapshot,
            "is_weekend_submitted": is_weekend_submitted,
            # Resource context features
            "resource_at_submitted": resource_at_submitted,
            # Target cycle time
            "total_cycle_hours": round(
                case_times.loc[case_id, "total_cycle_hours"], 4
            ),
        })

    features_df = pd.DataFrame(rows)
    if len(features_df) < 10:
        print("ERROR: Fewer than 10 cases reached snapshot activity.")
        sys.exit(1)

    # ---- Step 1: Train/Test Split & Leakage-Free Lateness Threshold ------
    # Perform 80/20 train/test split BEFORE deriving the lateness threshold.
    # This prevents information leakage from the test distribution into labels.
    train_df, test_df = train_test_split(
        features_df,
        test_size=0.2,
        random_state=42,
    )

    # Compute 75th percentile using TRAINING SET CYCLE TIMES ONLY
    late_threshold = float(train_df["total_cycle_hours"].quantile(0.75))

    # Apply that SAME training-derived threshold to BOTH training and test rows
    train_df = train_df.copy()
    test_df = test_df.copy()
    train_df["late"] = (train_df["total_cycle_hours"] > late_threshold).astype(int)
    test_df["late"] = (test_df["total_cycle_hours"] > late_threshold).astype(int)

    # Recombine into complete dataset ordered by case_id for downstream consistency
    training_df = pd.concat([train_df, test_df]).sort_values("case_id").reset_index(drop=True)

    print("=" * 60)
    print("  PHASE 2, STEP 1 -- Define Lateness Threshold (Leakage-Free)")
    print("=" * 60)
    print(f"  Training samples: {len(train_df)}")
    print(f"  Test samples    : {len(test_df)}")
    print(f"  Threshold source: training split only")
    print(f"  Late threshold (75th percentile, TRAINING SET ONLY): {late_threshold:.2f} hours")
    n_train_late = int(train_df["late"].sum())
    n_test_late = int(test_df["late"].sum())
    n_total_late = int(training_df["late"].sum())
    print(f"  Training late cases : {n_train_late} ({n_train_late / len(train_df) * 100:.1f}%)")
    print(f"  Test late cases     : {n_test_late} ({n_test_late / len(test_df) * 100:.1f}%)")
    print(f"  Overall late cases  : {n_total_late} ({n_total_late / len(training_df) * 100:.1f}%)")
    print("=" * 60)

    training_df.to_csv(TRAINING_DATA_FILE, index=False)

    # Save resource mapping for predict_delays.py to reuse
    with open(RESOURCE_MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(resource_map, f, indent=2)

    print(f"  Training data shape: {training_df.shape}")
    print(f"  Saved to: {TRAINING_DATA_FILE}")
    print(f"  Resource mapping saved to: {RESOURCE_MAPPING_FILE}")
    print()
    print("  First 5 rows:")
    print(training_df.head().to_string(index=False))
    print("=" * 60)


if __name__ == "__main__":
    main()
