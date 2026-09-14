"""
Phase 2, Step 5 -- Generate 20 synthetic in-progress (open) cases.

Creates open_cases.csv with cases stopped at Submitted or Reviewed.
Uses the same timestamp/resource generation style as Phase 1.
No case includes Approved or Completed -- they are genuinely mid-process.
"""

import csv
import os
import random
from datetime import datetime, timedelta

# Fixed seed for reproducibility
random.seed(99)

NUM_OPEN_CASES = 20
OUTPUT_FILE = "open_cases.csv"

# Same resource list as Phase 1
RESOURCES = [
    "Alice Johnson", "Bob Smith", "Carol Lee",
    "David Kim", "Eva Martinez", "Frank Chen",
]

# Same wait-time distributions as Phase 1
WAIT_HOURS_REVIEWED = (1, 5)


def main():
    print("=" * 60)
    print("  PHASE 2, STEP 5 -- Generate Open (In-Progress) Cases")
    print("=" * 60)

    rows = []
    base_time = datetime(2025, 2, 10, 9, 0, 0)
    act_1 = "Submitted"
    act_2 = "Reviewed"
    resources = RESOURCES

    # Inspect event_log.csv if available
    try:
        import pandas as pd
        if pd.Series(["event_log.csv"]).map(pd.io.common.file_exists).iloc[0] or os.path.exists("event_log.csv"):
            edf = pd.read_csv("event_log.csv")
            acts = list(edf["activity"].unique())
            if "Submitted" not in acts or "Reviewed" not in acts:
                second_acts = edf.groupby("case_id")["activity"].nth(1).value_counts()
                act_1 = edf.groupby("case_id")["activity"].first().value_counts().index[0]
                act_2 = second_acts.index[0] if not second_acts.empty else acts[1]
                res_list = sorted([str(r) for r in edf["resource"].dropna().unique()])
                if res_list:
                    resources = res_list
                edf["timestamp"] = pd.to_datetime(edf["timestamp"])
                base_time = edf["timestamp"].max().to_pydatetime()
    except Exception:
        pass

    # 8 cases stop at act_1, 12 at act_2
    stop_points = [act_1] * 8 + [act_2] * 12
    random.shuffle(stop_points)

    for i in range(NUM_OPEN_CASES):
        case_id = f"OPEN-{i + 1:04d}"
        stop_at = stop_points[i]

        # Random start offset (spread over 5 days, like Phase 1 style)
        start_offset = timedelta(
            days=random.randint(0, 5),
            hours=random.randint(0, 8),
            minutes=random.randint(0, 59),
        )
        current_time = base_time + start_offset

        # First event (always present)
        rows.append({
            "case_id": case_id,
            "activity": act_1,
            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "resource": random.choice(resources),
        })

        if stop_at == act_2:
            lo, hi = WAIT_HOURS_REVIEWED
            wait = random.uniform(lo, hi)
            current_time += timedelta(hours=wait)
            current_time += timedelta(minutes=random.randint(0, 30))

            rows.append({
                "case_id": case_id,
                "activity": act_2,
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "resource": random.choice(resources),
            })

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["case_id", "activity", "timestamp", "resource"]
        )
        writer.writeheader()
        writer.writerows(rows)

    n_submitted = stop_points.count("Submitted")
    n_reviewed = stop_points.count("Reviewed")

    print(f"  Generated {NUM_OPEN_CASES} open cases")
    print(f"    - Stopped at Submitted: {n_submitted}")
    print(f"    - Stopped at Reviewed : {n_reviewed}")
    print(f"  Total events: {len(rows)}")
    print(f"  Saved to: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
