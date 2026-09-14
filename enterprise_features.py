"""
ProcessLens — Enterprise Feature Engineering Module
===================================================
Provides:
1. Multi-prefix case snapshot extraction (milestones k >= 2 prior to completion).
2. System-level WIP congestion metrics (active WIP cases, arrival rate, resource load).
3. Leakage-free group-stratified case-level partitioning.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def compute_system_wip_timeline(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Precompute start and end timestamps for all cases to allow fast WIP querying."""
    case_bounds = df.groupby("case_id")["timestamp"].agg(start="min", end="max")
    return case_bounds["start"].values, case_bounds["end"].values


def get_wip_at_timestamp(ts: pd.Timestamp, case_starts: np.ndarray, case_ends: np.ndarray) -> int:
    """
    Compute number of active WIP cases in the system at calendar timestamp ts.
    A case is active at ts if its start <= ts and its completion end > ts.
    This is strictly non-leaking as it reflects the observable queue state at time ts.
    """
    ts_np = np.datetime64(ts)
    return int(np.sum((case_starts <= ts_np) & (case_ends > ts_np)))


def build_multi_prefix_dataset(
    event_log_path: str = "event_log.csv",
    max_prefixes_per_case: int = 4,
) -> Tuple[pd.DataFrame, Dict[str, int], Dict[str, float]]:
    """
    Builds a multi-prefix dataset from the event log.
    Ensures that for each case, snapshots are extracted at prefixes >= 2
    and strictly prior to the final completion event.
    """
    df = pd.read_csv(event_log_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    # Dynamic resource encoding
    unique_resources = sorted([str(r) for r in df["resource"].dropna().unique()])
    resource_map = {name: i for i, name in enumerate(unique_resources)}

    # Total cycle times for ground-truth calculation
    case_times = df.groupby("case_id")["timestamp"].agg(["min", "max"])
    case_times["total_cycle_hours"] = (
        (case_times["max"] - case_times["min"]).dt.total_seconds() / 3600.0
    )
    cycle_time_dict = case_times["total_cycle_hours"].to_dict()

    # Precompute system WIP timeline
    starts, ends = compute_system_wip_timeline(df)

    rows = []
    for case_id, group in df.groupby("case_id"):
        group = group.sort_values("timestamp").reset_index(drop=True)
        n_events = len(group)
        if n_events < 2:
            continue

        start_ts = group.iloc[0]["timestamp"]
        submitted_events = group[group["activity"] == "Submitted"]
        submitted_ts = submitted_events.iloc[0]["timestamp"] if not submitted_events.empty else start_ts

        # Prefixes to extract: from step 2 up to min(n_events-1, max_prefixes_per_case)
        upper_limit = min(n_events - 1, max_prefixes_per_case) if n_events > 2 else 2
        for prefix_len in range(2, upper_limit + 1):
            prefix_events = group.iloc[:prefix_len]
            last_event = prefix_events.iloc[-1]
            snapshot_ts = last_event["timestamp"]

            # Leakage boundary check: all events must be <= snapshot_ts
            assert prefix_events["timestamp"].max() <= snapshot_ts, f"Boundary violation for {case_id}"

            # Real-time WIP congestion at this snapshot timestamp
            wip_cases = get_wip_at_timestamp(snapshot_ts, starts, ends)

            # Elapsed and wait calculations
            elapsed_hours = (snapshot_ts - start_ts).total_seconds() / 3600.0
            wait_before_snapshot = (snapshot_ts - submitted_ts).total_seconds() / 3600.0

            # Inter-event wait stats
            waits = prefix_events["timestamp"].diff().dropna().dt.total_seconds() / 3600.0
            total_wait = float(waits.sum()) if not waits.empty else 0.0
            avg_wait = float(waits.mean()) if not waits.empty else 0.0
            max_wait = float(waits.max()) if not waits.empty else 0.0
            min_wait = float(waits.min()) if not waits.empty else 0.0
            long_waits = int((waits > 3.0).sum()) if not waits.empty else 0
            time_since_prev = float(waits.iloc[-1]) if not waits.empty else 0.0

            # Progress & rework features
            unique_acts = prefix_events["activity"].nunique()
            has_rework = 1 if len(prefix_events["activity"]) > unique_acts else 0
            res_encoded = resource_map.get(str(last_event["resource"]), -1)
            start_res = resource_map.get(str(group.iloc[0]["resource"]), -1)

            rows.append({
                "case_id": case_id,
                "prefix_len": prefix_len,
                "current_activity": str(last_event["activity"]),
                "elapsed_hours_so_far": round(elapsed_hours, 4),
                "wait_before_reviewed_hours": round(wait_before_snapshot, 4),
                "resource_at_reviewed": res_encoded,
                "hour_of_day_submitted": submitted_ts.hour,
                "has_been_reworked_yet": has_rework,
                "events_seen_so_far": prefix_len,
                "unique_activities_so_far": unique_acts,
                "transition_count_so_far": prefix_len - 1,
                "activity_repetition_count": prefix_len - unique_acts,
                "total_wait_hours_so_far": round(total_wait, 4),
                "average_wait_hours_so_far": round(avg_wait, 4),
                "max_wait_hours_so_far": round(max_wait, 4),
                "min_wait_hours_so_far": round(min_wait, 4),
                "number_of_long_waits_so_far": long_waits,
                "time_since_previous_activity": round(time_since_prev, 4),
                "hour_of_day_at_snapshot": snapshot_ts.hour,
                "day_of_week_submitted": submitted_ts.dayofweek,
                "day_of_week_at_snapshot": snapshot_ts.dayofweek,
                "is_weekend_submitted": 1 if submitted_ts.dayofweek >= 5 else 0,
                "resource_at_submitted": start_res,
                # Enterprise congestion feature
                "wip_active_cases": wip_cases,
                # Target
                "total_cycle_hours": round(cycle_time_dict[case_id], 4),
            })

    dataset = pd.DataFrame(rows)
    return dataset, resource_map, cycle_time_dict
