"""
ProcessLens — Storage Service
===============================
Project/run filesystem isolation.
Each run executes inside its dedicated run directory under:
storage/projects/{project_id}/runs/{run_id}/
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import STORAGE_ROOT, PROJECT_ROOT, OUTPUT_FILES

logger = logging.getLogger("processlens.storage")

FALLBACK_WARNING = "Showing fallback data, not this run's own output."

RUN_ARTIFACT_SUBDIRS = {
    "event_log": ("input", "event_log.csv"),
    "process_map": ("process_map", "process_map.png"),
    "training_data": ("processed", "training_data.csv"),
    "delay_model": ("models", "delay_model.joblib"),
    "anomaly_model": ("models", "anomaly_model.joblib"),
    "open_cases": ("processed", "open_cases.csv"),
    "predictions": ("outputs", "predictions.json"),
    "resource_mapping": ("processed", "resource_mapping.json"),
    "model_metrics": ("outputs", "model_metrics.json"),
    "explanation_output": ("outputs", "explanation_output.json"),
    "conformance": ("outputs", "conformance.json"),
}


def resolve_artifact_path(
    project_id: str = "default",
    run_id: Optional[str] = None,
    artifact_key: str = "event_log",
) -> tuple[Optional[Path], bool]:
    """
    Resolve the artifact path for a specific project/run, with explicit fallback tracking.
    Returns:
        (resolved_path: Optional[Path], is_fallback: bool)
    - If run-specific artifact exists: returns (path, False)
    - If run-specific artifact is missing but legacy/root fallback exists: returns (fallback_path, True)
    - If neither exists: returns (None, False)
    """
    # 1. When a specific run_id is requested
    if run_id and project_id:
        run_dir = get_run_dir(project_id, run_id)
        sub, filename = RUN_ARTIFACT_SUBDIRS.get(artifact_key, ("outputs", f"{artifact_key}.json"))
        run_path = run_dir / sub / filename
        if run_path.exists():
            return run_path, False
        flat_path = run_dir / filename
        if flat_path.exists():
            return flat_path, False

        # For default project, missing run artifact falls back to legacy root artifact
        if project_id == "default":
            legacy_path = OUTPUT_FILES.get(artifact_key)
            if legacy_path and legacy_path.exists():
                logger.info(f"Run '{run_id}' missing {artifact_key}; using fallback {legacy_path}")
                return legacy_path, True

        return None, False

    # 2. When project_id != 'default' and no run_id
    if project_id and project_id != "default":
        if artifact_key == "event_log":
            proj_upload = STORAGE_ROOT / "projects" / project_id / "uploads" / "event_log.csv"
            if proj_upload.exists():
                return proj_upload, False
            return None, False
        else:
            return None, False

    # 3. Default workspace (root files)
    root_path = OUTPUT_FILES.get(artifact_key)
    if root_path and root_path.exists():
        return root_path, False

    return None, False


def ensure_storage():
    """Create the storage root if missing."""
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    (STORAGE_ROOT / "projects").mkdir(exist_ok=True)


def ensure_project(project_id: str) -> Path:
    """Create and return the project directory."""
    p = STORAGE_ROOT / "projects" / project_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "uploads").mkdir(exist_ok=True)
    (p / "runs").mkdir(exist_ok=True)
    return p


def create_run_dir(project_id: str, run_id: str) -> Path:
    """Create the full run directory tree and return its path."""
    proj = ensure_project(project_id)
    run_dir = proj / "runs" / run_id
    for sub in ["input", "processed", "models", "outputs", "logs", "process_map", "reports"]:
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    return run_dir


def get_run_dir(project_id: str, run_id: str) -> Path:
    return STORAGE_ROOT / "projects" / project_id / "runs" / run_id


def save_run_metadata(project_id: str, run_id: str, **kwargs) -> None:
    """Save or update run metadata."""
    run_dir = get_run_dir(project_id, run_id)
    meta_path = run_dir / "metadata.json"
    meta = {}
    if meta_path.exists():
        try:
            with open(str(meta_path), encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as exc:
            logger.warning(f"Could not load existing metadata: {exc}")
    meta["project_id"] = project_id
    meta["run_id"] = run_id
    meta.update(kwargs)
    try:
        with open(str(meta_path), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, default=str)
    except Exception as exc:
        logger.error(f"Failed to write metadata: {exc}")


def load_run_metadata(project_id: str, run_id: str) -> dict:
    meta_path = get_run_dir(project_id, run_id) / "metadata.json"
    if meta_path.exists():
        try:
            with open(str(meta_path), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def setup_run_input(project_id: str, run_id: str, source_event_log: Optional[Path] = None) -> Path:
    """
    Set up the isolated input event_log.csv for the run.
    Copies the specified or project-specific event log into:
      1. run_dir / "input" / "event_log.csv"
      2. run_dir / "event_log.csv" (working directory for subprocess)
    """
    run_dir = create_run_dir(project_id, run_id)
    target_work = run_dir / "event_log.csv"
    target_input = run_dir / "input" / "event_log.csv"

    src = source_event_log
    if not src or not src.exists():
        # Check project uploads
        proj_upload = STORAGE_ROOT / "projects" / project_id / "uploads" / "event_log.csv"
        if proj_upload.exists():
            src = proj_upload
        elif OUTPUT_FILES["event_log"].exists():
            src = OUTPUT_FILES["event_log"]

    if src and src.exists():
        shutil.copy2(str(src), str(target_work))
        shutil.copy2(str(src), str(target_input))
        logger.info(f"Initialized run {run_id} input from {src}")

    return target_work


def copy_input_to_run(project_id: str, run_id: str) -> None:
    """Backward compatibility alias for setup_run_input."""
    setup_run_input(project_id, run_id)


def organize_run_outputs(project_id: str, run_id: str, phase: str) -> None:
    """
    Organize outputs generated inside the run's working directory into subdirectories,
    and mirror to root if running default project for backward compatibility.
    """
    run_dir = get_run_dir(project_id, run_id)

    copy_map = {
        "phase1": [
            (run_dir / "process_map.png", run_dir / "process_map" / "process_map.png", OUTPUT_FILES["process_map"]),
            (run_dir / "conformance.json", run_dir / "outputs" / "conformance.json", OUTPUT_FILES["conformance"]),
        ],
        "phase2": [
            (run_dir / "training_data.csv", run_dir / "processed" / "training_data.csv", OUTPUT_FILES["training_data"]),
            (run_dir / "delay_model.joblib", run_dir / "models" / "delay_model.joblib", OUTPUT_FILES["delay_model"]),
            (run_dir / "anomaly_model.joblib", run_dir / "models" / "anomaly_model.joblib", OUTPUT_FILES["anomaly_model"]),
            (run_dir / "open_cases.csv", run_dir / "processed" / "open_cases.csv", OUTPUT_FILES["open_cases"]),
            (run_dir / "predictions.json", run_dir / "outputs" / "predictions.json", OUTPUT_FILES["predictions"]),
            (run_dir / "resource_mapping.json", run_dir / "processed" / "resource_mapping.json", OUTPUT_FILES["resource_mapping"]),
            (run_dir / "model_metrics.json", run_dir / "outputs" / "model_metrics.json", OUTPUT_FILES["model_metrics"]),
        ],
        "phase3": [
            (run_dir / "explanation_output.json", run_dir / "outputs" / "explanation_output.json", OUTPUT_FILES["explanation_output"]),
        ],
    }

    for src, dst_sub, dst_root in copy_map.get(phase, []):
        if src.exists():
            dst_sub.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst_sub))
            # Backward compatibility mirror for default project
            if project_id == "default":
                try:
                    shutil.copy2(str(src), str(dst_root))
                except Exception as exc:
                    logger.warning(f"Failed to mirror {src.name} to root: {exc}")


def collect_outputs_from_root(project_id: str, run_id: str, phase: str) -> None:
    """Backward compatibility alias."""
    organize_run_outputs(project_id, run_id, phase)


def list_projects() -> list[dict]:
    """List all projects with run counts."""
    projects_dir = STORAGE_ROOT / "projects"
    if not projects_dir.exists():
        return []
    result = []
    for p in sorted(projects_dir.iterdir()):
        if p.is_dir():
            runs_dir = p / "runs"
            run_count = len(list(runs_dir.iterdir())) if runs_dir.exists() else 0
            result.append({
                "project_id": p.name,
                "run_count": run_count,
            })
    return result


def list_runs(project_id: str) -> list[dict]:
    """List all runs for a project with metadata."""
    runs_dir = STORAGE_ROOT / "projects" / project_id / "runs"
    if not runs_dir.exists():
        return []
    result = []
    for r in sorted(runs_dir.iterdir(), reverse=True):
        if r.is_dir():
            meta = load_run_metadata(project_id, r.name)
            result.append(meta if meta else {"run_id": r.name, "project_id": project_id})
    return result
