"""
ProcessLens — Snapshot Service
================================
Dynamic snapshot selection for feature engineering.
Allows users to choose which activity to use as the observation point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from backend.config import OUTPUT_FILES


def get_available_activities(event_log_path: Optional[Path] = None) -> list[dict]:
    """
    Return all unique activities from the event log with coverage stats.
    Sorted by position in the typical process flow (order of first appearance).
    """
    p = event_log_path or OUTPUT_FILES["event_log"]
    if not p.exists():
        return []

    df = pd.read_csv(str(p))
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    total_cases = df["case_id"].nunique()

    # Determine order by first appearance across all cases
    first_appearance = (
        df.sort_values("timestamp")
        .groupby("activity")["timestamp"]
        .first()
        .sort_values()
    )

    activities = []
    for idx, (activity, _) in enumerate(first_appearance.items()):
        cases_with = df[df["activity"] == activity]["case_id"].nunique()
        coverage_pct = round(100.0 * cases_with / total_cases, 1) if total_cases > 0 else 0.0
        is_last = (idx == len(first_appearance) - 1)
        activities.append({
            "activity": activity,
            "order": idx,
            "case_count": cases_with,
            "total_cases": total_cases,
            "coverage_pct": coverage_pct,
            "is_last": is_last,
            "suitable_for_snapshot": not is_last and coverage_pct >= 10.0,
        })

    return activities


def validate_snapshot_activity(
    activity: str,
    event_log_path: Optional[Path] = None,
) -> dict:
    """Validate that the activity is suitable as a snapshot milestone."""
    available = get_available_activities(event_log_path)
    if not available:
        return {
            "valid": False,
            "activity": activity,
            "error": "No event log found or it is empty.",
        }

    match = next((a for a in available if a["activity"] == activity), None)
    if not match:
        names = [a["activity"] for a in available]
        return {
            "valid": False,
            "activity": activity,
            "error": f"Activity '{activity}' not found. Available: {', '.join(names)}",
        }

    warnings = []
    if match["is_last"]:
        return {
            "valid": False,
            "activity": activity,
            "error": "Cannot use the last activity in the process as a snapshot — no open cases would remain for prediction.",
        }

    if match["coverage_pct"] < 10.0:
        warnings.append(
            f"Low coverage: only {match['coverage_pct']}% of cases reach '{activity}'. "
            f"Predictions may not generalize well."
        )

    if match["coverage_pct"] < 30.0:
        warnings.append(
            f"Moderate coverage: {match['coverage_pct']}% of cases reach '{activity}'. "
            f"Consider an earlier activity for broader coverage."
        )

    return {
        "valid": True,
        "activity": activity,
        "case_coverage_pct": match["coverage_pct"],
        "total_cases": match["total_cases"],
        "cases_with_activity": match["case_count"],
        "warnings": warnings,
    }
