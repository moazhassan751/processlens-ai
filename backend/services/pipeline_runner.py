"""
ProcessLens — Async Pipeline Runner
=====================================
Background subprocess execution with log capture, explicit timeouts,
SSE streaming, and complete project/run isolation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.config import (
    VENV_PYTHON, PROJECT_ROOT, PHASE_SCRIPTS, GRAPHVIZ_BIN,
    SUBPROCESS_TIMEOUT, PHASE3_TIMEOUT, OUTPUT_FILES,
)
from backend.models import RunStatusEnum
from backend.services import storage as storage_svc
from backend.services import supabase_client as sb
from backend.services.process_mining import compute_bottlenecks, compute_paths, compute_conformance
from backend.services.ml_service import compute_prediction_data

logger = logging.getLogger("processlens.pipeline")


# ---------------------------------------------------------------------------
# Status definitions & In-memory run registry (Phase H4 Concurrency Guard)
# ---------------------------------------------------------------------------

BLOCKING_STATUSES = {RunStatusEnum.RUNNING, RunStatusEnum.QUEUED}
BLOCKING_STATUS_STRINGS = {"RUNNING", "QUEUED"}
TERMINAL_STATUSES = {RunStatusEnum.COMPLETED, RunStatusEnum.FAILED, RunStatusEnum.CANCELLED}
TERMINAL_STATUS_STRINGS = {"COMPLETED", "FAILED", "CANCELLED"}

# Process-level concurrency synchronization lock
_run_lock = threading.Lock()


class PipelineRun:
    """Tracks a single background pipeline execution."""

    def __init__(self, run_id: str, project_id: str, snapshot_activity: str = "Reviewed"):
        self.run_id = run_id
        self.project_id = project_id
        self.snapshot_activity = snapshot_activity
        self.status = RunStatusEnum.QUEUED
        self.progress = 0
        self.current_stage: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.error_message: Optional[str] = None
        self.pipeline_run_id: Optional[str] = None  # Supabase UUID
        self.log_lines: deque[dict] = deque(maxlen=5000)
        self._subscribers: list[asyncio.Queue] = []

    def add_log(self, line: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = {"timestamp": ts, "line": line, "level": level}
        self.log_lines.append(entry)
        for q in self._subscribers:
            try:
                q.put_nowait(("log", entry))
            except asyncio.QueueFull:
                pass

    def notify_status(self):
        data = {
            "status": self.status.value,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "run_id": self.run_id,
            "error_message": self.error_message,
        }
        for q in self._subscribers:
            try:
                q.put_nowait(("status", data))
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "snapshot_activity": self.snapshot_activity,
        }


# Global registry of active/recent runs
_runs: dict[str, PipelineRun] = {}


def get_run(run_id: str) -> Optional[PipelineRun]:
    return _runs.get(run_id)


def get_active_run_for_project(project_id: str) -> Optional[tuple[str, str]]:
    """
    Check if a project already has any run with status RUNNING or QUEUED.
    Returns (run_id, status_string) if a blocking run exists, else None.
    Checks in-memory registry first, then persisted storage metadata.
    """
    # 1. In-memory registry check (active processes in this server)
    for run in _runs.values():
        if run.project_id == project_id:
            if run.status in BLOCKING_STATUSES:
                return (run.run_id, run.status.value)

    # 2. Persisted storage check (for controlled test setups or persisted state)
    try:
        persisted_runs = storage_svc.list_runs(project_id)
        for meta in persisted_runs:
            status_val = str(meta.get("status", "")).upper()
            if status_val in BLOCKING_STATUS_STRINGS:
                run_id = meta.get("run_id")
                # If this run exists in memory, verify memory status hasn't completed
                if run_id and run_id in _runs:
                    mem_run = _runs[run_id]
                    if mem_run.status in BLOCKING_STATUSES:
                        return (run_id, mem_run.status.value)
                elif run_id:
                    return (run_id, status_val)
    except Exception as exc:
        logger.warning(f"Error checking persisted runs for project {project_id}: {exc}")

    return None


def create_run_guarded(
    project_id: str = "default",
    snapshot_activity: str = "Reviewed",
) -> tuple[Optional[PipelineRun], Optional[str]]:
    """
    Atomically check for existing active/queued runs for project_id and create a new run if clear.
    Returns:
        (run: PipelineRun, conflict_run_id: None) if successful.
        (None, conflict_run_id: str) if a blocking run (RUNNING or QUEUED) already exists.
    """
    with _run_lock:
        active = get_active_run_for_project(project_id)
        if active is not None:
            conflict_run_id, status_str = active
            logger.warning(
                f"Concurrent run rejected for project '{project_id}': existing run '{conflict_run_id}' has status '{status_str}'."
            )
            return (None, conflict_run_id)

        # No blocking run -> create and register new run atomically
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        run = PipelineRun(run_id, project_id, snapshot_activity)
        _runs[run_id] = run
        logger.info(f"Registered run {run_id} for project {project_id}")
        return (run, None)


def create_run(project_id: str = "default", snapshot_activity: str = "Reviewed") -> PipelineRun:
    """Creates and registers a run directly (under lock)."""
    with _run_lock:
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        run = PipelineRun(run_id, project_id, snapshot_activity)
        _runs[run_id] = run
        logger.info(f"Registered run {run_id} for project {project_id}")
        return run


# ---------------------------------------------------------------------------
# Phase execution & Subprocess Robustness
# ---------------------------------------------------------------------------

PHASE_NAMES = {
    "phase1": "Discovery & Process Mining",
    "phase2": "ML Prediction Pipeline",
    "phase3": "Agentic Recommendation",
}

PHASE_PROGRESS = {
    "phase1": (0, 33),
    "phase2": (33, 66),
    "phase3": (66, 100),
}


def _check_insufficient_data(event_log_path: Path) -> tuple[bool, int]:
    """Check if event log has fewer than 10 cases. Returns (is_insufficient: bool, count: int)."""
    try:
        if not event_log_path.exists() or event_log_path.stat().st_size == 0:
            return True, 0
        import pandas as pd
        df = pd.read_csv(str(event_log_path))
        if df.empty or "case_id" not in df.columns:
            return True, 0
        count = int(df["case_id"].dropna().nunique())
        return count < 10, count
    except Exception as exc:
        logger.warning(f"Error checking case count in {event_log_path}: {exc}")
        return True, 0


import subprocess

async def _run_script_async(
    script: Path,
    run: PipelineRun,
    phase: str,
    work_dir: Path,
    extra_args: Optional[list[str]] = None,
) -> bool:
    """
    Run a Python script as a subprocess inside work_dir.
    Features:
      - Explicit timeout with process termination
      - Non-zero exit code capture
      - Exception handling without exposing raw stack traces
      - Streaming stdout/stderr (compatible across all platforms and Windows event loops)
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["CREWAI_TRACING_ENABLED"] = "false"
    env["CREWAI_TELEMETRY_OPT_OUT"] = "true"
    env["OTEL_SDK_DISABLED"] = "true"
    if os.path.isdir(GRAPHVIZ_BIN) and GRAPHVIZ_BIN not in env.get("PATH", ""):
        env["PATH"] = GRAPHVIZ_BIN + os.pathsep + env.get("PATH", "")

    cmd = [str(VENV_PYTHON), str(script)]
    if extra_args:
        cmd.extend(extra_args)
    elif script.name == "run_phase3.py":
        cmd.append("--fast")

    start_prog, end_prog = PHASE_PROGRESS.get(phase, (0, 100))
    timeout = PHASE3_TIMEOUT if phase == "phase3" else SUBPROCESS_TIMEOUT

    loop = asyncio.get_running_loop()

    def run_process_sync():
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(work_dir),
                env=env,
                text=True,
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError as fnf:
            return False, f"Python executable or script not found: {fnf}"
        except Exception as exc:
            return False, f"Failed to spawn subprocess {script.name}: {exc}"

        def reader(pipe, level):
            try:
                for line in iter(pipe.readline, ""):
                    text = line.rstrip()
                    if text:
                        loop.call_soon_threadsafe(run.add_log, text, level)
            except Exception:
                pass
            finally:
                pipe.close()

        t_out = threading.Thread(target=reader, args=(proc.stdout, "info"), daemon=True)
        t_err = threading.Thread(target=reader, args=(proc.stderr, "error"), daemon=True)
        t_out.start()
        t_err.start()

        try:
            retcode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.error(f"Process {script.name} in phase {phase} timed out after {timeout} seconds")
            try:
                proc.kill()
            except Exception:
                pass
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            return False, f"Phase {phase} timed out after {timeout} seconds"

        t_out.join(timeout=2)
        t_err.join(timeout=2)

        if retcode != 0:
            return False, f"Process {script.name} exited with non-zero exit code {retcode}"

        return True, None

    try:
        success, err_msg = await asyncio.to_thread(run_process_sync)
    except Exception as exc:
        logger.exception(f"Unexpected error while executing {script.name}: {exc}")
        err_msg = f"Unexpected error in {script.name}: {exc}"
        run.add_log(err_msg, "error")
        run.error_message = err_msg
        return False

    if not success:
        logger.warning(err_msg)
        run.add_log(err_msg, "error")
        run.error_message = err_msg
        return False

    run.progress = end_prog
    run.notify_status()
    return True


async def run_all_phases(run: PipelineRun) -> None:
    """Execute phases 1–3 in background with full isolation, updating run state."""
    run.status = RunStatusEnum.RUNNING
    run.started_at = datetime.now(timezone.utc).isoformat()
    run.notify_status()

    # 1. Setup isolated storage directory & input event log
    run_dir = storage_svc.create_run_dir(run.project_id, run.run_id)
    event_log_path = storage_svc.setup_run_input(run.project_id, run.run_id)

    upload_state = _read_upload_state()
    data_source = upload_state.get("source", "synthetic")
    source_filename = upload_state.get("filename") if data_source == "uploaded" else None
    row_count = upload_state.get("row_count") if data_source == "uploaded" else _get_row_count(event_log_path)

    # 2. Check Insufficient Data protection (< 10 cases)
    if event_log_path.exists() and data_source == "uploaded":
        is_insufficient, case_count = _check_insufficient_data(event_log_path)
        if is_insufficient:
            err_msg = (
                f"Insufficient data: event log contains only {case_count} case(s). "
                f"At least 10 cases are required for process mining and predictive analysis."
            )
            logger.warning(f"Run {run.run_id} aborted: {err_msg}")
            run.status = RunStatusEnum.FAILED
            run.error_message = err_msg
            run.completed_at = datetime.now(timezone.utc).isoformat()
            run.add_log(err_msg, "error")
            run.notify_status()
            storage_svc.save_run_metadata(
                run.project_id, run.run_id,
                status="FAILED", failed_at_phase="insufficient_data",
                completed_at=run.completed_at, error_message=err_msg,
            )
            return

    # 3. Create Supabase pipeline_run record
    run.pipeline_run_id = sb.create_pipeline_run(data_source, source_filename, row_count)

    storage_svc.save_run_metadata(
        run.project_id, run.run_id,
        status="RUNNING",
        created_at=run.created_at,
        started_at=run.started_at,
        data_source=data_source,
        source_filename=source_filename,
        row_count=row_count,
        snapshot_activity=run.snapshot_activity,
        pipeline_run_id=run.pipeline_run_id,
    )

    phases = [
        ("phase1", PHASE_SCRIPTS["phase1"]),
        ("phase2", PHASE_SCRIPTS["phase2"]),
        ("phase3", PHASE_SCRIPTS["phase3"]),
    ]

    for phase_name, script in phases:
        run.current_stage = PHASE_NAMES.get(phase_name, phase_name)
        run.add_log(f"Starting {run.current_stage}...")
        run.notify_status()

        # If data is uploaded, skip synthetic data generation in phase 1
        if phase_name == "phase1" and data_source == "uploaded":
            # Execute validation, discovery, and bottlenecks on uploaded log
            sub_scripts = [
                PROJECT_ROOT / "validate_data.py",
                PROJECT_ROOT / "discover_process.py",
                PROJECT_ROOT / "bottlenecks.py",
            ]
            phase_success = True
            for sub_script in sub_scripts:
                if not await _run_script_async(sub_script, run, phase_name, run_dir):
                    phase_success = False
                    break
        else:
            phase_success = await _run_script_async(script, run, phase_name, run_dir)

        if not phase_success:
            run.status = RunStatusEnum.FAILED
            if not run.error_message:
                run.error_message = f"Failed at {phase_name}"
            run.completed_at = datetime.now(timezone.utc).isoformat()
            run.add_log(f"FAILED at {phase_name}: {run.error_message}", "error")
            run.notify_status()
            sb.update_pipeline_run(run.pipeline_run_id, "failed", phase_name)
            storage_svc.save_run_metadata(
                run.project_id, run.run_id,
                status="FAILED", failed_at_phase=phase_name,
                completed_at=run.completed_at, error_message=run.error_message,
            )
            return

        # Check Insufficient Data after synthetic generation in phase 1
        if phase_name == "phase1":
            is_insufficient, case_count = _check_insufficient_data(run_dir / "event_log.csv")
            if is_insufficient:
                err_msg = (
                    f"Insufficient data: event log contains only {case_count} case(s). "
                    f"At least 10 cases are required for process mining and predictive analysis."
                )
                logger.warning(f"Run {run.run_id} aborted after phase 1: {err_msg}")
                run.status = RunStatusEnum.FAILED
                run.error_message = err_msg
                run.completed_at = datetime.now(timezone.utc).isoformat()
                run.add_log(err_msg, "error")
                run.notify_status()
                sb.update_pipeline_run(run.pipeline_run_id, "failed", "insufficient_data")
                storage_svc.save_run_metadata(
                    run.project_id, run.run_id,
                    status="FAILED", failed_at_phase="insufficient_data",
                    completed_at=run.completed_at, error_message=err_msg,
                )
                return

        # For phase 1, compute deterministic conformance before organizing outputs
        if phase_name == "phase1":
            try:
                conformance_res = compute_conformance(run_dir / "event_log.csv")
                with open(str(run_dir / "conformance.json"), "w", encoding="utf-8") as f:
                    json.dump(conformance_res, f, indent=2)
            except Exception as conf_exc:
                logger.warning(f"Failed to generate conformance during run {run.run_id}: {conf_exc}")

        # Collect isolated outputs and persist to Supabase
        storage_svc.organize_run_outputs(run.project_id, run.run_id, phase_name)
        try:
            if phase_name == "phase1":
                bottlenecks = compute_bottlenecks(run_dir / "event_log.csv")
                paths = compute_paths(run_dir / "event_log.csv")
                map_exists = (run_dir / "process_map.png").exists() or OUTPUT_FILES["process_map"].exists()
                sb.write_discovery_to_db(run.pipeline_run_id, bottlenecks, paths, map_exists)
            elif phase_name == "phase2":
                pred_file = run_dir / "predictions.json"
                pred_data = compute_prediction_data(pred_file if pred_file.exists() else None)
                sb.write_prediction_to_db(run.pipeline_run_id, pred_data)
            elif phase_name == "phase3":
                sb.write_explanation_to_db(run.pipeline_run_id)
        except Exception as db_exc:
            logger.warning(f"Failed writing phase {phase_name} results to Supabase: {db_exc}")

        run.add_log(f"Completed {run.current_stage}")

    run.status = RunStatusEnum.COMPLETED
    run.progress = 100
    run.current_stage = None
    run.completed_at = datetime.now(timezone.utc).isoformat()
    run.add_log("All phases completed successfully")
    run.notify_status()
    sb.update_pipeline_run(run.pipeline_run_id, "completed")
    storage_svc.save_run_metadata(
        run.project_id, run.run_id,
        status="COMPLETED", completed_at=run.completed_at,
    )
    logger.info(f"Run {run.run_id} completed successfully")


async def run_single_phase(run: PipelineRun, phase: str) -> None:
    """Execute a single phase in background with full isolation."""
    run.status = RunStatusEnum.RUNNING
    run.started_at = datetime.now(timezone.utc).isoformat()
    run.current_stage = PHASE_NAMES.get(phase, phase)
    run.notify_status()

    run_dir = storage_svc.create_run_dir(run.project_id, run.run_id)
    event_log_path = storage_svc.setup_run_input(run.project_id, run.run_id)

    upload_state = _read_upload_state()
    data_source = upload_state.get("source", "synthetic")
    source_filename = upload_state.get("filename") if data_source == "uploaded" else None
    row_count = upload_state.get("row_count") if data_source == "uploaded" else _get_row_count(event_log_path)
    run.pipeline_run_id = sb.create_pipeline_run(data_source, source_filename, row_count)

    script = PHASE_SCRIPTS.get(phase)
    if not script:
        run.status = RunStatusEnum.FAILED
        run.error_message = f"Unknown phase: {phase}"
        run.notify_status()
        return

    # Check insufficient data before Phase 2
    if phase == "phase2":
        is_insufficient, case_count = _check_insufficient_data(run_dir / "event_log.csv")
        if is_insufficient:
            err_msg = (
                f"Insufficient data: event log contains only {case_count} case(s). "
                f"At least 10 cases are required for process mining and predictive analysis."
            )
            logger.warning(f"Single phase {phase} aborted: {err_msg}")
            run.status = RunStatusEnum.FAILED
            run.error_message = err_msg
            run.completed_at = datetime.now(timezone.utc).isoformat()
            run.add_log(err_msg, "error")
            run.notify_status()
            sb.update_pipeline_run(run.pipeline_run_id, "failed", "insufficient_data")
            storage_svc.save_run_metadata(
                run.project_id, run.run_id,
                status="FAILED", failed_at_phase="insufficient_data",
                completed_at=run.completed_at, error_message=err_msg,
            )
            return

    if phase == "phase1" and data_source == "uploaded":
        sub_scripts = [
            PROJECT_ROOT / "validate_data.py",
            PROJECT_ROOT / "discover_process.py",
            PROJECT_ROOT / "bottlenecks.py",
        ]
        success = True
        for sub_script in sub_scripts:
            if not await _run_script_async(sub_script, run, phase, run_dir):
                success = False
                break
    else:
        success = await _run_script_async(script, run, phase, run_dir)

    if success and phase == "phase1":
        try:
            conformance_res = compute_conformance(run_dir / "event_log.csv")
            with open(str(run_dir / "conformance.json"), "w", encoding="utf-8") as f:
                json.dump(conformance_res, f, indent=2)
        except Exception as conf_exc:
            logger.warning(f"Failed to generate conformance in single phase run {run.run_id}: {conf_exc}")

    storage_svc.organize_run_outputs(run.project_id, run.run_id, phase)

    if success:
        run.status = RunStatusEnum.COMPLETED
        run.progress = 100
        run.completed_at = datetime.now(timezone.utc).isoformat()
        run.add_log(f"Completed {run.current_stage}")
        run.notify_status()

        try:
            if phase == "phase1":
                bottlenecks = compute_bottlenecks(run_dir / "event_log.csv")
                paths = compute_paths(run_dir / "event_log.csv")
                map_exists = (run_dir / "process_map.png").exists() or OUTPUT_FILES["process_map"].exists()
                sb.write_discovery_to_db(run.pipeline_run_id, bottlenecks, paths, map_exists)
            elif phase == "phase2":
                pred_file = run_dir / "predictions.json"
                pred_data = compute_prediction_data(pred_file if pred_file.exists() else None)
                sb.write_prediction_to_db(run.pipeline_run_id, pred_data)
            elif phase == "phase3":
                sb.write_explanation_to_db(run.pipeline_run_id)
        except Exception as exc:
            logger.warning(f"Error persisting phase {phase} results: {exc}")

        sb.update_pipeline_run(run.pipeline_run_id, "completed")
        storage_svc.save_run_metadata(run.project_id, run.run_id, status="COMPLETED", completed_at=run.completed_at)
    else:
        run.status = RunStatusEnum.FAILED
        if not run.error_message:
            run.error_message = f"Failed at {phase}"
        run.completed_at = datetime.now(timezone.utc).isoformat()
        run.add_log(f"FAILED at {phase}: {run.error_message}", "error")
        run.notify_status()
        sb.update_pipeline_run(run.pipeline_run_id, "failed", phase)
        storage_svc.save_run_metadata(
            run.project_id, run.run_id,
            status="FAILED", failed_at_phase=phase,
            completed_at=run.completed_at, error_message=run.error_message,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_upload_state() -> dict:
    from backend.config import UPLOAD_STATE_FILE
    try:
        if UPLOAD_STATE_FILE.exists():
            import json
            with open(str(UPLOAD_STATE_FILE), encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"source": "synthetic"}


def _get_row_count(event_log_path: Optional[Path] = None) -> Optional[int]:
    p = event_log_path or OUTPUT_FILES["event_log"]
    try:
        if p and p.exists():
            with open(str(p), "r", encoding="utf-8") as f:
                return max(0, sum(1 for _ in f) - 1)
    except Exception:
        pass
    return None
