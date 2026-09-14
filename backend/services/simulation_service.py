"""
ProcessLens — Simulation Service
===================================
Deterministic What-If Scenario Simulation engine (Phase F).
Evaluates the estimated operational impact of process interventions
(wait-time reductions, rework elimination, activity duration reductions,
and resource capacity scaling) against observed baseline event logs.

All calculations are 100% deterministic, reproducible, and mathematically traceable.
Zero LLM hallucination on numerical metrics.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from backend.config import OUTPUT_FILES
from backend.services.process_mining import compute_bottlenecks

logger = logging.getLogger("processlens.simulation")


def compute_simulation_baseline(event_log_path: Optional[Path] = None) -> dict[str, Any]:
    """
    Compute deterministic operational baseline from the active or specified event log.
    Extracts case-level cycle times, activity-level wait times, processing durations,
    rework loops, and identified process bottlenecks.
    """
    p = event_log_path or OUTPUT_FILES["event_log"]
    if not p.exists() or p.stat().st_size == 0:
        return {
            "available": False,
            "message": "Event log not yet available. Run the pipeline first.",
        }

    try:
        df = pd.read_csv(str(p))
        req_cols = {"case_id", "activity", "timestamp"}
        if not req_cols.issubset(df.columns):
            return {
                "available": False,
                "message": f"Event log missing required columns: {req_cols - set(df.columns)}",
            }

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

        case_count = int(df["case_id"].nunique())
        total_events = int(len(df))

        if case_count == 0:
            return {
                "available": False,
                "message": "Event log contains 0 cases.",
            }

        # 1. Case-level Cycle Time
        case_times = df.groupby("case_id")["timestamp"].agg(["min", "max"])
        case_cycle_hours = (case_times["max"] - case_times["min"]).dt.total_seconds() / 3600.0

        avg_cycle_time_hours = round(float(case_cycle_hours.mean()), 2)
        median_cycle_time_hours = round(float(case_cycle_hours.median()), 2)
        p75_cycle_time_hours = round(float(case_cycle_hours.quantile(0.75)), 2)

        # 2. Activity Wait Times (Handover delays leading into each event)
        df["prev_ts"] = df.groupby("case_id")["timestamp"].shift(1)
        df["wait_hours"] = (df["timestamp"] - df["prev_ts"]).dt.total_seconds() / 3600.0

        wait_stats = (
            df.dropna(subset=["wait_hours"])
            .groupby("activity")["wait_hours"]
            .agg(["mean", "median", "count"])
            .reset_index()
            .rename(columns={"mean": "avg_wait_hours", "median": "median_wait_hours", "count": "occurrence_count"})
        )
        wait_stats["avg_wait_hours"] = wait_stats["avg_wait_hours"].round(2)
        wait_stats["median_wait_hours"] = wait_stats["median_wait_hours"].round(2)

        # 3. Activity Processing Durations (Time from event to next event in case)
        df["next_ts"] = df.groupby("case_id")["timestamp"].shift(-1)
        df["duration_hours"] = (df["next_ts"] - df["timestamp"]).dt.total_seconds() / 3600.0

        duration_stats = (
            df.dropna(subset=["duration_hours"])
            .groupby("activity")["duration_hours"]
            .agg(["mean", "median"])
            .reset_index()
            .rename(columns={"mean": "avg_duration_hours", "median": "median_duration_hours"})
        )
        duration_stats["avg_duration_hours"] = duration_stats["avg_duration_hours"].round(2)
        duration_stats["median_duration_hours"] = duration_stats["median_duration_hours"].round(2)

        # 4. Rework repetition metrics
        activity_counts = df.groupby(["case_id", "activity"]).size().reset_index(name="count")
        rework = (
            activity_counts[activity_counts["count"] > 1]
            .groupby("activity")["case_id"]
            .nunique()
            .reset_index()
            .rename(columns={"case_id": "rework_cases"})
        )

        total_rework_cases = int(activity_counts[activity_counts["count"] > 1]["case_id"].nunique())
        rework_case_pct = round(100.0 * total_rework_cases / case_count, 1) if case_count > 0 else 0.0

        # Combine activity catalog (starting from all distinct activities)
        distinct_activities = pd.DataFrame({"activity": sorted(df["activity"].dropna().unique())})
        act_summary = (
            distinct_activities.merge(wait_stats, on="activity", how="left")
            .merge(duration_stats, on="activity", how="left")
            .merge(rework, on="activity", how="left")
        )
        act_summary["avg_wait_hours"] = act_summary["avg_wait_hours"].fillna(0.0)
        act_summary["median_wait_hours"] = act_summary["median_wait_hours"].fillna(0.0)
        act_summary["occurrence_count"] = act_summary["occurrence_count"].fillna(0).astype(int)
        act_summary["avg_duration_hours"] = act_summary["avg_duration_hours"].fillna(0.0)
        act_summary["median_duration_hours"] = act_summary["median_duration_hours"].fillna(0.0)
        act_summary["rework_cases"] = act_summary["rework_cases"].fillna(0).astype(int)

        activities_list = act_summary.to_dict(orient="records")

        # 5. Bottlenecks ranking (reuse existing process mining service)
        bottlenecks = compute_bottlenecks(p)
        primary_bottleneck = bottlenecks[0] if bottlenecks else None

        # 6. Resource catalog (if resource column exists)
        resources_list: list[dict[str, Any]] = []
        if "resource" in df.columns:
            res_stats = (
                df.dropna(subset=["resource"])
                .groupby("resource")
                .agg(event_count=("case_id", "count"), case_count=("case_id", "nunique"))
                .reset_index()
                .sort_values("event_count", ascending=False)
            )
            resources_list = res_stats.to_dict(orient="records")

        return {
            "available": True,
            "case_count": case_count,
            "event_count": total_events,
            "avg_cycle_time_hours": avg_cycle_time_hours,
            "median_cycle_time_hours": median_cycle_time_hours,
            "p75_cycle_time_hours": p75_cycle_time_hours,
            "rework_case_count": total_rework_cases,
            "rework_case_pct": rework_case_pct,
            "primary_bottleneck": primary_bottleneck,
            "bottlenecks": bottlenecks,
            "activities": activities_list,
            "resources": resources_list,
        }
    except Exception as exc:
        logger.exception(f"Failed to compute simulation baseline: {exc}")
        return {
            "available": False,
            "error": f"Failed to compute simulation baseline: {str(exc)}",
        }


def simulate_scenario(
    event_log_path: Optional[Path] = None,
    scenario_type: str = "bottleneck_wait_reduction",
    target_activity: Optional[str] = None,
    target_resource: Optional[str] = None,
    reduction_pct: float = 30.0,
    capacity_increase_pct: Optional[float] = None,
) -> dict[str, Any]:
    """
    Execute a deterministic What-If simulation scenario on the event log.

    Supported scenario types:
      1. 'bottleneck_wait_reduction' / 'activity_wait_reduction':
         Reduces observed handover wait times leading into target_activity by reduction_pct%.
      2. 'rework_reduction':
         Reduces observed rework loop delay (repeated occurrences of activity) by reduction_pct%.
      3. 'activity_duration_reduction':
         Reduces observed processing duration of target_activity by reduction_pct%.
      4. 'resource_capacity':
         Models capacity addition for target_resource under proportional throughput scaling.

    Returns deterministic baseline vs simulated comparison metrics.
    """
    p = event_log_path or OUTPUT_FILES["event_log"]
    if not p.exists() or p.stat().st_size == 0:
        return {
            "available": False,
            "message": "Simulation requires a completed process analysis. Run the pipeline first.",
        }

    # Input validations
    if reduction_pct <= 0.0 or reduction_pct > 100.0:
        raise ValueError("Reduction percentage must be between 0% (exclusive) and 100% (inclusive).")

    df = pd.read_csv(str(p))
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    available_activities = set(df["activity"].dropna().unique())

    if scenario_type in ["bottleneck_wait_reduction", "activity_wait_reduction", "activity_duration_reduction"]:
        if not target_activity:
            raise ValueError("Target activity is required for this scenario type.")
        if target_activity not in available_activities:
            raise ValueError(f"Selected activity '{target_activity}' does not exist in the active event log.")

    if scenario_type == "rework_reduction" and target_activity and target_activity != "all":
        if target_activity not in available_activities:
            raise ValueError(f"Selected activity '{target_activity}' does not exist in the active event log.")

    if scenario_type == "resource_capacity":
        if "resource" not in df.columns:
            raise ValueError("Resource capacity scenario requires a 'resource' column in the event log.")
        available_resources = set(df["resource"].dropna().unique())
        if target_resource and target_resource not in available_resources:
            raise ValueError(f"Selected resource '{target_resource}' does not exist in the active event log.")

    # Compute baseline metrics
    df["prev_ts"] = df.groupby("case_id")["timestamp"].shift(1)
    df["wait_hours"] = (df["timestamp"] - df["prev_ts"]).dt.total_seconds() / 3600.0

    df["next_ts"] = df.groupby("case_id")["timestamp"].shift(-1)
    df["duration_hours"] = (df["next_ts"] - df["timestamp"]).dt.total_seconds() / 3600.0

    # Mark occurrence index of each activity in each case (0 = first, 1+ = rework repetition)
    df["act_occurrence"] = df.groupby(["case_id", "activity"]).cumcount()

    case_times = df.groupby("case_id")["timestamp"].agg(["min", "max"])
    case_times["baseline_cycle_hours"] = (case_times["max"] - case_times["min"]).dt.total_seconds() / 3600.0
    case_map = case_times["baseline_cycle_hours"].to_dict()

    reduction_factor = reduction_pct / 100.0

    # Track case-level savings
    case_savings: dict[str, float] = {cid: 0.0 for cid in case_map}

    component_name = ""
    baseline_component_value = 0.0
    simulated_component_value = 0.0
    assumptions_text = ""
    scenario_title = ""
    calculation_basis: list[str] = []

    if scenario_type in ["bottleneck_wait_reduction", "activity_wait_reduction"]:
        scenario_title = f"{target_activity} Wait-Time Reduction (-{reduction_pct:.1f}%)"
        component_name = f"Avg Handover Wait Time for '{target_activity}'"

        target_waits = df[(df["activity"] == target_activity) & (df["wait_hours"].notna())]
        baseline_component_value = round(float(target_waits["wait_hours"].mean()), 2) if len(target_waits) > 0 else 0.0
        simulated_component_value = round(baseline_component_value * (1.0 - reduction_factor), 2)

        # For each case, compute sum of wait hours for target activity
        case_waits = target_waits.groupby("case_id")["wait_hours"].sum()
        for cid, w_sum in case_waits.items():
            case_savings[cid] = float(w_sum * reduction_factor)

        assumptions_text = (
            f"Assumes an operational improvement that reduces the handover waiting time "
            f"leading into activity '{target_activity}' by {reduction_pct:.1f}% across all case executions."
        )
        calculation_basis = [
            f"Baseline average wait time for '{target_activity}': {baseline_component_value:.2f} hours.",
            f"Applied intervention adjustment: {reduction_pct:.1f}% reduction factor.",
            f"Simulated average wait time for '{target_activity}': {simulated_component_value:.2f} hours.",
            f"Expected wait time reduction per instance: -{baseline_component_value - simulated_component_value:.2f} hours.",
            "Case cycle times recalculated by deducting the targeted wait savings from each observed case trace.",
        ]

    elif scenario_type == "rework_reduction":
        target_label = target_activity if (target_activity and target_activity != "all") else "all activities"
        scenario_title = f"Rework Delay Reduction on {target_label} (-{reduction_pct:.1f}%)"
        component_name = f"Rework Delay Hours ({target_label})"

        if target_activity and target_activity != "all":
            rework_rows = df[(df["activity"] == target_activity) & (df["act_occurrence"] > 0) & (df["wait_hours"].notna())]
        else:
            rework_rows = df[(df["act_occurrence"] > 0) & (df["wait_hours"].notna())]

        baseline_component_value = round(float(rework_rows["wait_hours"].sum()), 2) if len(rework_rows) > 0 else 0.0
        simulated_component_value = round(baseline_component_value * (1.0 - reduction_factor), 2)

        case_rework = rework_rows.groupby("case_id")["wait_hours"].sum()
        for cid, r_sum in case_rework.items():
            case_savings[cid] = float(r_sum * reduction_factor)

        assumptions_text = (
            f"Assumes quality control and first-time-right improvements that reduce the delay "
            f"incurred from repeated rework loops on {target_label} by {reduction_pct:.1f}%."
        )
        calculation_basis = [
            f"Baseline total rework delay across process instances: {baseline_component_value:.2f} hours.",
            f"Applied intervention adjustment: {reduction_pct:.1f}% reduction in rework loop time.",
            f"Simulated total rework delay: {simulated_component_value:.2f} hours.",
            f"Total operational hours saved across all rework cases: -{baseline_component_value - simulated_component_value:.2f} hours.",
            "Case cycle times recalculated by reducing loop repetition durations for affected cases.",
        ]

    elif scenario_type == "activity_duration_reduction":
        scenario_title = f"{target_activity} Processing Duration Reduction (-{reduction_pct:.1f}%)"
        component_name = f"Avg Execution Duration for '{target_activity}'"

        target_durations = df[(df["activity"] == target_activity) & (df["duration_hours"].notna())]
        baseline_component_value = round(float(target_durations["duration_hours"].mean()), 2) if len(target_durations) > 0 else 0.0
        simulated_component_value = round(baseline_component_value * (1.0 - reduction_factor), 2)

        case_durs = target_durations.groupby("case_id")["duration_hours"].sum()
        for cid, d_sum in case_durs.items():
            case_savings[cid] = float(d_sum * reduction_factor)

        assumptions_text = (
            f"Assumes task automation, tooling, or streamlined processing that reduces the active "
            f"duration of activity '{target_activity}' by {reduction_pct:.1f}%."
        )
        calculation_basis = [
            f"Baseline average execution duration for '{target_activity}': {baseline_component_value:.2f} hours.",
            f"Applied intervention adjustment: {reduction_pct:.1f}% duration reduction.",
            f"Simulated average execution duration: {simulated_component_value:.2f} hours.",
            f"Expected duration reduction per step: -{baseline_component_value - simulated_component_value:.2f} hours.",
            "Case cycle times recalculated by deducting execution time savings from each case.",
        ]

    elif scenario_type == "resource_capacity":
        cap_inc = float(capacity_increase_pct) if capacity_increase_pct is not None else float(reduction_pct)
        target_res = target_resource or "all resources"
        scenario_title = f"Resource Capacity Expansion (+{cap_inc:.1f}% on {target_res})"
        component_name = f"Handover Wait Time ({target_res})"

        # Proportional throughput scaling: W_sim = W_base / (1 + cap_inc / 100)
        scale_ratio = 1.0 / (1.0 + cap_inc / 100.0)
        eff_reduction_factor = 1.0 - scale_ratio

        if target_resource and target_resource != "all resources":
            res_rows = df[(df["resource"] == target_resource) & (df["wait_hours"].notna())]
        else:
            res_rows = df[df["wait_hours"].notna()]

        baseline_component_value = round(float(res_rows["wait_hours"].mean()), 2) if len(res_rows) > 0 else 0.0
        simulated_component_value = round(baseline_component_value * scale_ratio, 2)

        case_res_waits = res_rows.groupby("case_id")["wait_hours"].sum()
        for cid, rw_sum in case_res_waits.items():
            case_savings[cid] = float(rw_sum * eff_reduction_factor)

        assumptions_text = (
            f"Assumes a {cap_inc:.1f}% capacity or staffing expansion for {target_res}. "
            f"Under standard proportional service scaling, average wait times scale as W_base / (1 + ΔC). "
            f"No theoretical queue distribution is fabricated."
        )
        calculation_basis = [
            f"Baseline average wait time for {target_res}: {baseline_component_value:.2f} hours.",
            f"Added capacity assumption: +{cap_inc:.1f}% effective resource bandwidth.",
            f"Scaling multiplier: 1 / (1 + {cap_inc/100.0:.2f}) = {scale_ratio:.3f}.",
            f"Simulated average wait time: {simulated_component_value:.2f} hours.",
            f"Estimated wait time reduction: -{baseline_component_value - simulated_component_value:.2f} hours ({eff_reduction_factor * 100:.1f}%).",
        ]

    else:
        raise ValueError(f"Unknown scenario type: '{scenario_type}'.")

    # Compute baseline vs simulated aggregate cycle times
    baseline_cycle_times = list(case_map.values())
    simulated_cycle_times = [max(0.0, case_map[cid] - case_savings[cid]) for cid in case_map]

    total_cases = len(baseline_cycle_times)
    baseline_avg_cycle = round(float(np.mean(baseline_cycle_times)), 2) if total_cases > 0 else 0.0
    baseline_median_cycle = round(float(np.median(baseline_cycle_times)), 2) if total_cases > 0 else 0.0

    simulated_avg_cycle = round(float(np.mean(simulated_cycle_times)), 2) if total_cases > 0 else 0.0
    simulated_median_cycle = round(float(np.median(simulated_cycle_times)), 2) if total_cases > 0 else 0.0

    abs_reduction = round(baseline_avg_cycle - simulated_avg_cycle, 2)
    cycle_time_improvement_pct = round(100.0 * abs_reduction / baseline_avg_cycle, 1) if baseline_avg_cycle > 0 else 0.0
    component_reduction = round(baseline_component_value - simulated_component_value, 2)
    component_reduction_pct = round(100.0 * component_reduction / baseline_component_value, 1) if baseline_component_value > 0 else 0.0

    affected_cases = sum(1 for s in case_savings.values() if s > 0.0)

    # Plain-English deterministic summary
    explanation = (
        f"Under the selected assumption ({assumptions_text.strip()}), "
        f"the average cycle time is estimated to decrease from {baseline_avg_cycle:.2f}h to {simulated_avg_cycle:.2f}h, "
        f"representing an estimated improvement of {cycle_time_improvement_pct:.1f}% "
        f"(-{abs_reduction:.2f} hours saved per case on average across {affected_cases} affected cases)."
    )

    return {
        "available": True,
        "scenario": {
            "type": scenario_type,
            "title": scenario_title,
            "target_activity": target_activity,
            "target_resource": target_resource,
            "reduction_pct": reduction_pct,
            "capacity_increase_pct": capacity_increase_pct,
            "assumptions": assumptions_text,
            "calculation_basis": calculation_basis,
        },
        "baseline": {
            "case_count": total_cases,
            "avg_cycle_time_hours": baseline_avg_cycle,
            "median_cycle_time_hours": baseline_median_cycle,
            "component_name": component_name,
            "component_value": baseline_component_value,
        },
        "simulated": {
            "avg_cycle_time_hours": simulated_avg_cycle,
            "median_cycle_time_hours": simulated_median_cycle,
            "component_value": simulated_component_value,
            "affected_cases_count": affected_cases,
            "affected_cases_pct": round(100.0 * affected_cases / total_cases, 1) if total_cases > 0 else 0.0,
        },
        "impact": {
            "absolute_reduction_hours": abs_reduction,
            "cycle_time_improvement_pct": cycle_time_improvement_pct,
            "component_reduction_hours": component_reduction,
            "component_reduction_pct": component_reduction_pct,
        },
        "explanation": explanation,
    }
