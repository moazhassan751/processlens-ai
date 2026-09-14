"""
Step 1 — Generate a synthetic event log for a request-approval process.

Creates event_log.csv with columns: case_id, activity, timestamp, resource.
300 cases, ~18% rework path, Approved step seeded as bottleneck (20-40 h wait).
"""

import csv
import random
from datetime import datetime, timedelta

# Reproducibility
random.seed(42)

# Configuration
NUM_CASES = 300
REWORK_FRACTION = 0.18
OUTPUT_FILE = "event_log.csv"

NORMAL_PATH = ["Submitted", "Reviewed", "Approved", "Completed"]
REWORK_PATH = [
    "Submitted",
    "Reviewed",
    "Sent Back for Correction",
    "Reviewed",
    "Approved",
    "Completed",
]

RESOURCES = [
    "Alice Johnson",
    "Bob Smith",
    "Carol Lee",
    "David Kim",
    "Eva Martinez",
    "Frank Chen",
]

# Wait-time ranges (hours) — keyed by the activity that FOLLOWS the wait
WAIT_HOURS = {
    "Submitted": (0, 0),               # first event — no wait
    "Reviewed": (1, 5),                 # normal gap
    "Sent Back for Correction": (1, 5), # normal gap
    "Approved": (20, 40),               # ← seeded bottleneck
    "Completed": (1, 5),                # normal gap
}


def generate_event_log():
    """Return rows list and metadata about the generated log."""
    all_cases = list(range(1, NUM_CASES + 1))
    num_rework = round(NUM_CASES * REWORK_FRACTION)
    rework_cases = set(random.sample(all_cases, num_rework))

    rows = []
    # Spread case start times over ~30 days so the log looks realistic
    base_time = datetime(2025, 1, 6, 8, 0, 0)

    for case_id in all_cases:
        path = REWORK_PATH if case_id in rework_cases else NORMAL_PATH
        # Random start offset: 0-30 days + 0-8 hours
        start_offset = timedelta(
            days=random.randint(0, 30),
            hours=random.randint(0, 8),
            minutes=random.randint(0, 59),
        )
        current_time = base_time + start_offset

        for activity in path:
            lo, hi = WAIT_HOURS[activity]
            if lo > 0 or hi > 0:
                wait = random.uniform(lo, hi)
                current_time += timedelta(hours=wait)
                # Add small minute-level jitter so timestamps aren't round
                current_time += timedelta(minutes=random.randint(0, 30))

            resource = random.choice(RESOURCES)
            rows.append(
                {
                    "case_id": f"CASE-{case_id:04d}",
                    "activity": activity,
                    "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "resource": resource,
                }
            )

    return rows, num_rework


def main():
    rows, num_rework = generate_event_log()

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "activity", "timestamp", "resource"])
        writer.writeheader()
        writer.writerows(rows)

    unique_cases = {r["case_id"] for r in rows}
    print("=" * 55)
    print("  STEP 1 -- Event Log Generated")
    print("=" * 55)
    print(f"  Output file  : {OUTPUT_FILE}")
    print(f"  Total cases  : {len(unique_cases)}")
    print(f"  Total events : {len(rows)}")
    print(f"  Rework cases : {num_rework}  (~{num_rework/len(unique_cases)*100:.0f}%)")
    print("=" * 55)


if __name__ == "__main__":
    main()
