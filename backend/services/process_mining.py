"""
ProcessLens — Process Mining Service
======================================
Deterministic process analysis: bottlenecks, paths, and interactive graph.
No LLM calls — pure pandas/pm4py computation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from backend.config import OUTPUT_FILES, GRAPHVIZ_BIN

logger = logging.getLogger("processlens.process_mining")


def _ensure_graphviz():
    if os.path.isdir(GRAPHVIZ_BIN) and GRAPHVIZ_BIN not in os.environ.get("PATH", ""):
        os.environ["PATH"] = GRAPHVIZ_BIN + os.pathsep + os.environ.get("PATH", "")


def compute_bottlenecks(event_log_path: Optional[Path] = None) -> list[dict]:
    """Compute wait-time and rework metrics per activity."""
    p = event_log_path or OUTPUT_FILES["event_log"]
    if not p.exists():
        return []

    df = pd.read_csv(str(p))
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    df["prev_ts"] = df.groupby("case_id")["timestamp"].shift(1)
    df["wait_hours"] = (df["timestamp"] - df["prev_ts"]).dt.total_seconds() / 3600.0

    wait_stats = (
        df.dropna(subset=["wait_hours"])
        .groupby("activity")["wait_hours"]
        .mean()
        .reset_index()
        .rename(columns={"wait_hours": "avg_wait_hours"})
    )

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

    def label(val: float) -> str:
        ratio = (val - min_wait) / range_wait
        if ratio >= 0.66:
            return "High"
        elif ratio >= 0.33:
            return "Medium"
        return "Low"

    result["delay_contribution"] = result["avg_wait_hours"].apply(label)
    result["avg_wait_hours"] = result["avg_wait_hours"].round(2)
    return result.to_dict(orient="records")


def compute_paths(event_log_path: Optional[Path] = None) -> list[str]:
    """Discover process paths using pm4py Inductive Miner."""
    _ensure_graphviz()
    p = event_log_path or OUTPUT_FILES["event_log"]
    pm_path = OUTPUT_FILES.get("process_map")

    if not p.exists():
        return []
    if pm_path and not pm_path.exists():
        return []

    try:
        import pm4py

        df = pd.read_csv(str(p))
        df = df.rename(columns={
            "case_id": "case:concept:name",
            "activity": "concept:name",
            "timestamp": "time:timestamp",
            "resource": "org:resource",
        })
        df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])
        df = df.sort_values(["case:concept:name", "time:timestamp"])
        log = pm4py.format_dataframe(
            df, case_id="case:concept:name",
            activity_key="concept:name",
            timestamp_key="time:timestamp",
        )
        tree = pm4py.discover_process_tree_inductive(log)

        def extract(node, current=None):
            if current is None:
                current = []
            if node.label is not None:
                return [current + [node.label]]
            op = str(node.operator) if node.operator else "UNKNOWN"
            paths_out: list = []
            if op in ("SEQUENCE", "->"):
                combined = [current]
                for child in node.children:
                    new_combined: list = []
                    for px in combined:
                        new_combined.extend(extract(child, px))
                    combined = new_combined
                return combined
            elif op in ("XOR", "X"):
                for child in node.children:
                    paths_out.extend(extract(child, current))
                return paths_out
            elif op in ("PARALLEL", "+"):
                combined = [current]
                for child in node.children:
                    new_combined = []
                    for px in combined:
                        new_combined.extend(extract(child, px))
                    combined = new_combined
                return combined
            elif op in ("LOOP", "O", "*"):
                if len(node.children) >= 2:
                    body_paths = extract(node.children[0], [])
                    redo_paths = extract(node.children[1], [])
                    for bp in body_paths:
                        paths_out.append(current + bp)
                        for rp in redo_paths:
                            clean_rp = [a for a in rp if a is not None]
                            if clean_rp:
                                paths_out.append(current + bp + clean_rp + bp)
                else:
                    return extract(node.children[0], current)
                return paths_out
            else:
                for child in node.children:
                    paths_out.extend(extract(child, current))
                return paths_out

        all_paths = extract(tree)
        seen: set = set()
        path_strings: list[str] = []
        for path in all_paths:
            clean = [a for a in path if a is not None]
            if not clean:
                continue
            key = tuple(clean)
            if key in seen:
                continue
            seen.add(key)
            path_strings.append(" -> ".join(clean))
        return path_strings
    except Exception as exc:
        return [f"(Could not extract paths: {exc})"]


def compute_process_graph(event_log_path: Optional[Path] = None) -> dict:
    """
    Compute an interactive process graph with node/edge statistics.
    Pure pandas — no LLM.
    
    Returns:
        {
            "nodes": [{"id", "label", "frequency", "avg_duration_hours", "median_duration_hours", "is_bottleneck"}],
            "edges": [{"source", "target", "frequency", "avg_duration_hours", "median_duration_hours", "is_bottleneck"}]
        }
    """
    p = event_log_path or OUTPUT_FILES["event_log"]
    if not p.exists():
        return {"nodes": [], "edges": []}

    df = pd.read_csv(str(p))
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    # --- Node stats: frequency = number of times each activity appears ---
    activity_freq = df.groupby("activity")["case_id"].nunique().reset_index()
    activity_freq.columns = ["activity", "frequency"]

    # Activity-level durations: how long cases spend *at* this activity
    # (time from this event to the next event in the same case)
    df["next_ts"] = df.groupby("case_id")["timestamp"].shift(-1)
    df["duration_hours"] = (df["next_ts"] - df["timestamp"]).dt.total_seconds() / 3600.0

    activity_dur = (
        df.dropna(subset=["duration_hours"])
        .groupby("activity")["duration_hours"]
        .agg(["mean", "median"])
        .reset_index()
        .rename(columns={"mean": "avg_duration_hours", "median": "median_duration_hours"})
    )

    node_df = activity_freq.merge(activity_dur, on="activity", how="left").fillna(0)

    # --- Edge stats: transition frequencies and durations ---
    df["next_activity"] = df.groupby("case_id")["activity"].shift(-1)
    transitions = df.dropna(subset=["next_activity"]).copy()
    transitions["transition_hours"] = (
        (transitions["next_ts"] - transitions["timestamp"]).dt.total_seconds() / 3600.0
    )

    edge_stats = (
        transitions.groupby(["activity", "next_activity"])
        .agg(
            frequency=("case_id", "count"),
            avg_duration_hours=("transition_hours", "mean"),
            median_duration_hours=("transition_hours", "median"),
        )
        .reset_index()
    )

    # Identify bottleneck edge (highest avg duration)
    bottleneck_threshold = 0.0
    if len(edge_stats) > 0:
        bottleneck_threshold = edge_stats["avg_duration_hours"].quantile(0.75)

    nodes = []
    for _, row in node_df.iterrows():
        nodes.append({
            "id": row["activity"],
            "label": row["activity"],
            "frequency": int(row["frequency"]),
            "avg_duration_hours": round(float(row["avg_duration_hours"]), 2),
            "median_duration_hours": round(float(row["median_duration_hours"]), 2),
            "is_bottleneck": False,
        })

    # Identify reference variant transitions
    case_traces = df.sort_values(["case_id", "timestamp"]).groupby("case_id")["activity"].agg(list)
    variant_counts = case_traces.apply(tuple).value_counts()
    ref_edges: set[tuple[str, str]] = set()
    if not variant_counts.empty:
        clean_variants = [v for v in variant_counts.index if len(v) == len(set(v))]
        ref_var = clean_variants[0] if clean_variants else variant_counts.index[0]
        for idx in range(len(ref_var) - 1):
            ref_edges.add((str(ref_var[idx]), str(ref_var[idx + 1])))

    edges = []
    for _, row in edge_stats.iterrows():
        s = str(row["activity"])
        t = str(row["next_activity"])
        is_bn = bool(float(row["avg_duration_hours"]) >= bottleneck_threshold and bottleneck_threshold > 0)
        is_ref = (s, t) in ref_edges
        edges.append({
            "source": s,
            "target": t,
            "frequency": int(row["frequency"]),
            "avg_duration_hours": round(float(row["avg_duration_hours"]), 2),
            "median_duration_hours": round(float(row["median_duration_hours"]), 2),
            "is_bottleneck": is_bn,
            "is_conforming": is_ref,
            "is_deviating": not is_ref,
        })

    # Mark bottleneck nodes (nodes at either end of a bottleneck edge)
    bn_nodes = set()
    for e in edges:
        if e["is_bottleneck"]:
            bn_nodes.add(e["source"])
            bn_nodes.add(e["target"])
    for n in nodes:
        if n["id"] in bn_nodes:
            n["is_bottleneck"] = True

    return {"nodes": nodes, "edges": edges}


def discover_variants(event_log_path: Optional[Path] = None) -> list[dict]:
    """
    Discover all unique process variants from the event log ranked deterministically by frequency.

    Returns:
        List of dicts:
        [
            {
                "variant_id": str,          # Deterministic SHA-256 slug "var_xxxxxxxxxxxx"
                "activities": list[str],    # List of activities in execution order
                "activity_sequence": str,   # Human-readable "Act1 -> Act2 -> Act3"
                "case_count": int,          # Number of cases following this exact variant
                "percentage": float,        # Percentage of total cases (0.0 to 100.0)
                "rank": int,                # 1-based frequency ranking (1 = highest frequency)
                "is_default": bool,         # True if this is the dominant clean/most frequent variant
            },
            ...
        ]
    """
    p = event_log_path or OUTPUT_FILES["event_log"]
    if not p.exists() or p.stat().st_size == 0:
        return []

    try:
        df = pd.read_csv(str(p))
        if df.empty or "case_id" not in df.columns or "activity" not in df.columns or "timestamp" not in df.columns:
            return []

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

        case_traces = df.groupby("case_id")["activity"].agg(tuple)
        total_cases = len(case_traces)
        if total_cases == 0:
            return []

        counts = case_traces.value_counts()
        # Deterministic sort: primarily by case_count descending, secondarily by activity tuple ascending
        sorted_tuples = sorted(counts.index, key=lambda t: (-counts[t], t))

        # Default variant rule: clean variant without duplicate steps if available, else highest frequency
        clean_candidates = [t for t in sorted_tuples if len(t) == len(set(t))]
        default_tuple = clean_candidates[0] if clean_candidates else sorted_tuples[0]

        variants = []
        for idx, t in enumerate(sorted_tuples, start=1):
            act_list = list(t)
            seq_str = " -> ".join(act_list)
            cnt = int(counts[t])
            pct = round((cnt / total_cases) * 100.0, 2)
            var_id = "var_" + hashlib.sha256(seq_str.encode("utf-8")).hexdigest()[:12]
            variants.append({
                "variant_id": var_id,
                "activities": act_list,
                "activity_sequence": seq_str,
                "case_count": cnt,
                "percentage": pct,
                "rank": idx,
                "is_default": (t == default_tuple),
            })

        return variants
    except Exception as exc:
        logger.error(f"Failed to discover variants: {exc}")
        return []


def compute_conformance(
    event_log_path: Optional[Path] = None,
    reference_variant: Optional[list[str] | tuple[str, ...]] = None,
) -> dict:
    """
    Perform deterministic process conformance checking using PM4Py alignments
    and token-based replay against the normative (expected) reference process.

    Returns:
        {
            "available": bool,
            "reference_process": list[str],
            "summary": {
                "total_cases": int,
                "conforming_cases": int,
                "deviating_cases": int,
                "conformance_rate_pct": float,
                "average_trace_fitness": float,
                "log_fitness": float,
            },
            "top_deviations": list[dict],
            "case_deviations": list[dict],
            "transition_deviations": dict[str, int],  # "A -> B": count
        }
    """
    p = event_log_path or OUTPUT_FILES["event_log"]
    if not p.exists() or p.stat().st_size == 0:
        return {
            "available": False,
            "reference_process": [],
            "summary": {
                "total_cases": 0,
                "conforming_cases": 0,
                "deviating_cases": 0,
                "conformance_rate_pct": 0.0,
                "average_trace_fitness": 0.0,
                "log_fitness": 0.0,
            },
            "top_deviations": [],
            "case_deviations": [],
            "transition_deviations": {},
        }

    try:
        import pm4py

        df = pd.read_csv(str(p))
        if df.empty or "case_id" not in df.columns or "activity" not in df.columns or "timestamp" not in df.columns:
            return {
                "available": False,
                "error": "Event log is missing required columns (case_id, activity, timestamp).",
                "reference_process": [],
                "summary": {"total_cases": 0, "conforming_cases": 0, "deviating_cases": 0, "conformance_rate_pct": 0.0},
                "top_deviations": [],
                "case_deviations": [],
                "transition_deviations": {},
            }

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

        case_groups = df.groupby("case_id")
        case_traces = case_groups["activity"].agg(list)
        variant_counts = case_traces.apply(tuple).value_counts()

        if variant_counts.empty:
            return {"available": False, "error": "No valid case traces found."}

        # 1. Determine Normative Reference Process
        ref_variant: tuple[str, ...]
        if reference_variant:
            ref_variant = tuple(reference_variant)
        else:
            # Pick the most frequent variant with no internal duplicate steps (clean happy path)
            clean_variants = [v for v in variant_counts.index if len(v) == len(set(v))]
            if clean_variants:
                ref_variant = clean_variants[0]
            else:
                ref_variant = variant_counts.index[0]

        reference_process = list(ref_variant)
        ref_set = set(reference_process)

        # 2. Build Reference Process Petri Net
        ref_records = [
            {
                "case_id": "REF-CASE",
                "activity": act,
                "timestamp": pd.Timestamp("2026-01-01 00:00:00") + pd.Timedelta(seconds=idx * 60),
                "resource": "SYSTEM",
            }
            for idx, act in enumerate(reference_process)
        ]
        ref_df = pd.DataFrame(ref_records)
        ref_pm_df = ref_df.rename(columns={
            "case_id": "case:concept:name",
            "activity": "concept:name",
            "timestamp": "time:timestamp",
        })
        ref_log = pm4py.convert_to_event_log(
            pm4py.format_dataframe(ref_pm_df, case_id="case:concept:name", activity_key="concept:name", timestamp_key="time:timestamp")
        )
        net, im, fm = pm4py.discover_petri_net_inductive(ref_log)

        # 3. Format Full Event Log for PM4Py
        full_pm_df = df.rename(columns={
            "case_id": "case:concept:name",
            "activity": "concept:name",
            "timestamp": "time:timestamp",
            "resource": "org:resource",
        })
        full_log = pm4py.convert_to_event_log(
            pm4py.format_dataframe(full_pm_df, case_id="case:concept:name", activity_key="concept:name", timestamp_key="time:timestamp")
        )

        # 4. Compute Alignments and Token-Based Replay
        alignments = pm4py.conformance_diagnostics_alignments(full_log, net, im, fm)
        tbr_fitness = pm4py.fitness_token_based_replay(full_log, net, im, fm)

        total_cases = len(full_log)
        conforming_count = 0
        case_deviations: list[dict] = []
        pattern_aggregates: dict[str, dict] = {}
        transition_deviations: dict[str, int] = {}

        for idx, (trace, align) in enumerate(zip(full_log, alignments)):
            case_id = str(trace.attributes.get("concept:name", f"CASE-{idx+1}"))
            observed_path = [str(event.get("concept:name", "")) for event in trace]
            moves = align.get("alignment", [])
            fitness = round(float(align.get("fitness", 0.0)), 4)

            # Analyze alignment moves
            is_conforming = True
            mismatches: list[dict] = []
            deviations: list[dict] = []
            seen_activities: set[str] = set()

            prev_observed = None

            for log_move, model_move in moves:
                if log_move == model_move:
                    mismatches.append({"log": log_move, "model": model_move, "type": "sync"})
                    seen_activities.add(log_move)
                    prev_observed = log_move
                elif log_move != ">>" and model_move == ">>":
                    # Log move: activity executed in log but not expected by reference model
                    is_conforming = False
                    if observed_path.count(log_move) > 1 or log_move in seen_activities:
                        dev_type = "Rework Loop"
                    elif log_move not in ref_set:
                        dev_type = "Unplanned Activity"
                    else:
                        dev_type = "Out-of-Sequence Activity"
                    trans = f"{prev_observed} -> {log_move}" if prev_observed else f"Initial -> {log_move}"
                    transition_deviations[trans] = transition_deviations.get(trans, 0) + 1

                    desc = (
                        f"Repeated execution of '{log_move}' (rework loop)"
                        if dev_type == "Rework Loop"
                        else f"Unexpected execution of '{log_move}'"
                    )

                    deviations.append({
                        "type": dev_type,
                        "activity": log_move,
                        "transition": trans,
                        "description": desc,
                    })
                    mismatches.append({"log": log_move, "model": ">>", "type": "log_move", "category": dev_type})
                    seen_activities.add(log_move)
                    prev_observed = log_move
                elif log_move == ">>" and model_move != ">>":
                    # Model move: expected by model, skipped in trace
                    is_conforming = False
                    dev_type = "Skipped Activity"
                    trans = f"Skipped {model_move}"
                    transition_deviations[trans] = transition_deviations.get(trans, 0) + 1

                    deviations.append({
                        "type": dev_type,
                        "activity": model_move,
                        "transition": trans,
                        "description": f"Required process milestone '{model_move}' was skipped",
                    })
                    mismatches.append({"log": ">>", "model": model_move, "type": "model_move", "category": dev_type})

            if is_conforming:
                conforming_count += 1
                explanation = (
                    f"Case {case_id} is 100% conforming with the expected process. "
                    f"Followed exact sequence: {' -> '.join(reference_process)}."
                )
            else:
                # Deterministic plain-English synthesis
                dev_summaries = []
                for d in deviations:
                    dev_summaries.append(f"{d['type']} at '{d['activity']}'")
                explanation = (
                    f"Case {case_id} deviated from the reference process (fitness: {fitness * 100:.1f}%). "
                    f"Detected {len(deviations)} deviation(s): {', '.join(dev_summaries)}."
                )

                # Aggregate by deviation pattern
                pattern_key = " -> ".join([d["transition"] for d in deviations])
                if pattern_key not in pattern_aggregates:
                    pattern_aggregates[pattern_key] = {
                        "pattern": pattern_key,
                        "deviation_type": deviations[0]["type"] if deviations else "Deviation",
                        "affected_cases": 0,
                        "affected_activities": sorted(list({d["activity"] for d in deviations})),
                        "affected_transitions": list({d["transition"] for d in deviations}),
                        "description": deviations[0]["description"] if deviations else "",
                    }
                pattern_aggregates[pattern_key]["affected_cases"] += 1

            case_deviations.append({
                "case_id": case_id,
                "is_conforming": is_conforming,
                "fitness": fitness,
                "observed_path": observed_path,
                "expected_path": reference_process,
                "mismatch_count": len(deviations),
                "deviation_types": sorted(list({d["type"] for d in deviations})),
                "affected_activities": sorted(list({d["activity"] for d in deviations})),
                "affected_transitions": [d["transition"] for d in deviations],
                "alignment_moves": mismatches,
                "explanation": explanation,
            })

        deviating_count = total_cases - conforming_count
        conformance_rate = round(100.0 * conforming_count / total_cases, 1) if total_cases > 0 else 0.0
        avg_fitness = round(float(tbr_fitness.get("average_trace_fitness", 0.0)), 4)
        log_fitness = round(float(tbr_fitness.get("log_fitness", 0.0)), 4)

        # Format top deviations ranked by frequency
        top_deviations = sorted(pattern_aggregates.values(), key=lambda x: x["affected_cases"], reverse=True)
        for td in top_deviations:
            td["affected_pct"] = round(100.0 * td["affected_cases"] / total_cases, 1) if total_cases > 0 else 0.0

        ref_var_id = "var_" + hashlib.sha256(" -> ".join(reference_process).encode("utf-8")).hexdigest()[:12]

        return {
            "available": True,
            "reference_process": reference_process,
            "reference_variant_id": ref_var_id,
            "summary": {
                "total_cases": total_cases,
                "conforming_cases": conforming_count,
                "deviating_cases": deviating_count,
                "conformance_rate_pct": conformance_rate,
                "average_trace_fitness": avg_fitness,
                "log_fitness": log_fitness,
            },
            "top_deviations": top_deviations,
            "case_deviations": case_deviations,
            "transition_deviations": transition_deviations,
        }
    except Exception as exc:
        logger.exception(f"Error computing process conformance: {exc}")
        return {
            "available": False,
            "error": str(exc),
            "reference_process": [],
            "summary": {
                "total_cases": 0,
                "conforming_cases": 0,
                "deviating_cases": 0,
                "conformance_rate_pct": 0.0,
                "average_trace_fitness": 0.0,
                "log_fitness": 0.0,
            },
            "top_deviations": [],
            "case_deviations": [],
            "transition_deviations": {},
        }

