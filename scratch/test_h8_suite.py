"""
ProcessLens — Phase H8 Verification Test Suite
================================================
Comprehensive verification of Interactive Event Log Filtering on the Discovery Tab:
- Test 1: Unfiltered parity — /api/discovery and /api/process-graph with zero parameters
- Test 2: Filter options endpoint — /api/discovery/filter-options bounds and resources
- Test 3: Date range filtering — start_date and end_date case-level filtering
- Test 4: Resource filtering — repeatable / comma-separated resource matching
- Test 5: Case duration filtering — min_duration_hours and max_duration_hours cycle times
- Test 6: Multi-filter combination — combined date, resource, and duration criteria
- Test 7: Low-case graceful handling — < 2 matching cases returns 200 with clear message, no crash
- Test 8: Historical run isolation — filtering works correctly on dedicated historical run
- Test 9: Zero disk mutation guarantee — event_log.csv checksum is unchanged before and after
"""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app
from backend.config import OUTPUT_FILES
from backend.services import storage as storage_svc

client = TestClient(app)


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def test_1_unfiltered_parity():
    """Test 1: Unfiltered calls produce identical response structure and correct defaults."""
    print("\n[TEST 1] Testing unfiltered baseline parity...")
    r_disc = client.get("/api/discovery")
    assert r_disc.status_code == 200, r_disc.text
    d_data = r_disc.json()
    assert d_data.get("available") is True
    assert "bottlenecks" in d_data
    assert len(d_data["bottlenecks"]) > 0
    assert d_data.get("fallback") is False
    # When unfiltered, 'filtered' flag is not set or false
    assert not d_data.get("filtered")

    r_graph = client.get("/api/process-graph")
    assert r_graph.status_code == 200, r_graph.text
    g_data = r_graph.json()
    assert g_data.get("available") is True
    assert "nodes" in g_data
    assert "edges" in g_data
    assert len(g_data["nodes"]) > 0
    assert len(g_data["edges"]) > 0
    print("  [PASS] Unfiltered /api/discovery and /api/process-graph return standard baseline structure.")


def test_2_filter_options():
    """Test 2: GET /api/discovery/filter-options returns dynamic bounds from active event log."""
    print("\n[TEST 2] Testing /api/discovery/filter-options endpoint...")
    res = client.get("/api/discovery/filter-options")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data.get("available") is True
    assert "resources" in data and isinstance(data["resources"], list)
    assert len(data["resources"]) >= 2
    assert "Alice Johnson" in data["resources"]

    date_range = data.get("date_range", {})
    assert "min" in date_range and "max" in date_range
    assert "min_date" in date_range and "max_date" in date_range
    assert date_range["min_date"] <= date_range["max_date"]

    dur = data.get("duration_hours", {})
    assert "min" in dur and "max" in dur
    assert dur["min"] <= dur["max"]
    assert dur["min"] > 0

    assert data.get("total_cases") == 300
    print(f"  [PASS] Filter options: {len(data['resources'])} resources, date span {date_range['min_date']} to {date_range['max_date']}, duration {dur['min']}h to {dur['max']}h.")


def test_3_date_range_filtering():
    """Test 3: Date range filtering on case start timestamps."""
    print("\n[TEST 3] Testing date range filtering...")
    # Load ground truth via pandas
    df = pd.read_csv("event_log.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    case_starts = df.groupby("case_id")["timestamp"].min()

    start_filter = "2025-01-15"
    end_filter = "2025-01-25"

    expected_cases = set(
        case_starts[
            (case_starts >= pd.to_datetime(start_filter)) &
            (case_starts <= pd.to_datetime(end_filter) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1))
        ].index
    )
    expected_count = len(expected_cases)
    assert expected_count > 0 and expected_count < 300

    res = client.get(f"/api/discovery?start_date={start_filter}&end_date={end_filter}")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data.get("filtered") is True
    assert data.get("total_cases") == 300
    assert data.get("matched_cases") == expected_count, (
        f"Expected {expected_count} matched cases, got {data.get('matched_cases')}"
    )
    assert len(data.get("bottlenecks", [])) > 0

    # Also verify /api/process-graph
    g_res = client.get(f"/api/process-graph?start_date={start_filter}&end_date={end_filter}")
    assert g_res.status_code == 200, g_res.text
    g_data = g_res.json()
    assert g_data.get("matched_cases") == expected_count
    assert len(g_data.get("nodes", [])) > 0
    print(f"  [PASS] Date range [{start_filter} to {end_filter}]: exactly {expected_count} of 300 cases matched.")


def test_4_resource_filtering():
    """Test 4: Resource filtering (repeatable and comma-separated)."""
    print("\n[TEST 4] Testing resource filtering...")
    df = pd.read_csv("event_log.csv")
    alice_cases = set(df[df["resource"] == "Alice Johnson"]["case_id"].unique())
    expected_alice = len(alice_cases)

    # Test single resource
    res1 = client.get("/api/discovery?resource=Alice%20Johnson")
    assert res1.status_code == 200, res1.text
    d1 = res1.json()
    assert d1.get("filtered") is True
    assert d1.get("matched_cases") == expected_alice, (
        f"Expected {expected_alice}, got {d1.get('matched_cases')}"
    )

    # Test multiple resources (comma-separated)
    alice_bob_cases = set(df[df["resource"].isin(["Alice Johnson", "Bob Smith"])]["case_id"].unique())
    expected_alice_bob = len(alice_bob_cases)

    res2 = client.get("/api/discovery?resource=Alice%20Johnson,Bob%20Smith")
    assert res2.status_code == 200, res2.text
    d2 = res2.json()
    assert d2.get("matched_cases") == expected_alice_bob

    # Test multiple resources (repeatable query param)
    res3 = client.get("/api/discovery?resource=Alice%20Johnson&resource=Bob%20Smith")
    assert res3.status_code == 200, res3.text
    d3 = res3.json()
    assert d3.get("matched_cases") == expected_alice_bob
    print(f"  [PASS] Resource filter: Alice Johnson = {expected_alice} cases, Alice + Bob = {expected_alice_bob} cases.")


def test_5_duration_filtering():
    """Test 5: Case cycle time duration range filtering."""
    print("\n[TEST 5] Testing duration filtering...")
    df = pd.read_csv("event_log.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    durations = (df.groupby("case_id")["timestamp"].max() - df.groupby("case_id")["timestamp"].min()).dt.total_seconds() / 3600.0

    min_dur = 35.0
    max_dur = 45.0
    expected_dur_cases = set(durations[(durations >= min_dur) & (durations <= max_dur)].index)
    expected_dur_count = len(expected_dur_cases)
    assert expected_dur_count > 0 and expected_dur_count < 300

    res = client.get(f"/api/discovery?min_duration_hours={min_dur}&max_duration_hours={max_dur}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("filtered") is True
    assert data.get("matched_cases") == expected_dur_count

    # Check graph
    g_res = client.get(f"/api/process-graph?min_duration_hours={min_dur}&max_duration_hours={max_dur}")
    assert g_res.status_code == 200
    assert g_res.json().get("matched_cases") == expected_dur_count
    print(f"  [PASS] Duration range [{min_dur}h to {max_dur}h]: exactly {expected_dur_count} of 300 cases matched.")


def test_6_combined_filtering():
    """Test 6: Multi-parameter combined filtering."""
    print("\n[TEST 6] Testing combined filtering (Date + Resource + Duration)...")
    df = pd.read_csv("event_log.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    agg = df.groupby("case_id").agg(
        first_ts=("timestamp", "min"),
        last_ts=("timestamp", "max"),
        res_set=("resource", lambda s: set(s.dropna())),
    )
    agg["duration_hours"] = (agg["last_ts"] - agg["first_ts"]).dt.total_seconds() / 3600.0

    mask = (
        (agg["first_ts"] >= pd.to_datetime("2025-01-10")) &
        (agg["first_ts"] <= pd.to_datetime("2025-01-30 23:59:59")) &
        (agg["res_set"].apply(lambda s: "Carol Lee" in s)) &
        (agg["duration_hours"] >= 30.0) &
        (agg["duration_hours"] <= 50.0)
    )
    expected_combined = len(agg[mask])
    assert expected_combined >= 2, f"Need at least 2 cases for valid discovery test, found {expected_combined}"

    url = "/api/discovery?start_date=2025-01-10&end_date=2025-01-30&resource=Carol%20Lee&min_duration_hours=30.0&max_duration_hours=50.0"
    res = client.get(url)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("matched_cases") == expected_combined
    assert len(data.get("bottlenecks", [])) > 0
    assert "paths" in data and len(data["paths"]) > 0
    print(f"  [PASS] Combined multi-filter matched exactly {expected_combined} cases with recomputed bottlenecks & paths.")


def test_7_low_cases_graceful_handling():
    """Test 7: Filtering matching fewer than 2 cases returns graceful message and empty graph without error."""
    print("\n[TEST 7] Testing low-case count (< 2 cases) graceful handling...")
    # An impossible filter: duration > 999 hours
    url_disc = "/api/discovery?min_duration_hours=999.0"
    res_disc = client.get(url_disc)
    assert res_disc.status_code == 200, res_disc.text
    d_data = res_disc.json()

    assert d_data.get("matched_cases") == 0
    assert d_data.get("total_cases") == 300
    assert d_data.get("process_map_exists") is False
    assert d_data.get("bottlenecks") == []
    assert d_data.get("paths") == []
    assert "Not enough cases match these filters to discover a process" in d_data.get("message", "")

    url_graph = "/api/process-graph?min_duration_hours=999.0"
    res_graph = client.get(url_graph)
    assert res_graph.status_code == 200, res_graph.text
    g_data = res_graph.json()
    assert g_data.get("matched_cases") == 0
    assert g_data.get("nodes") == []
    assert g_data.get("edges") == []
    assert "Not enough cases match these filters to discover a process" in g_data.get("message", "")

    # Exactly 1 case matched (e.g. narrow time window targeting a single specific case)
    df = pd.read_csv("event_log.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    first_case_time = df.groupby("case_id")["timestamp"].min().sort_values().iloc[0]
    narrow_start = (first_case_time - pd.Timedelta(seconds=1)).isoformat()
    narrow_end = (first_case_time + pd.Timedelta(seconds=1)).isoformat()

    res_1case = client.get(f"/api/discovery?start_date={narrow_start}&end_date={narrow_end}")
    assert res_1case.status_code == 200
    d_1case = res_1case.json()
    assert d_1case.get("matched_cases") == 1
    assert "Not enough cases match these filters to discover a process" in d_1case.get("message", "")
    assert d_1case.get("bottlenecks") == []
    print("  [PASS] 0 and 1 case matches return HTTP 200 with graceful message and safe empty collections.")


def test_8_historical_run_isolation():
    """Test 8: Filters apply to historical runs without mutating or cross-contaminating default project."""
    print("\n[TEST 8] Testing historical run isolation...")
    project_id = "test_h8_proj"
    run_id = "run_hist_h8"
    run_dir = storage_svc.create_run_dir(project_id, run_id)

    # Copy standard event log into run directory
    shutil.copyfile("event_log.csv", run_dir / "input" / "event_log.csv")

    try:
        # Check filter options on historical run
        opts_res = client.get(f"/api/discovery/filter-options?project_id={project_id}&run_id={run_id}")
        assert opts_res.status_code == 200
        assert opts_res.json().get("total_cases") == 300

        # Filter historical run by resource
        f_res = client.get(f"/api/discovery?project_id={project_id}&run_id={run_id}&resource=Alice%20Johnson")
        assert f_res.status_code == 200
        f_data = f_res.json()
        assert f_data.get("matched_cases") == 147
        assert f_data.get("fallback") is False

        # Verify root project is unaffected
        root_res = client.get("/api/discovery")
        assert root_res.status_code == 200
        assert not root_res.json().get("filtered")
    finally:
        shutil.rmtree(run_dir.parent.parent, ignore_errors=True)
    print("  [PASS] Historical run filtering is fully isolated and does not cross-contaminate.")


def test_9_zero_disk_mutation():
    """Test 9: Guaranteed zero disk writes during filtering."""
    print("\n[TEST 9] Testing zero disk mutation guarantee...")
    log_path = Path("event_log.csv")
    before_hash = hash_file(log_path)
    before_mtime = log_path.stat().st_mtime

    # Run 5 diverse filter requests
    client.get("/api/discovery?start_date=2025-01-10&end_date=2025-01-20")
    client.get("/api/discovery?resource=Eva%20Martinez")
    client.get("/api/discovery?min_duration_hours=20&max_duration_hours=40")
    client.get("/api/process-graph?resource=Frank%20Chen")
    client.get("/api/discovery/paths?min_duration_hours=50")

    after_hash = hash_file(log_path)
    after_mtime = log_path.stat().st_mtime

    assert before_hash == after_hash, "event_log.csv content was mutated during filtering!"
    assert before_mtime == after_mtime, "event_log.csv timestamp was modified during filtering!"
    print(f"  [PASS] SHA-256 ({before_hash[:12]}...) and mtime completely unchanged across 5 filtered requests.")


def run_all_h8_tests():
    print("=" * 70)
    print("PROCESSLENS — PHASE H8 INTERACTIVE DISCOVERY FILTERING TEST SUITE")
    print("=" * 70)

    test_1_unfiltered_parity()
    test_2_filter_options()
    test_3_date_range_filtering()
    test_4_resource_filtering()
    test_5_duration_filtering()
    test_6_combined_filtering()
    test_7_low_cases_graceful_handling()
    test_8_historical_run_isolation()
    test_9_zero_disk_mutation()

    print("\n" + "=" * 70)
    print(">>> ALL 9 PHASE H8 TESTS PASSED (100%) <<<")
    print("=" * 70)


if __name__ == "__main__":
    run_all_h8_tests()
