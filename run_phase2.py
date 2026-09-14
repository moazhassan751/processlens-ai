"""
Phase 2 -- Run all Phase 2 steps in sequence.

Assumes event_log.csv from Phase 1 already exists.

Usage:  python run_phase2.py
"""

import os
import subprocess
import sys


def run_step(label: str, script: str) -> bool:
    """Run a Python script as a subprocess. Returns True on success."""
    print(f"\n>> {label}", flush=True)
    print("-" * 60, flush=True)
    result = subprocess.run(
        [sys.executable, script],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        print(f"\n[FAIL] at: {label} (exit code {result.returncode})", flush=True)
        return False
    return True


def main():
    print(flush=True)
    print("+" + "=" * 60 + "+", flush=True)
    print("|   ProcessLens Phase 2 -- ML Prediction Pipeline         |", flush=True)
    print("+" + "=" * 60 + "+", flush=True)

    # Check prerequisite
    if not os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "event_log.csv")
    ):
        print(
            "\n[ERROR] event_log.csv not found. Run Phase 1 first.", flush=True
        )
        sys.exit(1)

    steps = [
        ("Steps 1-2: Build training data", "build_training_data.py"),
        ("Step 3: Train delay-risk classifier", "train_model.py"),
        ("Step 4: Anomaly detection", "detect_anomalies.py"),
        ("Step 5: Generate open cases", "generate_open_cases.py"),
        ("Step 6: Predict delays for open cases", "predict_delays.py"),
    ]

    for label, script in steps:
        if not run_step(label, script):
            print(
                "\n[!] Pipeline stopped due to error. Fix the issue and re-run.",
                flush=True,
            )
            sys.exit(1)

    # ---- Final summary ----
    print(flush=True)
    print("+" + "=" * 60 + "+", flush=True)
    print("|   ProcessLens Phase 2 -- COMPLETE                       |", flush=True)
    print("+" + "=" * 60 + "+", flush=True)

    files_to_check = [
        "training_data.csv",
        "delay_model.joblib",
        "anomaly_model.joblib",
        "open_cases.csv",
        "predictions.json",
        "resource_mapping.json",
    ]
    for f in files_to_check:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
        if os.path.exists(path):
            size = os.path.getsize(path) / 1024
            print(f"  [OK] {f} ({size:.1f} KB)", flush=True)
        else:
            print(f"  [X] {f} -- MISSING", flush=True)

    print(flush=True)


if __name__ == "__main__":
    main()
