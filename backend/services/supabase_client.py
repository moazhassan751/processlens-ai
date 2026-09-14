"""
ProcessLens — Supabase Client & CRUD Helpers
=============================================
Extracted from the original main.py. Provides Supabase initialization
and all persistence operations for pipeline runs and results.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from backend.config import SUPABASE_URL, SUPABASE_KEY, OUTPUT_FILES

logger = logging.getLogger("processlens.supabase")

# ---------------------------------------------------------------------------
# Client initialization
# ---------------------------------------------------------------------------

_sb = None


def init_supabase():
    """Initialize the Supabase client. Call once at startup."""
    global _sb
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            from supabase import create_client
            _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("Connected to %s", SUPABASE_URL)
        except Exception as exc:
            logger.warning("Supabase client init failed: %s", exc)
            _sb = None
    else:
        logger.info("SUPABASE_URL or SUPABASE_KEY not configured; running in local mode")


def get_client():
    """Return the Supabase client or None."""
    return _sb


# ---------------------------------------------------------------------------
# Pipeline Run CRUD
# ---------------------------------------------------------------------------


def create_pipeline_run(
    data_source: str,
    source_filename: Optional[str] = None,
    row_count: Optional[int] = None,
) -> Optional[str]:
    """Create a new record in pipeline_runs with status='running'."""
    if _sb is None:
        return None
    try:
        res = (
            _sb.table("pipeline_runs")
            .insert({
                "data_source": data_source,
                "source_filename": source_filename,
                "row_count": row_count,
                "status": "running",
                "failed_at_phase": None,
            })
            .execute()
        )
        if res.data and len(res.data) > 0:
            return str(res.data[0]["id"])
    except Exception as exc:
        logger.error("Failed to create pipeline_run: %s", exc)
    return None


def update_pipeline_run(
    run_id: Optional[str], status: str, failed_at_phase: Optional[str] = None
) -> None:
    """Update status and optional failed_at_phase of a pipeline run."""
    if _sb is None or not run_id:
        return
    try:
        payload = {"status": status}
        if failed_at_phase is not None:
            payload["failed_at_phase"] = failed_at_phase
        _sb.table("pipeline_runs").update(payload).eq("id", run_id).execute()
    except Exception as exc:
        logger.error("Failed to update pipeline_run %s: %s", run_id, exc)


# ---------------------------------------------------------------------------
# Child-table write helpers
# ---------------------------------------------------------------------------


def write_discovery_to_db(
    run_id: Optional[str],
    bottlenecks: list[dict],
    paths: list[str],
    process_map_exists: bool,
) -> None:
    if _sb is None or not run_id:
        return
    try:
        map_path = "process_map.png" if process_map_exists else None
        _sb.table("discovery_results").insert({
            "run_id": run_id,
            "bottleneck_table": bottlenecks,
            "discovered_paths": paths,
            "process_map_path": map_path,
        }).execute()
    except Exception as exc:
        logger.error("Failed to write discovery_results: %s", exc)


def write_prediction_to_db(
    run_id: Optional[str],
    pred_data: dict,
) -> None:
    if _sb is None or not run_id:
        return
    try:
        metrics = pred_data.get("model_metrics", {})
        _sb.table("prediction_results").insert({
            "run_id": run_id,
            "roc_auc": metrics.get("roc_auc"),
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            "f1": metrics.get("f1"),
            "feature_importances": pred_data.get("feature_importances"),
            "open_case_predictions": pred_data.get("open_cases"),
        }).execute()
    except Exception as exc:
        logger.error("Failed to write prediction_results: %s", exc)


def write_explanation_to_db(run_id: Optional[str]) -> None:
    if _sb is None or not run_id:
        return
    try:
        exp_path = OUTPUT_FILES["explanation_output"]
        if not exp_path.exists():
            return
        with open(str(exp_path), encoding="utf-8") as f:
            exp_data = json.load(f)

        findings = exp_data.get("investigator_findings")
        findings_json = {"text": findings} if isinstance(findings, str) else findings
        rec_text = exp_data.get("retry_recommendation") or exp_data.get("draft_recommendation")
        verifier_result = {
            "verification_result": exp_data.get("verification_result"),
            "retry_verification": exp_data.get("retry_verification"),
            "approved": exp_data.get("approved"),
        }
        rejection_occurred = bool(exp_data.get("retry_recommendation")) or (
            "REJECTED" in (exp_data.get("verification_result") or "")
        )
        rejection_reason = exp_data.get("verification_result") if rejection_occurred else None

        _sb.table("explanation_results").insert({
            "run_id": run_id,
            "investigator_findings": findings_json,
            "recommendation_text": rec_text,
            "verifier_result": verifier_result,
            "rejection_occurred": rejection_occurred,
            "rejection_reason": rejection_reason,
        }).execute()
    except Exception as exc:
        logger.error("Failed to write explanation_results: %s", exc)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_pipeline_runs(limit: int = 10) -> list[dict]:
    if _sb is None:
        return []
    try:
        res = (
            _sb.table("pipeline_runs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def get_run_details(run_id: str) -> Optional[dict]:
    """Fetch full run with all child tables."""
    if _sb is None:
        return None
    try:
        run_res = _sb.table("pipeline_runs").select("*").eq("id", run_id).execute()
        if not run_res.data:
            return None
        run_info = run_res.data[0]

        # Discovery
        disc_res = _sb.table("discovery_results").select("*").eq("run_id", run_id).execute()
        discovery_data = {"available": False, "bottlenecks": []}
        paths_data = {"available": False, "paths": []}
        if disc_res.data:
            d = disc_res.data[0]
            discovery_data = {
                "available": True,
                "process_map_exists": bool(d.get("process_map_path")),
                "bottlenecks": d.get("bottleneck_table") or [],
            }
            paths_data = {
                "available": True,
                "paths": d.get("discovered_paths") or [],
            }

        # Predictions
        pred_res = _sb.table("prediction_results").select("*").eq("run_id", run_id).execute()
        predictions_data = {"available": False}
        if pred_res.data:
            p = pred_res.data[0]
            open_cases = p.get("open_case_predictions") or []
            late_risk_count = sum(1 for c in open_cases if c.get("predicted_label") == "Late Risk")
            on_track_count = sum(1 for c in open_cases if c.get("predicted_label") == "On Track")
            insufficient_count = sum(1 for c in open_cases if c.get("predicted_label") == "Insufficient Data")
            anomaly_count = sum(1 for c in open_cases if c.get("anomaly_flag"))

            predictions_data = {
                "available": True,
                "summary": {
                    "late_risk_count": late_risk_count,
                    "on_track_count": on_track_count,
                    "insufficient_data_count": insufficient_count,
                    "anomaly_count": anomaly_count,
                    "total_cases": len(open_cases),
                },
                "model_metrics": {
                    "roc_auc": float(p["roc_auc"]) if p.get("roc_auc") is not None else 0.0,
                    "precision": float(p["precision"]) if p.get("precision") is not None else 0.0,
                    "recall": float(p["recall"]) if p.get("recall") is not None else 0.0,
                    "f1": float(p["f1"]) if p.get("f1") is not None else 0.0,
                },
                "feature_importances": p.get("feature_importances") or [],
                "open_cases": open_cases,
            }

        # Explanation
        exp_res = _sb.table("explanation_results").select("*").eq("run_id", run_id).execute()
        explanation_data = {"available": False}
        if exp_res.data:
            e = exp_res.data[0]
            v_res = e.get("verifier_result") or {}
            findings = e.get("investigator_findings")
            if isinstance(findings, dict) and "findings" in findings:
                findings_str = findings["findings"]
            elif isinstance(findings, dict) and "text" in findings:
                findings_str = findings["text"]
            else:
                findings_str = str(findings) if findings is not None else ""

            explanation_data = {
                "available": True,
                "investigator_findings": findings_str,
                "draft_recommendation": e.get("recommendation_text") or "",
                "verification_result": v_res.get("verification_result") or "",
                "retry_recommendation": (
                    e.get("recommendation_text") if e.get("rejection_occurred") else ""
                ),
                "retry_verification": v_res.get("retry_verification") or "",
                "approved": v_res.get("approved", not e.get("rejection_occurred")),
                "rejection_occurred": e.get("rejection_occurred", False),
                "rejection_reason": e.get("rejection_reason"),
            }

        return {
            "run": run_info,
            "discovery": discovery_data,
            "paths": paths_data,
            "predictions": predictions_data,
            "explanation": explanation_data,
        }
    except Exception as exc:
        logger.error("Failed to get run details: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Case explanation cache (Supabase)
# ---------------------------------------------------------------------------


def get_cached_explanation(cache_key: str) -> Optional[dict]:
    """Check Supabase for a cached case explanation."""
    if _sb is None:
        return None
    try:
        res = (
            _sb.table("case_explanations")
            .select("*")
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return None


def save_cached_explanation(
    case_id: str,
    run_id: Optional[str],
    cache_key: str,
    risk_score: Optional[float],
    risk_level: str,
    anomaly: bool,
    explanation: dict,
    source: str,
) -> None:
    """Persist a case explanation to Supabase cache."""
    if _sb is None:
        return
    try:
        _sb.table("case_explanations").upsert({
            "case_id": case_id,
            "run_id": run_id,
            "cache_key": cache_key,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "anomaly": anomaly,
            "explanation": explanation,
            "source": source,
        }, on_conflict="cache_key").execute()
    except Exception as exc:
        logger.error("Failed to cache explanation: %s", exc)
