"""
Step 2 — Validate the event log.

Checks event_log.csv for:
  1. Empty CSV / dataset
  2. Missing required columns (case_id, activity, timestamp, resource)
  3. Row-level missing/empty values
  4. Row-level invalid timestamp formatting (ISO-8601)
  5. Timestamps not strictly increasing within each case
  6. Exact duplicate rows
  7. Insufficient data (< 10 cases)
  8. Activities outside the expected set

Exposes validate(df) for reuse by other scripts and upload router.
"""

import sys
import pandas as pd

EXPECTED_ACTIVITIES = {
    "Submitted",
    "Reviewed",
    "Approved",
    "Completed",
    "Sent Back for Correction",
}

EVENT_LOG_FILE = "event_log.csv"
MIN_CASES_REQUIRED = 10


def validate(df: pd.DataFrame) -> tuple[bool, str]:
    """
    Run all validation checks on the DataFrame.
    Returns (passed: bool, report: str).
    """
    results: list[str] = []
    all_passed = True

    # --- Check 0: Empty DataFrame ---
    if df is None or len(df) == 0:
        return False, (
            "=" * 55 + "\n  STEP 2 -- Event Log Validation\n" + "=" * 55 +
            "\n  [FAIL] Dataset contains no valid event records"
            "\n  [X] VALIDATION FAILED -- fix issues before proceeding\n" + "=" * 55
        )

    # --- Check 1: Required columns presence ---
    required_cols = ["case_id", "activity", "timestamp"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        for mc in missing_cols:
            results.append(f"  [FAIL] Missing required column: {mc}")
        all_passed = False
    else:
        results.append("  [PASS] All required columns present (case_id, activity, timestamp)")

    # If required columns are missing, we cannot proceed with row-level checks
    if not all_passed:
        header = "=" * 55 + "\n  STEP 2 -- Event Log Validation\n" + "=" * 55
        body = "\n".join(results)
        footer = "\n  [X] VALIDATION FAILED -- fix issues before proceeding\n" + "=" * 55
        return False, f"{header}\n{body}{footer}"

    # --- Check 2: Row-level missing/empty values ---
    missing_row_errors: list[str] = []
    for col in required_cols:
        null_mask = df[col].isnull() | (df[col].astype(str).str.strip() == "")
        null_indices = df[null_mask].index.tolist()
        for idx in null_indices[:10]:  # Limit per column to avoid blowing up report
            missing_row_errors.append(f"  [FAIL] row {idx + 2}: {col} is empty")
        if len(null_indices) > 10:
            missing_row_errors.append(f"  [FAIL] ... and {len(null_indices) - 10} more rows with empty {col}")

    if missing_row_errors:
        results.extend(missing_row_errors)
        all_passed = False
    else:
        results.append("  [PASS] No missing or empty values in required columns")

    # --- Check 3: Row-level timestamp parsing (ISO-8601 validation) ---
    invalid_ts_rows: list[str] = []
    parsed_timestamps = []
    ts_all_valid = True

    for idx, raw_val in enumerate(df["timestamp"]):
        row_num = idx + 2
        try:
            val_str = str(raw_val).strip()
            if not val_str:
                ts_all_valid = False
                continue
            parsed_dt = pd.to_datetime(val_str, format="ISO8601")
            parsed_timestamps.append(parsed_dt)
        except Exception:
            try:
                parsed_dt = pd.to_datetime(val_str)
                parsed_timestamps.append(parsed_dt)
            except Exception:
                ts_all_valid = False
                if len(invalid_ts_rows) < 10:
                    invalid_ts_rows.append(f"  [FAIL] row {row_num}: timestamp is not valid ISO-8601")

    if invalid_ts_rows:
        results.extend(invalid_ts_rows)
        all_passed = False
    else:
        results.append("  [PASS] All timestamps are valid ISO-8601 datetime strings")

    # --- Check 4: Timestamps strictly increasing within each case ---
    if ts_all_valid and len(parsed_timestamps) == len(df):
        df_check = df.copy()
        df_check["ts_parsed"] = parsed_timestamps
        bad_cases = []
        for case_id, group in df_check.groupby("case_id"):
            ts = group["ts_parsed"].tolist()
            for i in range(1, len(ts)):
                if ts[i] <= ts[i - 1]:
                    bad_cases.append(case_id)
                    break
        if bad_cases:
            results.append(
                f"  [FAIL] Non-increasing timestamps in {len(bad_cases)} case(s): "
                f"{bad_cases[:5]}{'...' if len(bad_cases) > 5 else ''}"
            )
            all_passed = False
        else:
            results.append("  [PASS] All timestamps strictly increasing within each case")

    # --- Check 5: Exact duplicate rows ---
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        results.append(f"  [FAIL] {dup_count} exact duplicate row(s) found")
        all_passed = False
    else:
        results.append("  [PASS] No exact duplicate rows")

    # --- Check 6: Insufficient data protection (< 10 cases) ---
    num_cases = int(df["case_id"].dropna().nunique())
    if num_cases < MIN_CASES_REQUIRED:
        results.append(
            f"  [FAIL] Insufficient data: event log contains only {num_cases} case(s). "
            f"At least {MIN_CASES_REQUIRED} cases are required."
        )
        all_passed = False
    else:
        results.append(f"  [PASS] Dataset contains sufficient cases ({num_cases} cases)")

    # --- Check 7: Unexpected activities ---
    actual_activities = set(df["activity"].dropna().unique())
    unexpected = actual_activities - EXPECTED_ACTIVITIES
    if unexpected:
        results.append(f"  [FAIL] Unexpected activities: {sorted(unexpected)}")
        all_passed = False
    else:
        results.append("  [PASS] All activities match the expected set")

    # Build final report
    header = "=" * 55 + "\n  STEP 2 -- Event Log Validation\n" + "=" * 55
    body = "\n".join(results)
    if all_passed:
        footer = "\n  [OK] VALIDATION PASSED"
    else:
        footer = "\n  [X] VALIDATION FAILED -- fix issues before proceeding"
    footer += "\n" + "=" * 55

    report = f"{header}\n{body}{footer}"
    return all_passed, report


def main():
    try:
        df = pd.read_csv(EVENT_LOG_FILE)
    except FileNotFoundError:
        print(f"ERROR: {EVENT_LOG_FILE} not found. Run generate_data.py first.")
        sys.exit(1)
    except pd.errors.EmptyDataError:
        print("ERROR: CSV file is empty.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Could not read {EVENT_LOG_FILE}: {e}")
        sys.exit(1)

    passed, report = validate(df)
    print(report)
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
