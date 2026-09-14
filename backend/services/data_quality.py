"""
ProcessLens — Data Quality Service
===================================
Computes defensible data-quality telemetry directly from the currently active event log.
No hard-coded values, no stale cache.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from backend.config import OUTPUT_FILES

logger = logging.getLogger("processlens.data_quality")


def compute_data_quality(event_log_path: Optional[Path] = None) -> dict:
    """
    Compute data quality telemetry from the specified or active event_log.csv.
    Returns:
      - case_count: int
      - event_count: int
      - date_range: {start, end, formatted, duration_days}
      - activity_count: int
      - activities: list[str]
      - rework_case_count: int
      - rework_case_pct: float (percentage of cases with rework)
      - avg_events_per_case: float
      - missing_values_count: int
      - is_valid: bool
    """
    p = event_log_path or OUTPUT_FILES["event_log"]
    if not p.exists() or p.stat().st_size == 0:
        return {
            "available": False,
            "case_count": 0,
            "event_count": 0,
            "date_range": None,
            "activity_count": 0,
            "activities": [],
            "rework_case_count": 0,
            "rework_case_pct": 0.0,
            "avg_events_per_case": 0.0,
            "missing_values_count": 0,
            "is_valid": False,
        }

    try:
        df = pd.read_csv(str(p))
        req_cols = {"case_id", "activity", "timestamp", "resource"}
        missing_cols = req_cols - set(df.columns)
        if missing_cols:
            return {
                "available": True,
                "is_valid": False,
                "error": f"Missing required columns: {', '.join(missing_cols)}",
                "case_count": 0,
                "event_count": len(df),
            }

        total_cases = int(df["case_id"].nunique())
        total_events = int(len(df))
        missing_vals = int(df[list(req_cols)].isna().sum().sum())

        df["parsed_ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
        valid_ts = df["parsed_ts"].dropna()

        if not valid_ts.empty:
            min_ts = valid_ts.min()
            max_ts = valid_ts.max()
            duration_days = round((max_ts - min_ts).total_seconds() / 86400.0, 1)
            date_range = {
                "start": min_ts.isoformat(),
                "end": max_ts.isoformat(),
                "formatted": f"{min_ts.strftime('%b %d, %Y')} – {max_ts.strftime('%b %d, %Y')}",
                "duration_days": duration_days,
            }
        else:
            date_range = {
                "start": None,
                "end": None,
                "formatted": "No valid timestamps",
                "duration_days": 0.0,
            }

        distinct_activities = sorted([str(a) for a in df["activity"].dropna().unique()])
        activity_count = len(distinct_activities)

        # Rework detection: cases with duplicated activities
        rework_case_count = 0
        for _, grp in df.groupby("case_id"):
            acts = grp["activity"].tolist()
            if len(acts) > len(set(acts)):
                rework_case_count += 1

        rework_pct = round(100.0 * rework_case_count / total_cases, 1) if total_cases > 0 else 0.0
        avg_events = round(total_events / total_cases, 1) if total_cases > 0 else 0.0

        return {
            "available": True,
            "case_count": total_cases,
            "event_count": total_events,
            "date_range": date_range,
            "activity_count": activity_count,
            "activities": distinct_activities,
            "rework_case_count": rework_case_count,
            "rework_case_pct": rework_pct,
            "avg_events_per_case": avg_events,
            "missing_values_count": missing_vals,
            "is_valid": True,
        }
    except Exception as exc:
        logger.exception(f"Error computing data quality: {exc}")
        return {
            "available": False,
            "error": str(exc),
            "case_count": 0,
            "event_count": 0,
            "is_valid": False,
        }
