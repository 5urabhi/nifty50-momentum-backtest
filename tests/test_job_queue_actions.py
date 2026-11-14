"""Bounded serial queue and safe retry guarantees; no real worker/API calls."""
from __future__ import annotations

from concurrent.futures import Future
from unittest.mock import patch
import unittest

from fastapi import HTTPException

from workstation_api import app as module


class StoppedWorker:
    def __init__(self):
        self.pending=[]
    def submit(self,task):
        future=Future()
        self.pending.append((task,future))
        return future


class JobQueueTests(unittest.TestCase):
    def setUp(self):
        self.worker=StoppedWorker()
        self.before=(module.JOBS,module.JOB_FUTURES,
                     module.JOB_RETRY_SPECS,module.JOB_STOP_SIGNALS)
        module.JOBS={}
        module.JOB_FUTURES={}
        module.JOB_RETRY_SPECS={}
        module.JOB_STOP_SIGNALS={}
        self.mocks=[
            patch.object(module,"RUNNER",self.worker),
            patch.object(module,"_persist_job",return_value=None),
            patch.object(module.research_library,"list_job_history",return_value=[]),
        ]
        for p in self.mocks:p.start()

    def tearDown(self):
        for p in reversed(self.mocks):p.stop()
        (module.JOBS,module.JOB_FUTURES,
         module.JOB_RETRY_SPECS,module.JOB_STOP_SIGNALS)=self.before

    def test_bounded_serial_queue_and_positions(self):
        ids=[]
        for i in range(module.MAX_ACTIVE_LOCAL_JOBS):
            response=module._spawn("workspace_validation",lambda:{"step":i})
            ids.append(response["job_id"])
        self.assertEqual(len(self.worker.pending),6)
        self.assertEqual(len(module.JOBS),6)
        snapshot=module.workspace_jobs()
        self.assertEqual(snapshot["max_pending_or_running"],6)
        self.assertEqual(snapshot["worker_concurrency"],1)
        order=[j for j in reversed(snapshot["jobs"])]
        self.assertEqual([j["queue_position"] for j in order],[1,2,3,4,5,6])
        self.assertTrue(all(j["status"]=="queued" for j in order))
        with self.assertRaises(HTTPException) as fail:
            module._spawn("workspace_validation",lambda:None)
        self.assertEqual(fail.exception.status_code,409)
        self.assertIn("full",fail.exception.detail)

    def test_cancel_queued_releases_capacity_and_safe_retry(self):
        first=module._spawn("workspace_validation",lambda:None)["job_id"]
        for _ in range(5):module._spawn("workspace_validation",lambda:None)
        stopped=module.workspace_cancel_job(first)
        self.assertEqual(stopped["status"],"cancelled")
        self.assertFalse(module.JOB_FUTURES[first].running())
        self.assertTrue(module.JOB_FUTURES[first].cancelled())
        snapshot=module.workspace_jobs()
        self.assertTrue(next(j for j in snapshot["jobs"] if j["id"]==first)["retryable"])
        retried=module.workspace_retry_job(first)
        self.assertEqual(retried["status"],"queued")
        self.assertNotEqual(retried["job_id"],first)

    def test_failure_actions_do_not_include_vendor_content(self):
        self.assertIn("Dhan",module._job_next_action(
            {"status":"error","error":"Dhan token expired"}))
        self.assertIn("throttling",module._job_next_action(
            {"status":"error","error":"HTTP 429 rate limit"}))
        self.assertIn("Model Laboratory",module._job_next_action(
            {"status":"error","error":"Insufficient source history"}))
        self.assertIn("local queue",module._job_next_action(
            {"status":"queued"}))
        self.assertIn("checkpoint",module._job_next_action(
            {"status":"running","cancellable":True}))
