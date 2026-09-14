"""
Phase 3 -- MCP Tool Server for ProcessLens.

Exposes four tools that read directly from event_log.csv and predictions.json
(always fresh from disk, never cached):

  1. get_step_stats       -- bottleneck table
  2. compare_by_resource  -- resource breakdown for a given activity
  3. get_rework_cases     -- rework rate, trigger, and cost
  4. get_prediction_summary -- Phase 2 prediction counts
"""

import json
import os
import sys
import pandas as pd
from mcp.server.fastmcp import FastMCP

# Create server
mcp = FastMCP("ProcessLens Tools")

# Resolve file paths relative to this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EVENT_LOG = os.path.join(SCRIPT_DIR, "event_log.csv")
PREDICTIONS = os.path.join(SCRIPT_DIR, "predictions.json")


def _load_event_log():
    """Load event_log.csv fresh from disk every time."""
    return pd.read_csv(EVENT_LOG, parse_dates=["timestamp"])


def _load_predictions():
    """Load predictions.json fresh from disk every time."""
    with open(PREDICTIONS, "r", encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def get_step_stats() -> str:
    """
    Returns the bottleneck table: for each activity, the average wait time
    (hours before it starts), how many cases repeat it (rework indicator),
    and a delay contribution label (High/Medium/Low).

    Returns JSON with a list of activity stats sorted by avg_wait_hours descending.
    """
    df = _load_event_log()
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    # Average wait time per activity
    df["prev_ts"] = df.groupby("case_id")["timestamp"].shift(1)
    df["wait_hours"] = (df["timestamp"] - df["prev_ts"]).dt.total_seconds() / 3600.0

    wait_stats = (
        df.dropna(subset=["wait_hours"])
        .groupby("activity")["wait_hours"]
        .mean()
        .reset_index()
        .rename(columns={"wait_hours": "avg_wait_hours"})
    )

    # Rework: cases where an activity appears more than once
    activity_counts = df.groupby(["case_id", "activity"]).size().reset_index(name="count")
    rework = (
        activity_counts[activity_counts["count"] > 1]
        .groupby("activity")["case_id"]
        .nunique()
        .reset_index()
        .rename(columns={"case_id": "times_repeated"})
    )

    result = wait_stats.merge(rework, on="activity", how="left")
    result["times_repeated"] = result["times_repeated"].fillna(0).astype(int)
    result = result.sort_values("avg_wait_hours", ascending=False).reset_index(drop=True)

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
    return json.dumps(result.to_dict(orient="records"), indent=2)


@mcp.tool()
def compare_by_resource(activity_name: str) -> str:
    """
    For a specific activity, returns average wait time and case count
    broken down by resource. Answers: 'is one reviewer slower than another?'

    Args:
        activity_name: The activity to analyze (e.g. 'Approved', 'Reviewed').

    Returns JSON with per-resource stats for the given activity.
    """
    df = _load_event_log()
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    # Compute wait time for each event
    df["prev_ts"] = df.groupby("case_id")["timestamp"].shift(1)
    df["wait_hours"] = (df["timestamp"] - df["prev_ts"]).dt.total_seconds() / 3600.0

    # Filter to the requested activity
    filtered = df[df["activity"] == activity_name].dropna(subset=["wait_hours"])

    if filtered.empty:
        return json.dumps({
            "activity": activity_name,
            "error": f"No data found for activity '{activity_name}'",
            "resources": [],
        })

    resource_stats = (
        filtered.groupby("resource")
        .agg(
            avg_wait_hours=("wait_hours", "mean"),
            case_count=("case_id", "nunique"),
        )
        .reset_index()
        .sort_values("avg_wait_hours", ascending=False)
    )
    resource_stats["avg_wait_hours"] = resource_stats["avg_wait_hours"].round(2)

    return json.dumps({
        "activity": activity_name,
        "resources": resource_stats.to_dict(orient="records"),
    }, indent=2)


@mcp.tool()
def get_rework_cases() -> str:
    """
    Returns rework statistics: total rework rate, which activity most commonly
    triggers rework, and an estimate of total extra hours added by rework
    (difference in average cycle time between reworked and non-reworked cases).

    Returns JSON with rework analysis.
    """
    df = _load_event_log()
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    total_cases = df["case_id"].nunique()

    # Find cases with repeated activities (rework indicator)
    activity_counts = df.groupby(["case_id", "activity"]).size().reset_index(name="count")
    rework_events = activity_counts[activity_counts["count"] > 1]
    rework_case_ids = set(rework_events["case_id"].unique())
    rework_count = len(rework_case_ids)
    rework_rate = round(rework_count / total_cases * 100, 1) if total_cases > 0 else 0

    # Which activity triggers rework most
    if not rework_events.empty:
        trigger_activity = (
            rework_events.groupby("activity")["case_id"]
            .nunique()
            .idxmax()
        )
        trigger_count = int(
            rework_events.groupby("activity")["case_id"].nunique().max()
        )
    else:
        trigger_activity = "None"
        trigger_count = 0

    # Estimate extra hours from rework
    case_times = df.groupby("case_id")["timestamp"].agg(["min", "max"])
    case_times["cycle_hours"] = (
        (case_times["max"] - case_times["min"]).dt.total_seconds() / 3600.0
    )

    rework_mask = case_times.index.isin(rework_case_ids)
    avg_rework = round(case_times.loc[rework_mask, "cycle_hours"].mean(), 2)
    avg_normal = round(case_times.loc[~rework_mask, "cycle_hours"].mean(), 2)
    extra_hours_per_case = round(avg_rework - avg_normal, 2)
    total_extra_hours = round(extra_hours_per_case * rework_count, 2)

    return json.dumps({
        "total_cases": total_cases,
        "rework_cases": rework_count,
        "rework_rate_pct": rework_rate,
        "most_common_rework_activity": trigger_activity,
        "most_common_rework_count": trigger_count,
        "avg_cycle_hours_reworked": avg_rework,
        "avg_cycle_hours_normal": avg_normal,
        "extra_hours_per_reworked_case": extra_hours_per_case,
        "total_extra_hours_from_rework": total_extra_hours,
    }, indent=2)


@mcp.tool()
def get_prediction_summary() -> str:
    """
    Reads predictions.json from Phase 2 and returns counts of
    Late Risk / On Track / Insufficient Data predictions, plus the
    average late-risk probability among flagged cases.

    Returns JSON with prediction summary.
    """
    predictions = _load_predictions()

    counts = {"Late Risk": 0, "On Track": 0, "Insufficient Data": 0}
    late_probs = []

    for p in predictions:
        label = p.get("predicted_label", "Unknown")
        counts[label] = counts.get(label, 0) + 1
        if label == "Late Risk" and p.get("late_risk_probability") is not None:
            late_probs.append(p["late_risk_probability"])

    avg_late_prob = round(sum(late_probs) / len(late_probs), 4) if late_probs else None

    return json.dumps({
        "total_open_cases": len(predictions),
        "late_risk_count": counts.get("Late Risk", 0),
        "on_track_count": counts.get("On Track", 0),
        "insufficient_data_count": counts.get("Insufficient Data", 0),
        "avg_late_risk_probability": avg_late_prob,
        "late_risk_cases": [
            p["case_id"]
            for p in predictions
            if p.get("predicted_label") == "Late Risk"
        ],
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
