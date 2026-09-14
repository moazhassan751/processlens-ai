"""
ProcessLens — Explain Router
================================
On-demand LLM case explanations (Phase 7 Feature 5).
Only called when user explicitly clicks "Explain Case".
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.config import OUTPUT_FILES
from backend.services import llm_service
from backend.services import storage as storage_svc

logger = logging.getLogger("processlens.explain")

router = APIRouter()


@router.post("/api/explain/case/{case_id}")
def explain_case(
    case_id: str,
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Optional run ID"),
):
    """
    Generate an explanation for a specific case's risk assessment.
    Uses LLM if available + under rate limit, otherwise deterministic fallback.
    Results are cached.
    """
    # Load predictions to find this case
    pred_path, is_pred_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "predictions")
    if not pred_path or not pred_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "predictions.json not found. Run the pipeline first.", "fallback": False},
        )

    try:
        with open(str(pred_path), encoding="utf-8") as f:
            all_cases = json.load(f)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": f"Failed to read predictions: {exc}"})

    # Find the specific case
    case_data = next((c for c in all_cases if c.get("case_id") == case_id), None)
    if case_data is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Case '{case_id}' not found in predictions."},
        )

    # Build compact structured facts
    risk_score = case_data.get("late_risk_probability")
    if risk_score is None:
        risk_score = case_data.get("risk_score", 0.0)
    risk_score = float(risk_score)
    predicted_label = case_data.get("predicted_label", "Unknown")
    anomaly = case_data.get("anomaly_flag", False)

    # Determine risk level from label
    if predicted_label == "Late Risk":
        risk_level = "HIGH" if risk_score > 0.7 else "MEDIUM"
    elif predicted_label == "On Track":
        risk_level = "LOW"
    else:
        risk_level = "UNKNOWN"

    # Compute activity durations from event log
    activities_completed = []
    total_duration_hours = 0
    current_activity = "Unknown"
    bottleneck_activity = None

    log_path, is_log_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "event_log")
    if log_path and log_path.exists():
        try:
            import pandas as pd
            df = pd.read_csv(str(log_path))
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            case_events = df[df["case_id"] == case_id].sort_values("timestamp")
            if not case_events.empty:
                activities_completed = case_events["activity"].tolist()
                current_activity = activities_completed[-1] if activities_completed else "Unknown"
                time_range = (case_events["timestamp"].max() - case_events["timestamp"].min())
                total_duration_hours = round(time_range.total_seconds() / 3600, 2)

                # Find bottleneck (longest wait between activities)
                case_events = case_events.copy()
                case_events["prev_ts"] = case_events["timestamp"].shift(1)
                case_events["wait"] = (case_events["timestamp"] - case_events["prev_ts"]).dt.total_seconds()
                waits = case_events.dropna(subset=["wait"])
                if not waits.empty:
                    bottleneck_idx = waits["wait"].idxmax()
                    bottleneck_activity = waits.loc[bottleneck_idx, "activity"]
        except Exception:
            pass

    # Build risk factors
    risk_factors = []
    if risk_score > 0.7:
        risk_factors.append(f"High risk score ({risk_score:.1%})")
    if anomaly:
        risk_factors.append("Flagged as anomaly by isolation forest")
    if case_data.get("elapsed_hours_so_far"):
        risk_factors.append(f"Elapsed time: {case_data['elapsed_hours_so_far']:.1f}h")
    if case_data.get("has_been_reworked_yet"):
        risk_factors.append("Case has experienced rework")

    case_facts = {
        "case_id": case_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "anomaly": anomaly,
        "total_duration_hours": total_duration_hours,
        "activities_completed": len(activities_completed),
        "current_activity": current_activity,
        "bottleneck_activity": bottleneck_activity,
        "risk_factors": risk_factors,
    }

    try:
        result = llm_service.explain_case(case_facts, run_id)
    except Exception as exc:
        logger.error("LLM explanation failed for case %s: %s; using deterministic fallback", case_id, exc)
        from backend.services.llm_service import _deterministic_case_explanation
        result = {
            "explanation": _deterministic_case_explanation(case_facts),
            "source": "fallback",
            "cached": False,
        }

    is_fallback = is_pred_fallback or (is_log_fallback if run_id else False)
    resp = {
        "case_id": case_id,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "anomaly": anomaly,
        "explanation": result["explanation"],
        "prescriptive_action": case_data.get("prescriptive_action"),
        "source": result["source"],
        "cached": result.get("cached", False),
        "fallback": is_fallback,
    }
    if is_fallback:
        resp["warning"] = storage_svc.FALLBACK_WARNING
    return resp
