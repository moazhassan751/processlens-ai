"""
Step 3 — Discover the process from the event log using pm4py's Inductive Miner.

- Loads and validates event_log.csv (reuses validate_data.validate)
- Converts to pm4py format
- Runs the Inductive Miner
- Exports process_map.png
- Prints discovered paths as plain text
"""

import os
import sys

import pandas as pd
import pm4py

from validate_data import validate

EVENT_LOG_FILE = "event_log.csv"
PROCESS_MAP_FILE = "process_map.png"


def ensure_graphviz_on_path():
    """Add Graphviz to PATH if not already present (Windows install location)."""
    graphviz_bin = r"C:\Program Files\Graphviz\bin"
    if os.path.isdir(graphviz_bin) and graphviz_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = graphviz_bin + os.pathsep + os.environ.get("PATH", "")


def load_and_validate() -> pd.DataFrame:
    """Load the CSV and run validation; exit on failure."""
    try:
        df = pd.read_csv(EVENT_LOG_FILE)
    except FileNotFoundError:
        print(f"ERROR: {EVENT_LOG_FILE} not found. Run generate_data.py first.")
        sys.exit(1)

    passed, report = validate(df)
    print(report)
    if not passed:
        sys.exit(1)
    return df


def prepare_event_log(df: pd.DataFrame):
    """Convert DataFrame to pm4py-compatible format."""
    df = df.rename(
        columns={
            "case_id": "case:concept:name",
            "activity": "concept:name",
            "timestamp": "time:timestamp",
            "resource": "org:resource",
        }
    )
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])
    df = df.sort_values(["case:concept:name", "time:timestamp"])
    log = pm4py.format_dataframe(df, case_id="case:concept:name",
                                  activity_key="concept:name",
                                  timestamp_key="time:timestamp")
    return log


def extract_paths_from_tree(tree, current_path=None):
    """
    Walk a pm4py ProcessTree and extract human-readable path descriptions.
    Returns a list of path strings.
    """
    if current_path is None:
        current_path = []

    paths = []

    if tree.label is not None:
        # Leaf node -- an activity
        return [current_path + [tree.label]]

    op = str(tree.operator) if tree.operator else "UNKNOWN"

    if op in ("SEQUENCE", "->"):
        # All children in order
        combined = [current_path]
        for child in tree.children:
            new_combined = []
            for p in combined:
                child_paths = extract_paths_from_tree(child, p)
                new_combined.extend(child_paths)
            combined = new_combined
        return combined

    elif op in ("XOR", "X"):
        # One of the children (choice)
        for child in tree.children:
            paths.extend(extract_paths_from_tree(child, current_path))
        return paths

    elif op in ("PARALLEL", "+"):
        # All children, any order -- simplify by listing sequentially
        combined = [current_path]
        for child in tree.children:
            new_combined = []
            for p in combined:
                child_paths = extract_paths_from_tree(child, p)
                new_combined.extend(child_paths)
            combined = new_combined
        return combined

    elif op in ("LOOP", "O", "*"):
        # Loop: first child is body, second is redo
        # No-loop path: just the body
        # One-iteration path: body + redo + body (back through the loop once)
        if len(tree.children) >= 2:
            body_paths = extract_paths_from_tree(tree.children[0], [])
            redo_paths = extract_paths_from_tree(tree.children[1], [])
            loop_paths = []
            for bp in body_paths:
                # Path with no rework: just the body
                loop_paths.append(current_path + bp)
                # Path with one rework iteration: body + redo + body
                for rp in redo_paths:
                    clean_rp = [a for a in rp if a is not None]
                    if clean_rp:  # skip tau (silent) transitions
                        loop_paths.append(current_path + bp + clean_rp + bp)
            return loop_paths
        else:
            return extract_paths_from_tree(tree.children[0], current_path)

    else:
        # Fallback
        for child in tree.children:
            paths.extend(extract_paths_from_tree(child, current_path))
        return paths


def main():
    ensure_graphviz_on_path()

    print()
    df = load_and_validate()
    print()

    log = prepare_event_log(df)

    # Discover process tree using Inductive Miner
    print("=" * 55)
    print("  STEP 3 -- Process Discovery (Inductive Miner)")
    print("=" * 55)

    tree = pm4py.discover_process_tree_inductive(log)

    # Export visual process map
    # Use discover_petri_net for a cleaner PNG export
    net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(log)
    pm4py.save_vis_petri_net(net, initial_marking, final_marking, PROCESS_MAP_FILE)

    if os.path.exists(PROCESS_MAP_FILE):
        size_kb = os.path.getsize(PROCESS_MAP_FILE) / 1024
        print(f"  [OK] Process map saved: {PROCESS_MAP_FILE} ({size_kb:.1f} KB)")
    else:
        print(f"  [X] Failed to create {PROCESS_MAP_FILE}")
        sys.exit(1)

    # Print discovered paths as plain text
    print()
    print("  Discovered Path(s):")
    print("  " + "-" * 50)
    try:
        paths = extract_paths_from_tree(tree)
        # Deduplicate and filter out paths with only tau/None
        seen = set()
        path_num = 0
        for path in paths:
            clean = [a for a in path if a is not None]
            if not clean:
                continue
            key = tuple(clean)
            if key in seen:
                continue
            seen.add(key)
            path_num += 1
            print(f"  Path {path_num}: {' -> '.join(clean)}")
    except Exception as e:
        # Fallback: print the tree representation
        print(f"  (Could not extract paths: {e})")
        print(f"  Process tree: {tree}")

    print("=" * 55)


if __name__ == "__main__":
    main()
