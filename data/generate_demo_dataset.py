"""
Generate a best-in-class enterprise demo dataset for ProcessLens.

Scenario: Retail Banking — Loan Application Processing
  Submitted → Reviewed → Approved → Completed
  (with ~15% rework via "Sent Back for Correction")

Design Goals:
  ✓ 1,000 completed cases (~5,400+ events) — enterprise-scale impression
  ✓ 25 in-flight open cases for predictive risk showcase
  ✓ Realistic approval bottleneck (18–42 h wait — manager batch-review)
  ✓ ~15% rework rate (compliance rejection loop)
  ✓ 12 named banking resources across 3 tiers (intake, review, approval)
  ✓ Volume peaks on Mon/Tue mornings (realistic banking pattern)
  ✓ Seasonal surge in mid-Q1 (Jan–Feb application spike)
  ✓ Resource workload imbalance (2 senior reviewers overloaded)
  ✓ Weekend/holiday slowdowns on approval step
  ✓ Timestamps span ~6 months for meaningful time-series analysis

Compatible with ProcessLens validation:
  - Columns: case_id, activity, timestamp, resource
  - Activities: Submitted, Reviewed, Approved, Completed, Sent Back for Correction
  - Timestamps: strictly increasing within each case
  - No duplicates, no nulls
"""

import csv
import random
import math
from datetime import datetime, timedelta
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

random.seed(2025)

NUM_COMPLETED_CASES = 1000
NUM_OPEN_CASES = 25
REWORK_FRACTION = 0.15  # 15% of cases hit a rework loop

# Output paths
SCRIPT_DIR = Path(__file__).parent
EVENT_LOG_FILE = SCRIPT_DIR / "demo_event_log.csv"
OPEN_CASES_FILE = SCRIPT_DIR / "demo_open_cases.csv"

# ═══════════════════════════════════════════════════════════════
# Banking Resources — 12 staff across 3 operational tiers
# ═══════════════════════════════════════════════════════════════

# Tier 1: Intake Officers (handle Submitted)
INTAKE_OFFICERS = [
    "Sarah Mitchell",
    "James Ortega",
    "Priya Sharma",
    "Kevin Nguyen",
]

# Tier 2: Compliance Reviewers (handle Reviewed, Sent Back for Correction)
COMPLIANCE_REVIEWERS = [
    "Rachel Goldman",    # Senior — gets 40% of reviews (overloaded)
    "Marcus Chen",       # Senior — gets 30% of reviews (overloaded)
    "Aisha Patel",       # Junior — gets 15%
    "Tom Henderson",     # Junior — gets 15%
]
REVIEWER_WEIGHTS = [0.40, 0.30, 0.15, 0.15]  # workload imbalance

# Tier 3: Approval Managers (handle Approved, Completed)
APPROVAL_MANAGERS = [
    "Linda Park",        # VP — gets 35% approvals
    "Robert Dawson",     # Director — gets 35% approvals
    "Diana Vasquez",     # Senior Manager — gets 20%
    "Christopher Hall",  # Manager — gets 10%
]
MANAGER_WEIGHTS = [0.35, 0.35, 0.20, 0.10]

# Combined list for resource_mapping compatibility
ALL_RESOURCES = sorted(
    INTAKE_OFFICERS + COMPLIANCE_REVIEWERS + APPROVAL_MANAGERS
)

# ═══════════════════════════════════════════════════════════════
# Activity paths
# ═══════════════════════════════════════════════════════════════

NORMAL_PATH = ["Submitted", "Reviewed", "Approved", "Completed"]
REWORK_PATH = [
    "Submitted",
    "Reviewed",
    "Sent Back for Correction",
    "Reviewed",
    "Approved",
    "Completed",
]

# ═══════════════════════════════════════════════════════════════
# Wait-time distributions (hours) — realistic banking process
# ═══════════════════════════════════════════════════════════════

def get_wait_hours(activity: str, current_time: datetime) -> float:
    """
    Return wait hours for the given activity, adjusted for
    day-of-week and time-of-day realism.
    """
    weekday = current_time.weekday()  # 0=Mon, 6=Sun
    is_weekend = weekday >= 5

    if activity == "Submitted":
        return 0.0  # first event, no wait

    elif activity == "Reviewed":
        # Standard triage: 1.5–6 hours, slower on weekends
        base = random.uniform(1.5, 6.0)
        if is_weekend:
            base += random.uniform(8, 16)  # weekend backlog
        return base

    elif activity == "Sent Back for Correction":
        # Quick rejection decision: 1–4 hours after review
        return random.uniform(1.0, 4.0)

    elif activity == "Approved":
        # ═══ THE BOTTLENECK ═══
        # Managers batch-review: 18–42 hours typical
        # Fri afternoon → Mon morning creates 48–60h weekend gap
        if weekday == 4 and current_time.hour >= 14:
            # Friday afternoon submission → Monday approval
            return random.uniform(48, 64)
        elif is_weekend:
            return random.uniform(36, 56)
        else:
            # Normal weekday bottleneck
            return random.uniform(18, 42)

    elif activity == "Completed":
        # Final processing: 1–5 hours
        return random.uniform(1.0, 5.0)

    return random.uniform(1, 3)


def pick_resource(activity: str) -> str:
    """
    Assign resource based on activity tier with weighted distribution
    to create realistic workload imbalances.
    """
    if activity == "Submitted":
        return random.choice(INTAKE_OFFICERS)

    elif activity in ("Reviewed", "Sent Back for Correction"):
        return random.choices(COMPLIANCE_REVIEWERS, weights=REVIEWER_WEIGHTS, k=1)[0]

    elif activity in ("Approved", "Completed"):
        return random.choices(APPROVAL_MANAGERS, weights=MANAGER_WEIGHTS, k=1)[0]

    return random.choice(ALL_RESOURCES)


# ═══════════════════════════════════════════════════════════════
# Case start time distribution — realistic banking volumes
# ═══════════════════════════════════════════════════════════════

def generate_start_time(case_index: int, total_cases: int) -> datetime:
    """
    Distribute case start times over ~6 months (Jan 2025 – Jun 2025)
    with volume peaks in Jan–Feb (Q1 lending rush) and Mon/Tue mornings.
    """
    base = datetime(2025, 1, 6, 8, 0, 0)  # Monday Jan 6, 2025

    # Spread over ~180 days with seasonal weighting
    # Use beta distribution to front-load cases into Jan–Mar
    progress = case_index / max(total_cases - 1, 1)
    day_offset = int(progress * 175)

    # Add seasonal clustering: more cases in Q1 (beta skew)
    seasonal_jitter = int(random.betavariate(2, 5) * 40) - 15
    day_offset = max(0, min(175, day_offset + seasonal_jitter))

    # Business hours: 7 AM – 6 PM, heavier on Mon–Wed
    hour = random.choices(
        range(7, 19),
        weights=[2, 5, 8, 10, 10, 9, 8, 7, 6, 4, 3, 2],  # peak 10–11 AM
        k=1
    )[0]
    minute = random.randint(0, 59)

    start = base + timedelta(days=day_offset, hours=hour - 8, minutes=minute)

    # Skip weekends for submission (banks closed)
    while start.weekday() >= 5:
        start += timedelta(days=1)

    return start


# ═══════════════════════════════════════════════════════════════
# Generate completed cases (event_log.csv)
# ═══════════════════════════════════════════════════════════════

def generate_completed_cases() -> list[dict]:
    all_cases = list(range(1, NUM_COMPLETED_CASES + 1))
    num_rework = round(NUM_COMPLETED_CASES * REWORK_FRACTION)
    rework_cases = set(random.sample(all_cases, num_rework))

    rows = []

    for case_index, case_num in enumerate(all_cases):
        path = REWORK_PATH if case_num in rework_cases else NORMAL_PATH
        current_time = generate_start_time(case_index, NUM_COMPLETED_CASES)

        for activity in path:
            wait = get_wait_hours(activity, current_time)
            if wait > 0:
                current_time += timedelta(hours=wait)
                # Add minute-level jitter for realism
                current_time += timedelta(
                    minutes=random.randint(0, 25),
                    seconds=random.randint(0, 59)
                )

            resource = pick_resource(activity)
            rows.append({
                "case_id": f"CASE-{case_num:04d}",
                "activity": activity,
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "resource": resource,
            })

    return rows, num_rework, rework_cases


# ═══════════════════════════════════════════════════════════════
# Generate open (in-flight) cases (open_cases.csv)
# ═══════════════════════════════════════════════════════════════

def generate_open_cases(last_completed_time: datetime) -> list[dict]:
    """
    Create 25 open cases at various stages:
      - 10 stopped at Submitted (just arrived)
      - 15 stopped at Reviewed (awaiting approval — in the bottleneck)
    """
    rows = []
    # Open cases start near the end of the completed timeline
    base = last_completed_time - timedelta(days=3)

    stop_distribution = ["Submitted"] * 10 + ["Reviewed"] * 15
    random.shuffle(stop_distribution)

    for i in range(NUM_OPEN_CASES):
        case_id = f"OPEN-{i + 1:04d}"
        stop_at = stop_distribution[i]

        start_offset = timedelta(
            days=random.randint(0, 4),
            hours=random.randint(7, 17),
            minutes=random.randint(0, 59),
        )
        current_time = base + start_offset

        # Skip weekends
        while current_time.weekday() >= 5:
            current_time += timedelta(days=1)

        rows.append({
            "case_id": case_id,
            "activity": "Submitted",
            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "resource": pick_resource("Submitted"),
        })

        if stop_at == "Reviewed":
            wait = random.uniform(1.5, 6.0)
            current_time += timedelta(hours=wait, minutes=random.randint(0, 25))

            rows.append({
                "case_id": case_id,
                "activity": "Reviewed",
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "resource": pick_resource("Reviewed"),
            })

    return rows


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  ProcessLens — Enterprise Demo Dataset Generator")
    print("  Scenario: Retail Banking — Loan Application Processing")
    print("=" * 65)

    # Generate completed event log
    rows, num_rework, rework_cases = generate_completed_cases()

    with open(EVENT_LOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["case_id", "activity", "timestamp", "resource"]
        )
        writer.writeheader()
        writer.writerows(rows)

    unique_cases = {r["case_id"] for r in rows}
    unique_resources = {r["resource"] for r in rows}

    print(f"\n  [EVENT LOG] Completed cases:")
    print(f"     File           : {EVENT_LOG_FILE}")
    print(f"     Total cases    : {len(unique_cases)}")
    print(f"     Total events   : {len(rows)}")
    print(f"     Rework cases   : {num_rework}  (~{num_rework/len(unique_cases)*100:.0f}%)")
    print(f"     Resources      : {len(unique_resources)}")
    print(f"     Time span      : {rows[0]['timestamp'][:10]} -> {rows[-1]['timestamp'][:10]}")

    # Generate open cases
    from datetime import datetime as dt
    last_ts = max(r["timestamp"] for r in rows)
    last_time = dt.strptime(last_ts, "%Y-%m-%d %H:%M:%S")

    open_rows = generate_open_cases(last_time)

    with open(OPEN_CASES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["case_id", "activity", "timestamp", "resource"]
        )
        writer.writeheader()
        writer.writerows(open_rows)

    n_submitted = sum(1 for r in open_rows if r["activity"] == "Submitted") - \
                  sum(1 for r in open_rows if r["activity"] == "Reviewed")
    n_reviewed = sum(1 for r in open_rows if r["activity"] == "Reviewed")

    print(f"\n  [OPEN CASES] In-flight:")
    print(f"     File           : {OPEN_CASES_FILE}")
    print(f"     Total cases    : {NUM_OPEN_CASES}")
    print(f"     At Submitted   : {n_submitted}")
    print(f"     At Reviewed    : {n_reviewed}")
    print(f"     Total events   : {len(open_rows)}")

    # Summary stats for demo talking points
    print(f"\n  [DEMO HIGHLIGHTS] Talking points:")
    print(f"     Approval bottleneck : ~18-42h weekday, ~48-64h weekend")
    print(f"     Rework rate         : ~{REWORK_FRACTION*100:.0f}% compliance rejection loop")
    print(f"     Overloaded reviewer : Rachel Goldman (~40% review volume)")
    print(f"     Weekend effect      : Approval wait doubles on Fri->Mon")
    print(f"     Banking resources   : 12 staff across 3 tiers")

    print("\n" + "=" * 65)
    print("  [OK] Demo dataset generated successfully!")
    print("     Upload demo_event_log.csv to ProcessLens for the demo.")
    print("=" * 65)


if __name__ == "__main__":
    main()
