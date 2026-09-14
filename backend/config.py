"""
ProcessLens — Centralized Configuration
========================================
All paths, environment variables, constants, and feature flags.
"""

from __future__ import annotations

import os
from pathlib import Path

from typing import Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # d:\Process Lens
VENV_PYTHON = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    import sys
    VENV_PYTHON = Path(sys.executable)

STORAGE_ROOT = PROJECT_ROOT / "storage"

# Legacy flat-file paths (backward compat for live-run endpoints)
OUTPUT_FILES = {
    "event_log":          PROJECT_ROOT / "event_log.csv",
    "process_map":        PROJECT_ROOT / "process_map.png",
    "training_data":      PROJECT_ROOT / "training_data.csv",
    "delay_model":        PROJECT_ROOT / "delay_model.joblib",
    "anomaly_model":      PROJECT_ROOT / "anomaly_model.joblib",
    "open_cases":         PROJECT_ROOT / "open_cases.csv",
    "predictions":        PROJECT_ROOT / "predictions.json",
    "resource_mapping":   PROJECT_ROOT / "resource_mapping.json",
    "model_metrics":      PROJECT_ROOT / "model_metrics.json",
    "explanation_output": PROJECT_ROOT / "explanation_output.json",
    "conformance":        PROJECT_ROOT / "conformance.json",
    "enterprise_model_metrics": PROJECT_ROOT / "enterprise_model_metrics.json",
}

UPLOAD_STATE_FILE = PROJECT_ROOT / "upload_state.json"
EVENT_LOG_PREVIOUS = PROJECT_ROOT / "event_log_previous.csv"

REQUIRED_COLUMNS = {"case_id", "activity", "timestamp", "resource"}

PHASE_SCRIPTS = {
    "phase1": PROJECT_ROOT / "run_all.py",
    "phase2": PROJECT_ROOT / "run_phase2.py",
    "phase3": PROJECT_ROOT / "run_phase3.py",
}

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

load_dotenv(PROJECT_ROOT / ".env")

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# LLM Service
LLM_ENABLED = os.environ.get("LLM_ENABLED", "true").lower() in ("true", "1", "yes")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")  # "groq" or "gemini"
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-oss-20b")
LLM_MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "200"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "20"))
LLM_MAX_REQUESTS_PER_MINUTE = int(os.environ.get("LLM_MAX_REQUESTS_PER_MINUTE", "10"))
LLM_CACHE_ENABLED = os.environ.get("LLM_CACHE_ENABLED", "true").lower() in ("true", "1", "yes")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

# Graphviz
GRAPHVIZ_BIN = r"C:\Program Files\Graphviz\bin"

# Subprocess Timeouts (Phase A Robustness)
SUBPROCESS_TIMEOUT = int(os.environ.get("SUBPROCESS_TIMEOUT", "120"))
PHASE3_TIMEOUT = int(os.environ.get("PHASE3_TIMEOUT", "300"))

# API Key Protection (Phase H6)
API_KEY: Optional[str] = os.environ.get("API_KEY", "").strip() or None

