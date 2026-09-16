"""
ProcessLens — LLM Service
===========================
Centralized LLM gateway with cache, rate limiting, and deterministic fallback.
The rest of the app never touches the LLM SDK directly.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
import logging
from typing import Optional

import httpx

from backend.config import (
    LLM_ENABLED, LLM_PROVIDER, LLM_MODEL,
    LLM_MAX_OUTPUT_TOKENS, LLM_TEMPERATURE, LLM_TIMEOUT,
    LLM_MAX_REQUESTS_PER_MINUTE, LLM_CACHE_ENABLED,
    GROQ_API_KEY, GROQ_BASE_URL, GEMINI_API_KEY,
)
from backend.services import supabase_client as sb

logger = logging.getLogger("processlens.llm")

# ---------------------------------------------------------------------------
# In-memory cache + rate limiter
# ---------------------------------------------------------------------------

_mem_cache: dict[str, dict] = {}
_request_times: deque = deque()

SYSTEM_PROMPT = (
    "You are a process-analysis assistant.\n"
    "Explain analytical results clearly, professionally, and concisely.\n"
    "Use only the supplied structured evidence. Do not invent facts.\n"
    "Explicitly differentiate between immediate remediation (what to do now) "
    "and root cause prevention (how to prevent it from happening again).\n"
    'Return valid JSON: {\n'
    '  "summary": "Clear executive summary of root-cause risk diagnosis",\n'
    '  "evidence": ["Specific data point 1", "Specific data point 2"],\n'
    '  "what_to_do": "Immediate tactical remediation steps to expedite or unblock this case",\n'
    '  "how_to_prevent": "Preventative process controls, SLA thresholds, and validation rules to stop recurrence",\n'
    '  "recommendation": "Comprehensive combined operational recommendation"\n'
    '}'
)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _get_cache_key(facts: dict) -> str:
    """SHA256 hash of the relevant case facts."""
    canonical = json.dumps(facts, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _check_cache(key: str) -> Optional[dict]:
    """Check in-memory cache, then Supabase."""
    if not LLM_CACHE_ENABLED:
        return None
    if key in _mem_cache:
        return _mem_cache[key]
    # Check Supabase
    result = sb.get_cached_explanation(key)
    if result:
        _mem_cache[key] = result
        return result
    return None


def _store_cache(key: str, data: dict) -> None:
    if LLM_CACHE_ENABLED:
        _mem_cache[key] = data


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


def _check_rate_limit() -> bool:
    """Return True if we're under the rate limit."""
    now = time.time()
    # Remove old entries
    while _request_times and _request_times[0] < now - 60:
        _request_times.popleft()
    return len(_request_times) < LLM_MAX_REQUESTS_PER_MINUTE


def _record_request():
    _request_times.append(time.time())


# ---------------------------------------------------------------------------
# LLM callers
# ---------------------------------------------------------------------------


def _call_groq(prompt: str) -> Optional[dict]:
    """Call Groq API (OpenAI-compatible)."""
    if not GROQ_API_KEY:
        return None
    try:
        timeout = httpx.Timeout(LLM_TIMEOUT, connect=5.0)
        resp = httpx.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": LLM_MAX_OUTPUT_TOKENS,
                "temperature": LLM_TEMPERATURE,
                "response_format": {"type": "json_object"},
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            logger.warning("Groq API returned HTTP %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Groq API error: %s", exc)
    return None


def _call_gemini(prompt: str) -> Optional[dict]:
    """Call Gemini API as fallback."""
    if not GEMINI_API_KEY:
        return None
    try:
        timeout = httpx.Timeout(LLM_TIMEOUT, connect=5.0)
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            params={"key": GEMINI_API_KEY},
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]}],
                "generationConfig": {
                    "maxOutputTokens": LLM_MAX_OUTPUT_TOKENS,
                    "temperature": LLM_TEMPERATURE,
                    "responseMimeType": "application/json",
                },
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        else:
            logger.warning("Gemini API returned HTTP %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Gemini API error: %s", exc)
    return None


def _call_llm(prompt: str) -> Optional[dict]:
    """Unified LLM caller: tries primary, then fallback."""
    _record_request()
    if LLM_PROVIDER == "groq":
        result = _call_groq(prompt)
        if result:
            return result
        return _call_gemini(prompt)
    else:
        result = _call_gemini(prompt)
        if result:
            return result
        return _call_groq(prompt)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_case_prompt(facts: dict) -> str:
    """Build a compact prompt for case explanation (~100 tokens input)."""
    return (
        "Explain this process case risk assessment.\n"
        f"Case: {facts.get('case_id', '?')}\n"
        f"Risk Score: {facts.get('risk_score', '?')}\n"
        f"Risk Level: {facts.get('risk_level', '?')}\n"
        f"Anomaly: {'Yes' if facts.get('anomaly') else 'No'}\n"
        f"Total Duration: {facts.get('total_duration_hours', '?')} hours\n"
        f"Activities Completed: {facts.get('activities_completed', '?')}\n"
        f"Current Activity: {facts.get('current_activity', '?')}\n"
        f"Risk Factors: {json.dumps(facts.get('risk_factors', []))}\n"
        f"Bottleneck Activity: {facts.get('bottleneck_activity', 'None')}"
    )


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _deterministic_case_explanation(facts: dict) -> dict:
    """Generate a template-based explanation from structured facts."""
    risk_level = facts.get("risk_level", "UNKNOWN")
    risk_score = facts.get("risk_score", 0)
    anomaly = facts.get("anomaly", False)
    duration = facts.get("total_duration_hours", 0)
    current = facts.get("current_activity", "unknown")
    factors = facts.get("risk_factors", [])
    bottleneck = facts.get("bottleneck_activity", None)

    evidence = []

    if risk_score is not None:
        evidence.append(f"Risk score: {risk_score:.1%}")
    if duration:
        evidence.append(f"Total elapsed time: {duration:.1f} hours")
    if current:
        evidence.append(f"Currently at: {current}")
    if anomaly:
        evidence.append("Flagged as statistical anomaly by isolation forest")
    if bottleneck:
        evidence.append(f"Passed through bottleneck activity: {bottleneck}")
    for f in factors[:3]:
        evidence.append(f"Risk factor: {f}")

    if risk_level == "HIGH" or (risk_score and risk_score > 0.7):
        summary = (
            f"Case {facts.get('case_id', '?')} is classified as HIGH RISK "
            f"with a delay probability of {risk_score:.1%}. "
            f"The case has been in process for {duration:.1f} hours "
            f"and is currently held at '{current}'."
        )
        if anomaly:
            summary += " Additionally, the case exhibits anomalous execution patterns flagging irregular cycle behavior."
        what_to_do = (
            f"Immediately escalate Case {facts.get('case_id', '?')} to the lead reviewer for priority handling. "
            f"Expedite queue handover at '{current}' and conduct a fast-track compliance verification."
        )
        how_to_prevent = (
            f"Set up an automated 24-hour SLA alert on activity '{current}'. "
            f"Enforce mandatory input checklist validation at intake to eliminate downstream handoff stalls and rework cycles."
        )
        recommendation = f"{what_to_do} {how_to_prevent}"
    elif risk_level == "MEDIUM" or (risk_score and risk_score > 0.4):
        summary = (
            f"Case {facts.get('case_id', '?')} presents a MODERATE risk level "
            f"(delay probability: {risk_score:.1%}). "
            f"Currently active at '{current}' after {duration:.1f} hours of elapsed execution time."
        )
        what_to_do = (
            f"Queue Case {facts.get('case_id', '?')} for proactive inspection before the next batch cycle. "
            f"Verify that all handover requirements for '{current}' are satisfied."
        )
        how_to_prevent = (
            f"Monitor queue depth for '{current}' and redistribute workload if active resource queue exceeds 5 pending cases."
        )
        recommendation = f"{what_to_do} {how_to_prevent}"
    else:
        summary = (
            f"Case {facts.get('case_id', '?')} is proceeding ON TRACK "
            f"with a minimal delay probability of {risk_score:.1%}. "
            f"Current milestone: '{current}' after {duration:.1f} hours."
        )
        what_to_do = "No intervention required. Allow standard automated workflow progression."
        how_to_prevent = "Maintain standard automated SLA tracking and periodic batch status synchronization."
        recommendation = "No intervention required. This case is proceeding normally within established operational benchmarks."

    return {
        "summary": summary,
        "evidence": evidence,
        "what_to_do": what_to_do,
        "how_to_prevent": how_to_prevent,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def explain_case(case_facts: dict, run_id: Optional[str] = None) -> dict:
    """
    Generate or retrieve a cached explanation for a process case.
    
    Returns:
        {
            "explanation": {"summary": ..., "evidence": [...], "recommendation": ...},
            "source": "llm" | "fallback",
            "cached": bool,
        }
    """
    cache_key = _get_cache_key(case_facts)

    # 1. Check cache
    cached = _check_cache(cache_key)
    if cached:
        return {
            "explanation": cached.get("explanation", cached),
            "source": cached.get("source", "fallback"),
            "cached": True,
        }

    # 2. Try LLM if enabled and under rate limit
    source = "fallback"
    explanation = None

    if LLM_ENABLED and _check_rate_limit():
        prompt = _build_case_prompt(case_facts)
        try:
            result = _call_llm(prompt)
            if result and isinstance(result, dict) and "summary" in result:
                what_to_do = result.get("what_to_do")
                how_to_prevent = result.get("how_to_prevent")
                rec = result.get("recommendation", "")
                if not what_to_do and rec:
                    what_to_do = rec
                if not how_to_prevent and rec:
                    how_to_prevent = "Enforce automated stage SLA limits and intake validation to prevent recurrence."
                explanation = {
                    "summary": result["summary"],
                    "evidence": result.get("evidence", []),
                    "what_to_do": what_to_do or "Prioritize case for expedited review.",
                    "how_to_prevent": how_to_prevent or "Enforce automated stage SLA limits and intake validation.",
                    "recommendation": rec or f"{what_to_do} {how_to_prevent}",
                }
                source = "llm"
        except Exception as exc:
            logger.warning("Error calling LLM: %s", exc)

    # 3. Fallback
    if explanation is None:
        explanation = _deterministic_case_explanation(case_facts)
        source = "fallback"

    # 4. Cache result
    result_data = {
        "explanation": explanation,
        "source": source,
    }
    _store_cache(cache_key, result_data)

    # Persist to Supabase (best effort)
    try:
        sb.save_cached_explanation(
            case_id=case_facts.get("case_id", "?"),
            run_id=run_id,
            cache_key=cache_key,
            risk_score=case_facts.get("risk_score"),
            risk_level=case_facts.get("risk_level", "UNKNOWN"),
            anomaly=case_facts.get("anomaly", False),
            explanation=explanation,
            source=source,
        )
    except Exception as exc:
        logger.warning("Failed to save cached explanation to Supabase: %s", exc)

    return {
        "explanation": explanation,
        "source": source,
        "cached": False,
    }
