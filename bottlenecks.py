"""
Step 4 — Rank bottlenecks using pandas directly on event_log.csv.

For each activity:
  - Average wait time (hours since previous event in that case)
  - Times repeated (how many cases have this activity more than once)
  - Delay contribution label: High / Medium / Low
"""

import sys
import pandas as pd

EVENT_LOG_FILE = "event_log.csv"


def analyze_bottlenecks(filepath: str = EVENT_LOG_FILE) -> pd.DataFrame:
    """
    Compute wait-time and rework metrics per activity.
    Returns a DataFrame sorted by avg_wait_hours descending.
    """
    try:
        df = pd.read_csv(filepath)
    except FileNotFoundError:
        print(f"ERROR: {filepath} not found. Run generate_data.py first.")
        sys.exit(1)

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    # --- Average wait time per activity ------------------------------------
    # For each event, compute hours since the previous event in the same case
    df["prev_ts"] = df.groupby("case_id")["timestamp"].shift(1)
    df["wait_hours"] = (df["timestamp"] - df["prev_ts"]).dt.total_seconds() / 3600.0

    # First event of each case has NaN wait — drop those for avg calculation
    wait_stats = (
        df.dropna(subset=["wait_hours"])
        .groupby("activity")["wait_hours"]
        .mean()
        .reset_index()
        .rename(columns={"wait_hours": "avg_wait_hours"})
    )

    # --- Rework indicator: cases that have the activity more than once -----
    activity_counts = df.groupby(["case_id", "activity"]).size().reset_index(name="count")
    rework = (
        activity_counts[activity_counts["count"] > 1]
        .groupby("activity")["case_id"]
        .nunique()
        .reset_index()
        .rename(columns={"case_id": "times_repeated"})
    )

    # --- Merge and label ---------------------------------------------------
    result = wait_stats.merge(rework, on="activity", how="left")
    result["times_repeated"] = result["times_repeated"].fillna(0).astype(int)
    result = result.sort_values("avg_wait_hours", ascending=False).reset_index(drop=True)

    # Label delay contribution based on relative position
    max_wait = result["avg_wait_hours"].max()
    min_wait = result["avg_wait_hours"].min()
    range_wait = max_wait - min_wait if max_wait != min_wait else 1.0

    def label(val):
        ratio = (val - min_wait) / range_wait
        if ratio >= 0.66:
            return "High"
        elif ratio >= 0.33:
            return "Medium"
        else:
            return "Low"

    result["delay_contribution"] = result["avg_wait_hours"].apply(label)
    result["avg_wait_hours"] = result["avg_wait_hours"].round(2)

    return result


def print_bottleneck_table(table: pd.DataFrame):
    """Pretty-print the bottleneck table."""
    print("=" * 75)
    print("  STEP 4 -- Bottleneck Analysis")
    print("=" * 75)
    print(
        f"  {'Activity':<30} {'Avg Wait (h)':>13} {'Rework Cases':>13} {'Delay':>8}"
    )
    print("  " + "-" * 70)
    for _, row in table.iterrows():
        print(
            f"  {row['activity']:<30} {row['avg_wait_hours']:>13.2f} "
            f"{row['times_repeated']:>13d} {row['delay_contribution']:>8}"
        )
    print("=" * 75)


def main():
    table = analyze_bottlenecks()
    print_bottleneck_table(table)
    return table


if __name__ == "__main__":
    main()
