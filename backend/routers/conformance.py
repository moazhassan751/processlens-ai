"""
ProcessLens — Conformance Router
==================================
Deterministic Process Conformance Checking (Phase E & Phase H7).
Computes alignments, trace-level fitness, and deviation diagnostics
against the normative (expected) reference process model.
Supports user-selectable reference variants discovered from the active event log.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from backend.config import OUTPUT_FILES
from backend.services.process_mining import compute_conformance, discover_variants
from backend.services import storage as storage_svc

logger = logging.getLogger("processlens.conformance")
router = APIRouter()


@router.get("/api/conformance/variants")
def get_conformance_variants(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
):
    """
    Return discovered process variants ranked deterministically by frequency.
    Used by frontend to inspect and select a custom reference variant for conformance checking.
    """
    event_log_path, is_log_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "event_log")

    if not event_log_path or not event_log_path.exists() or event_log_path.stat().st_size == 0:
        return JSONResponse(
            status_code=202,
            content={
                "available": False,
                "message": "event_log.csv not yet available. Run the pipeline or upload data first.",
                "variants": [],
                "fallback": False,
            },
        )

    variants = discover_variants(event_log_path)
    total_cases = sum(v["case_count"] for v in variants) if variants else 0
    default_var = next((v for v in variants if v.get("is_default")), variants[0] if variants else None)

    res = {
        "available": True,
        "total_cases": total_cases,
        "variant_count": len(variants),
        "default_variant_id": default_var["variant_id"] if default_var else None,
        "variants": variants,
        "fallback": is_log_fallback,
    }
    if is_log_fallback:
        res["warning"] = storage_svc.FALLBACK_WARNING
    return JSONResponse(status_code=200, content=res)


@router.get("/api/conformance")
def get_conformance(
    project_id: str = Query("default", description="Workspace project ID"),
    run_id: Optional[str] = Query(None, description="Specific run ID"),
    reference_variant: Optional[str] = Query(None, description="Optional variant ID or activity sequence"),
):
    """
    Return deterministic process conformance analysis.
    Evaluates observed cases against the normative expected process model.
    When reference_variant is omitted, uses the most frequent/dominant variant (backward compatible).
    When reference_variant is provided, validates existence against discovered variants and executes conformance.
    """
    clean_ref = reference_variant.strip() if reference_variant and reference_variant.strip() else None

    # 1. If no custom reference_variant is requested, check cached conformance output first
    if not clean_ref:
        cached_path, is_cached_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "conformance")
        if cached_path and cached_path.exists():
            try:
                with open(str(cached_path), encoding="utf-8") as f:
                    content = json.load(f)
                content["fallback"] = is_cached_fallback
                if is_cached_fallback:
                    content["warning"] = storage_svc.FALLBACK_WARNING

                # Populate reference_variant_id if missing from legacy cache
                ref_proc = content.get("reference_process", [])
                if ref_proc and "reference_variant_id" not in content:
                    content["reference_variant_id"] = (
                        "var_" + hashlib.sha256(" -> ".join(ref_proc).encode("utf-8")).hexdigest()[:12]
                    )
                return JSONResponse(status_code=200, content=content)
            except Exception as exc:
                logger.warning(f"Could not read cached conformance from {cached_path}: {exc}")

    # 2. Resolve event log path based on project / run isolation with fallback tracking
    event_log_path, is_log_fallback = storage_svc.resolve_artifact_path(project_id, run_id, "event_log")

    if not event_log_path or not event_log_path.exists() or event_log_path.stat().st_size == 0:
        return JSONResponse(
            status_code=202,
            content={
                "available": False,
                "message": "event_log.csv not yet available. Run the pipeline or upload data first.",
                "fallback": False,
            },
        )

    # 3. Discover available variants for validation & selection
    variants = discover_variants(event_log_path)
    ref_list: Optional[list[str]] = None
    selected_variant_id: Optional[str] = None

    if clean_ref:
        matched_variant = None
        for v in variants:
            # 1) Direct variant_id match (e.g. "var_7f8c12a0d9b4")
            if v["variant_id"] == clean_ref:
                matched_variant = v
                break
            # 2) Full activity sequence match (e.g. "Submitted -> Reviewed -> Approved -> Completed")
            if v["activity_sequence"] == clean_ref:
                matched_variant = v
                break
            # 3) Comma-separated match (e.g. "Submitted,Reviewed,Approved,Completed")
            if ",".join(v["activities"]) == clean_ref:
                matched_variant = v
                break
            # 4) Tokenized list equality
            if v["activities"] == [a.strip() for a in clean_ref.split(",") if a.strip()]:
                matched_variant = v
                break
            if v["activities"] == [a.strip() for a in clean_ref.split("->") if a.strip()]:
                matched_variant = v
                break

        if not matched_variant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reference_variant. The requested variant was not found in the discovered variants.",
            )

        ref_list = matched_variant["activities"]
        selected_variant_id = matched_variant["variant_id"]
    else:
        # Default: dominant clean or most frequent variant
        default_var = next((v for v in variants if v.get("is_default")), variants[0] if variants else None)
        if default_var:
            ref_list = default_var["activities"]
            selected_variant_id = default_var["variant_id"]

    # 4. Compute deterministic conformance
    try:
        results = compute_conformance(event_log_path, ref_list)
        if not results.get("available"):
            results["fallback"] = False
            return JSONResponse(status_code=202, content=results)

        if selected_variant_id:
            results["reference_variant_id"] = selected_variant_id

        results["fallback"] = is_log_fallback
        if is_log_fallback:
            results["warning"] = storage_svc.FALLBACK_WARNING
        return JSONResponse(status_code=200, content=results)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Conformance endpoint error: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "available": False,
                "error": f"Failed to compute process conformance: {str(exc)}",
            },
        )

