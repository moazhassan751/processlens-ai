import io
import json
import os
import shutil
import sys
from pathlib import Path
import pandas as pd
from starlette.testclient import TestClient

PROJECT_ROOT = Path("d:/Process Lens").resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app
from backend.routers.upload import (
    sanitize_cell_value,
    sanitize_dataframe_for_csv,
    _is_numeric,
)

def run_security_tests():
    print("=" * 65)
    print("      PROCESSLENS — PHASE H2 SECURITY TEST SUITE      ")
    print("=" * 65)

    # -------------------------------------------------------------------
    # TEST 1: Equals-prefix injection
    # -------------------------------------------------------------------
    val1 = '=cmd|"/C calc"!A1'
    out1 = sanitize_cell_value(val1)
    assert out1 == '\'=cmd|"/C calc"!A1', f"TEST 1 Failed: got {repr(out1)}"
    print(f"  [PASS] TEST 1: {val1} -> {out1}")

    # -------------------------------------------------------------------
    # TEST 2: Plus-prefix injection
    # -------------------------------------------------------------------
    val2 = '+cmd|"/C calc"!A1'
    out2 = sanitize_cell_value(val2)
    assert out2 == '\'+cmd|"/C calc"!A1', f"TEST 2 Failed: got {repr(out2)}"
    print(f"  [PASS] TEST 2: {val2} -> {out2}")

    # -------------------------------------------------------------------
    # TEST 3: At-prefix injection
    # -------------------------------------------------------------------
    val3 = '@SUM(A1:A10)'
    out3 = sanitize_cell_value(val3)
    assert out3 == '\'@SUM(A1:A10)', f"TEST 3 Failed: got {repr(out3)}"
    print(f"  [PASS] TEST 3: {val3} -> {out3}")

    # -------------------------------------------------------------------
    # TEST 4: Minus-prefix string injection
    # -------------------------------------------------------------------
    val4 = '-cmd|"/C calc"!A1'
    out4 = sanitize_cell_value(val4)
    assert out4 == '\'-cmd|"/C calc"!A1', f"TEST 4 Failed: got {repr(out4)}"
    print(f"  [PASS] TEST 4: {val4} -> {out4}")

    # -------------------------------------------------------------------
    # TEST 5: Genuine numeric negative value
    # -------------------------------------------------------------------
    val5_int = -5
    out5_int = sanitize_cell_value(val5_int)
    assert out5_int == -5 and isinstance(out5_int, int), f"TEST 5a Failed: got {out5_int}"

    val5_str = "-5"
    out5_str = sanitize_cell_value(val5_str)
    assert out5_str == "-5", f"TEST 5b Failed: got {out5_str}"

    val5_float = -12.34
    out5_float = sanitize_cell_value(val5_float)
    assert out5_float == -12.34, f"TEST 5c Failed: got {out5_float}"
    print(f"  [PASS] TEST 5: Numeric {val5_int} -> {out5_int}, String '{val5_str}' -> '{out5_str}', Float {val5_float} -> {out5_float}")

    # -------------------------------------------------------------------
    # TEST 6: Timestamp preservation
    # -------------------------------------------------------------------
    val6 = "2026-09-01 10:00:00"
    out6 = sanitize_cell_value(val6, is_timestamp_col=True)
    assert out6 == "2026-09-01 10:00:00", f"TEST 6 Failed: got {out6}"
    print(f"  [PASS] TEST 6: Timestamp {val6} -> {out6}")

    # -------------------------------------------------------------------
    # TEST 7: Normal text preservation
    # -------------------------------------------------------------------
    normal_texts = ["Reviewed", "Submit Application", "CASE-123", "Alice Johnson"]
    for txt in normal_texts:
        out = sanitize_cell_value(txt)
        assert out == txt, f"TEST 7 Failed for {txt}: got {out}"
    print(f"  [PASS] TEST 7: Normal texts {normal_texts} preserved unchanged.")

    # -------------------------------------------------------------------
    # TEST 8: Realistic uploaded event log via /api/upload
    # -------------------------------------------------------------------
    app = create_app()
    client = TestClient(app)
    # Preserve predictions.json across upload test
    predictions_backup = None
    pred_path = PROJECT_ROOT / "predictions.json"
    if pred_path.exists():
        predictions_backup = pred_path.read_bytes()

    # Build 10 valid cases with 1 malicious case_id and 1 malicious resource
    rows = []
    for i in range(1, 11):
        if i == 1:
            cid = '=cmd|"/C calc"!A1'
            res = '+MaliciousAdmin'
        elif i == 2:
            cid = '@CaseTwo'
            res = '-ReviewerText'
        else:
            cid = f"CASE-{i:04d}"
            res = "Alice Johnson"

        rows.append({
            "case_id": cid,
            "activity": "Submitted",
            "timestamp": f"2026-09-01 0{i % 9 + 1}:00:00",
            "resource": res,
        })
        rows.append({
            "case_id": cid,
            "activity": "Reviewed",
            "timestamp": f"2026-09-01 0{i % 9 + 1}:30:00",
            "resource": res,
        })

    upload_df = pd.DataFrame(rows)
    csv_bytes = upload_df.to_csv(index=False).encode("utf-8")

    # Upload to test_security_project
    test_proj = "test_sec_proj"
    resp = client.post(
        f"/api/upload?project_id={test_proj}",
        files={"file": ("malicious_test.csv", io.BytesIO(csv_bytes), "text/csv")},
    )

    assert resp.status_code == 200, f"Upload failed: {resp.status_code} - {resp.text}"
    resp_data = resp.json()
    assert resp_data["accepted"] is True
    assert resp_data["row_count"] == 20
    print(f"  [OK] /api/upload accepted valid 10-case CSV ({resp_data['row_count']} rows)")

    # Verify persisted project file
    proj_csv_path = PROJECT_ROOT / "storage" / "projects" / test_proj / "uploads" / "event_log.csv"
    assert proj_csv_path.exists(), f"Project upload missing at {proj_csv_path}"

    with open(str(proj_csv_path), "r", encoding="utf-8") as f:
        proj_csv_content = f.read()

    # Raw content inspection: must contain sanitized quote
    assert "'=cmd" in proj_csv_content or "\"'=cmd" in proj_csv_content, "Sanitized quote missing in project CSV"
    assert "'+MaliciousAdmin" in proj_csv_content, "Plus-prefix quote missing in project CSV"
    assert "'@CaseTwo" in proj_csv_content, "At-prefix quote missing in project CSV"
    assert "'-ReviewerText" in proj_csv_content, "Minus-prefix quote missing in project CSV"

    # Make sure unescaped formulas do NOT exist at column start
    lines = proj_csv_content.splitlines()
    for line in lines[1:]:  # skip header
        parts = line.split(",")
        # case_id is parts[0]
        assert not parts[0].startswith("=cmd"), f"Unsanitized formula in case_id: {parts[0]}"
        assert not parts[0].startswith("@CaseTwo"), f"Unsanitized @ in case_id: {parts[0]}"

    print(f"  [PASS] Persisted project event_log.csv contains neutralized values.")

    # Verify root event_log.csv
    root_csv_path = PROJECT_ROOT / "event_log.csv"
    with open(str(root_csv_path), "r", encoding="utf-8") as f:
        root_csv_content = f.read()
    assert "'=cmd" in root_csv_content or "\"'=cmd" in root_csv_content
    print(f"  [PASS] Active root event_log.csv contains neutralized values.")

    # Clean up test project directory
    proj_dir = PROJECT_ROOT / "storage" / "projects" / test_proj
    if proj_dir.exists():
        shutil.rmtree(str(proj_dir), ignore_errors=True)

    # Restore synthetic dataset
    reset_resp = client.post("/api/reset-to-synthetic")
    assert reset_resp.status_code == 200
    if predictions_backup is not None:
        pred_path.write_bytes(predictions_backup)
    print("  Cleaned up test project and restored synthetic dataset.")

    print("\n" + "=" * 65)
    print(">>> ALL 8 PHASE H2 SECURITY TESTS PASSED (100%) <<<")
    print("=" * 65)

if __name__ == "__main__":
    run_security_tests()
