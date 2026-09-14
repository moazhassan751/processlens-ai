"""
ProcessLens — Phase H4 Concurrent-Run Guard Verification Suite
=============================================================
Tests 1 through 10 as specified in H4 requirements:
  TEST 1: Normal first run succeeds, initial status valid, pipeline starts
  TEST 2: Back-to-back second run while RUNNING returns HTTP 409
  TEST 3: Existing QUEUED run returns HTTP 409 identifying queued run_id
  TEST 4: Different project allowed while another project is RUNNING
  TEST 5: COMPLETED run does not block new run
  TEST 6: FAILED run does not block new run
  TEST 7: CANCELLED run does not block new run
  TEST 8: Rejected request leaves zero extra run records in memory or on disk
  TEST 9: Existing run status and run_id remain intact after rejection
  TEST 10: Near-simultaneous concurrent requests: exactly one succeeds, one rejected with 409
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app
from backend.models import RunStatusEnum
from backend.services import pipeline_runner as runner
from backend.services import storage as storage_svc


def cleanup_test_project(proj_id: str):
    proj_dir = storage_svc.STORAGE_ROOT / "projects" / proj_id
    if proj_dir.exists():
        shutil.rmtree(proj_dir, ignore_errors=True)
    # Also clean up memory
    to_remove = [k for k, r in runner._runs.items() if r.project_id == proj_id]
    for k in to_remove:
        del runner._runs[k]


async def _fast_bg_run_all(run):
    run.status = RunStatusEnum.RUNNING
    await asyncio.sleep(0.05)


async def _fast_bg_run_single(run, phase):
    run.status = RunStatusEnum.RUNNING
    await asyncio.sleep(0.05)


def run_sync_tests():
    app = create_app()

    print("=" * 65, flush=True)
    print("      PROCESSLENS — PHASE H4 CONCURRENT-RUN GUARD SUITE       ", flush=True)
    print("=" * 65, flush=True)

    with patch("backend.routers.pipeline.runner.run_all_phases", side_effect=_fast_bg_run_all), \
         patch("backend.routers.pipeline.runner.run_single_phase", side_effect=_fast_bg_run_single):

        client = TestClient(app)

        # -------------------------------------------------------------------
        # TEST 1: Normal first run
        # -------------------------------------------------------------------
        print("\n--- TEST 1: Normal First Run ---", flush=True)
        proj_1 = "proj_h4_test1"
        cleanup_test_project(proj_1)
        res1 = client.post(f"/api/run/all?project_id={proj_1}")
        assert res1.status_code == 200, f"Expected 200, got {res1.status_code}: {res1.text}"
        body1 = res1.json()
        assert "run_id" in body1, f"Missing run_id in response: {body1}"
        assert body1.get("status") in ("QUEUED", "RUNNING"), f"Unexpected status: {body1.get('status')}"
        run_obj1 = runner.get_run(body1["run_id"])
        assert run_obj1 is not None, "Run object must exist in runner registry"
        run_obj1.status = RunStatusEnum.COMPLETED
        print(f"  [PASS] Test 1: Normal first run created {body1['run_id']} with initial status {body1.get('status')}", flush=True)

        # -------------------------------------------------------------------
        # TEST 2: Back-to-back second run while RUNNING
        # -------------------------------------------------------------------
        print("\n--- TEST 2: Back-to-back Second Run while RUNNING ---", flush=True)
        proj_2 = "proj_h4_test2"
        cleanup_test_project(proj_2)
        # Controlled active run in RUNNING status
        active_run = runner.create_run(proj_2)
        active_run.status = RunStatusEnum.RUNNING

        res2 = client.post(f"/api/run/all?project_id={proj_2}")
        assert res2.status_code == 409, f"Expected 409, got {res2.status_code}: {res2.text}"
        body2 = res2.json()
        assert active_run.run_id in body2.get("detail", ""), f"Response detail must name {active_run.run_id}: {body2}"
        assert "already in progress" in body2.get("detail", "").lower(), f"Response detail must indicate progress: {body2}"
        assert active_run.status == RunStatusEnum.RUNNING, "Existing run status must remain intact"
        print(f"  [PASS] Test 2: Second run returned HTTP 409 naming active run {active_run.run_id}", flush=True)

        # -------------------------------------------------------------------
        # TEST 3: Existing QUEUED run
        # -------------------------------------------------------------------
        print("\n--- TEST 3: Existing QUEUED Run ---", flush=True)
        proj_3 = "proj_h4_test3"
        cleanup_test_project(proj_3)
        queued_run = runner.create_run(proj_3)
        queued_run.status = RunStatusEnum.QUEUED

        res3 = client.post(f"/api/run/phase1?project_id={proj_3}")
        assert res3.status_code == 409, f"Expected 409, got {res3.status_code}: {res3.text}"
        body3 = res3.json()
        assert queued_run.run_id in body3.get("detail", ""), f"Response detail must name {queued_run.run_id}: {body3}"
        assert "already in progress" in body3.get("detail", "").lower()
        print(f"  [PASS] Test 3: Run request blocked by QUEUED run {queued_run.run_id} with HTTP 409", flush=True)

        # -------------------------------------------------------------------
        # TEST 4: Different project allowed
        # -------------------------------------------------------------------
        print("\n--- TEST 4: Different Project Allowed ---", flush=True)
        proj_4a = "proj_h4_test4_a"
        proj_4b = "proj_h4_test4_b"
        cleanup_test_project(proj_4a)
        cleanup_test_project(proj_4b)

        run_4a = runner.create_run(proj_4a)
        run_4a.status = RunStatusEnum.RUNNING

        res4b = client.post(f"/api/run/all?project_id={proj_4b}")
        assert res4b.status_code == 200, f"Expected 200 for project B, got {res4b.status_code}: {res4b.text}"
        body4b = res4b.json()
        run_4b = runner.get_run(body4b["run_id"])
        assert run_4b is not None
        assert run_4a.status == RunStatusEnum.RUNNING, "Project A run must remain RUNNING"
        run_4b.status = RunStatusEnum.COMPLETED
        print(f"  [PASS] Test 4: Project B started {body4b['run_id']} while Project A was RUNNING", flush=True)

        # -------------------------------------------------------------------
        # TEST 5: COMPLETED run does not block
        # -------------------------------------------------------------------
        print("\n--- TEST 5: COMPLETED Run Does Not Block ---", flush=True)
        proj_5 = "proj_h4_test5"
        cleanup_test_project(proj_5)
        run_5 = runner.create_run(proj_5)
        run_5.status = RunStatusEnum.COMPLETED

        res5 = client.post(f"/api/run/phase2?project_id={proj_5}")
        assert res5.status_code == 200, f"Expected 200, got {res5.status_code}: {res5.text}"
        body5 = res5.json()
        run_5_new = runner.get_run(body5["run_id"])
        assert run_5_new is not None
        assert run_5_new.run_id != run_5.run_id
        run_5_new.status = RunStatusEnum.COMPLETED
        print(f"  [PASS] Test 5: COMPLETED run did not block new run {body5['run_id']}", flush=True)

        # -------------------------------------------------------------------
        # TEST 6: FAILED run does not block
        # -------------------------------------------------------------------
        print("\n--- TEST 6: FAILED Run Does Not Block ---", flush=True)
        proj_6 = "proj_h4_test6"
        cleanup_test_project(proj_6)
        run_6 = runner.create_run(proj_6)
        run_6.status = RunStatusEnum.FAILED

        res6 = client.post(f"/api/run/phase3?project_id={proj_6}")
        assert res6.status_code == 200, f"Expected 200, got {res6.status_code}: {res6.text}"
        body6 = res6.json()
        run_6_new = runner.get_run(body6["run_id"])
        assert run_6_new is not None
        assert run_6_new.run_id != run_6.run_id
        run_6_new.status = RunStatusEnum.COMPLETED
        print(f"  [PASS] Test 6: FAILED run did not block new run {body6['run_id']}", flush=True)

        # -------------------------------------------------------------------
        # TEST 7: CANCELLED run does not block
        # -------------------------------------------------------------------
        print("\n--- TEST 7: CANCELLED Run Does Not Block ---", flush=True)
        proj_7 = "proj_h4_test7"
        cleanup_test_project(proj_7)
        run_7 = runner.create_run(proj_7)
        run_7.status = RunStatusEnum.CANCELLED

        res7 = client.post(f"/api/run/all?project_id={proj_7}")
        assert res7.status_code == 200, f"Expected 200, got {res7.status_code}: {res7.text}"
        body7 = res7.json()
        run_7_new = runner.get_run(body7["run_id"])
        assert run_7_new is not None
        assert run_7_new.run_id != run_7.run_id
        run_7_new.status = RunStatusEnum.COMPLETED
        print(f"  [PASS] Test 7: CANCELLED run did not block new run {body7['run_id']}", flush=True)

        # -------------------------------------------------------------------
        # TEST 8: Rejected request leaves no extra run record
        # -------------------------------------------------------------------
        print("\n--- TEST 8: Rejected Request Leaves No Extra Run Record ---", flush=True)
        proj_8 = "proj_h4_test8"
        cleanup_test_project(proj_8)
        run_8 = runner.create_run(proj_8)
        run_8.status = RunStatusEnum.RUNNING

        mem_count_before = len([r for r in runner._runs.values() if r.project_id == proj_8])
        disk_count_before = len(storage_svc.list_runs(proj_8))

        res8 = client.post(f"/api/run/all?project_id={proj_8}")
        assert res8.status_code == 409, f"Expected 409, got {res8.status_code}"

        mem_count_after = len([r for r in runner._runs.values() if r.project_id == proj_8])
        disk_count_after = len(storage_svc.list_runs(proj_8))

        assert mem_count_after == mem_count_before == 1, f"Memory runs altered! Before: {mem_count_before}, After: {mem_count_after}"
        assert disk_count_after == disk_count_before, f"Disk runs altered! Before: {disk_count_before}, After: {disk_count_after}"
        print(f"  [PASS] Test 8: Exactly 1 run record remains in memory and disk after rejected request", flush=True)

        # -------------------------------------------------------------------
        # TEST 9: Existing run status remains intact
        # -------------------------------------------------------------------
        print("\n--- TEST 9: Existing Run Status Remains Intact ---", flush=True)
        proj_9 = "proj_h4_test9"
        cleanup_test_project(proj_9)
        run_9 = runner.create_run(proj_9)
        run_9.status = RunStatusEnum.RUNNING
        run_9.progress = 55
        run_9.current_stage = "ML Prediction Pipeline"

        res9 = client.post(f"/api/run/phase1?project_id={proj_9}")
        assert res9.status_code == 409

        assert run_9.status == RunStatusEnum.RUNNING
        assert run_9.progress == 55
        assert run_9.current_stage == "ML Prediction Pipeline"
        print(f"  [PASS] Test 9: Existing run {run_9.run_id} status, progress, and stage remained intact", flush=True)

        # -------------------------------------------------------------------
        # TEST 9b: Persisted RUNNING status on disk blocks new run
        # -------------------------------------------------------------------
        print("\n--- TEST 9b: Disk-Persisted RUNNING Status Blocks New Run ---", flush=True)
        proj_disk = "proj_h4_disk"
        cleanup_test_project(proj_disk)
        storage_svc.create_run_dir(proj_disk, "run_disk_active_01")
        storage_svc.save_run_metadata(proj_disk, "run_disk_active_01", status="RUNNING")

        res_disk = client.post(f"/api/run/all?project_id={proj_disk}")
        assert res_disk.status_code == 409, f"Expected 409, got {res_disk.status_code}: {res_disk.text}"
        assert "run_disk_active_01" in res_disk.json().get("detail", "")
        cleanup_test_project(proj_disk)
        print(f"  [PASS] Test 9b: Disk-persisted RUNNING run correctly blocked new run with HTTP 409", flush=True)

        # Cleanup test projects
        for p in [proj_1, proj_2, proj_3, proj_4a, proj_4b, proj_5, proj_6, proj_7, proj_8, proj_9, proj_disk]:
            cleanup_test_project(p)


# -------------------------------------------------------------------
# TEST 10: Concurrent Near-Simultaneous Requests
# -------------------------------------------------------------------
async def run_concurrent_test():
    print("\n--- TEST 10: Concurrent Near-Simultaneous Requests ---", flush=True)
    from httpx import ASGITransport, AsyncClient
    app = create_app()
    proj_10 = "proj_h4_concurrent"
    cleanup_test_project(proj_10)

    with patch("backend.routers.pipeline.runner.run_all_phases", side_effect=_fast_bg_run_all):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Fire 2 near-simultaneous requests
            req1 = client.post(f"/api/run/all?project_id={proj_10}")
            req2 = client.post(f"/api/run/all?project_id={proj_10}")

            res1, res2 = await asyncio.gather(req1, req2)

            statuses = [res1.status_code, res2.status_code]
            assert 200 in statuses, f"Expected one 200, got {statuses}"
            assert 409 in statuses, f"Expected one 409, got {statuses}"

            success_res = res1 if res1.status_code == 200 else res2
            conflict_res = res2 if res1.status_code == 200 else res1

            success_body = success_res.json()
            conflict_body = conflict_res.json()

            assert success_body["run_id"] in conflict_body.get("detail", ""), (
                f"Conflict detail must name the successfully started run {success_body['run_id']}: {conflict_body}"
            )

            active_runs = [r for r in runner._runs.values() if r.project_id == proj_10]
            assert len(active_runs) == 1, f"Expected exactly 1 run record, got {len(active_runs)}"

            active_runs[0].status = RunStatusEnum.COMPLETED
            cleanup_test_project(proj_10)

            print(f"  [PASS] Test 10: Exactly one request succeeded (200, run_id={success_body['run_id']}) and one was rejected (409). Active runs = 1.", flush=True)


def main():
    run_sync_tests()
    asyncio.run(run_concurrent_test())
    print("\n" + "=" * 65, flush=True)
    print(">>> ALL 10 PHASE H4 CONCURRENT-RUN TESTS PASSED (100%) <<<", flush=True)
    print("=" * 65, flush=True)


if __name__ == "__main__":
    main()
