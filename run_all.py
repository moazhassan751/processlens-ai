"""
Step 5 — Run all ProcessLens Phase 1 steps in sequence.

Usage:  python run_all.py
"""

import os
import subprocess
import sys


def ensure_graphviz_on_path():
    """Add Graphviz to PATH if not already present (Windows install location)."""
    graphviz_bin = r"C:\Program Files\Graphviz\bin"
    if os.path.isdir(graphviz_bin) and graphviz_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = graphviz_bin + os.pathsep + os.environ.get("PATH", "")


def run_step(label: str, script: str) -> bool:
    """Run a Python script as a subprocess. Returns True on success."""
    print(f"\n>> {label}", flush=True)
    print("-" * 55, flush=True)
    result = subprocess.run(
        [sys.executable, script],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        print(f"\n[FAIL] FAILED at: {label} (exit code {result.returncode})", flush=True)
        return False
    return True


def main():
    ensure_graphviz_on_path()

    print(flush=True)
    print("+" + "=" * 55 + "+", flush=True)
    print("|   ProcessLens Phase 1 -- Full Pipeline Run            |", flush=True)
    print("+" + "=" * 55 + "+", flush=True)

    steps = [
        ("Step 1: Generate synthetic event log", "generate_data.py"),
        ("Step 2: Validate event log", "validate_data.py"),
        ("Step 3: Discover process (Inductive Miner)", "discover_process.py"),
        ("Step 4: Rank bottlenecks", "bottlenecks.py"),
    ]

    for label, script in steps:
        if not run_step(label, script):
            print("\n[!] Pipeline stopped due to error. Fix the issue and re-run.", flush=True)
            sys.exit(1)

    # --- Final summary ---
    print(flush=True)
    print("+" + "=" * 55 + "+", flush=True)
    print("|   ProcessLens Phase 1 -- COMPLETE                     |", flush=True)
    print("+" + "=" * 55 + "+", flush=True)

    map_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "process_map.png")
    if os.path.exists(map_file):
        size_kb = os.path.getsize(map_file) / 1024
        print(f"  [OK] Process map created: process_map.png ({size_kb:.1f} KB)", flush=True)
    else:
        print("  [X] process_map.png was NOT created -- check Step 3 output", flush=True)

    print("  [OK] Bottleneck table printed above (Step 4)", flush=True)
    print("  [OK] All steps completed successfully", flush=True)
    print(flush=True)


if __name__ == "__main__":
    main()
