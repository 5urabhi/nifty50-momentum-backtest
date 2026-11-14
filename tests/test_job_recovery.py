"""Restart recovery: source locked, opt-in, no broker calls or secret persistence."""
from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from workstation_api import app as api, job_recovery


class WaitingWorker:
    def __init__(self):
        self.pending=[]
    def submit(self,work):
        future=Future()
        self.pending.append((work,future))
        return future


class JobRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="quantlab_restart_test_")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.dataset=self.root/"original"
        self.dataset.mkdir()
        (self.dataset/"prices.csv").write_text("date,SECURITY_A\\n2020-01-31,100\\n")
        self.source={"kind":"uploaded"}
        self.patcher=patch.object(job_recovery.service,"DATA",self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.lookup=patch.object(job_recovery.service,"dataset_path",
            return_value=(self.dataset,self.source))
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def test_recoverable_spec_locks_actual_source_bytes(self):
        kind="workspace_validation"
        args=()
        kwargs={"dataset_id":"upload_mydata","model":"min_variance"}
        self.assertTrue(job_recovery.save("0123456789abcdef",kind,args,kwargs))
        self.assertTrue(job_recovery.available("0123456789abcdef"))
        restored=job_recovery.restore("0123456789abcdef")
        self.assertEqual(restored,(kind,[],kwargs))
        self.assertNotIn("100\\n",(
            self.root/"research_workspace"/"restart_retries"/"0123456789abcdef.json"
        ).read_text())
        (self.dataset/"prices.csv").write_text("date,SECURITY_A\\n2020-01-31,101\\n")
        with self.assertRaisesRegex(ValueError,"changed"):
            job_recovery.restore("0123456789abcdef")

    def test_resume_rejected_when_source_removed_or_replaced(self):
        self.assertTrue(job_recovery.save("aaaabbbbccccdddd",
            "workspace_learning",("upload_mydata","SECURITY_A"),{}))
        (self.dataset/"prices.csv").unlink()
        with self.assertRaisesRegex(ValueError,"price"):
            job_recovery.restore("aaaabbbbccccdddd")

    def test_never_store_broker_jobs_or_credentials(self):
        self.assertFalse(job_recovery.save("1234567890abcdef",
            "dhan_bulk",("batch_1",),{}))
        self.assertFalse(job_recovery.available("1234567890abcdef"))
        with self.assertRaisesRegex(ValueError,"credential"):
            job_recovery.save("1234567890abcdee","workspace_validation",(),
                {"dataset_id":"upload_mydata","api_key":"TOPSECRET"})
        with self.assertRaisesRegex(ValueError,"credential"):
            job_recovery.save("1234567890abcdee","workspace_validation",(),
                {"dataset_id":"upload_mydata","comment":"Bearer abcdef"})
        self.assertFalse(job_recovery.available("1234567890abcdee"))

    def test_report_replay_requires_same_active_notebook(self):
        original={"kind":"notebook","trashed":False,"title":"Draft",
                  "payload":{"cells":[{"type":"markdown","content":"Version A"}]}}
        with patch.object(job_recovery.research_library,"get",return_value=original):
            self.assertTrue(job_recovery.save("abcdef0123456789",
                "workspace_report",("notebook_1",),{"format":"html"}))
            self.assertEqual(job_recovery.restore("abcdef0123456789")[0],"workspace_report")
        edited={**original,"payload":{"cells":[{"type":"markdown","content":"Version B"}]}}
        with patch.object(job_recovery.research_library,"get",return_value=edited):
            with self.assertRaisesRegex(ValueError,"changed"):
                job_recovery.restore("abcdef0123456789")

    def test_only_explicit_api_action_uses_interrupted_receipt(self):
        worker=WaitingWorker()
        previous=(api.JOBS,api.JOB_FUTURES,api.JOB_RETRY_SPECS,api.JOB_STOP_SIGNALS)
        api.JOBS={}
        api.JOB_FUTURES={}
        api.JOB_RETRY_SPECS={}
        api.JOB_STOP_SIGNALS={}
        self.addCleanup(lambda: (
            setattr(api,"JOBS",previous[0]),
            setattr(api,"JOB_FUTURES",previous[1]),
            setattr(api,"JOB_RETRY_SPECS",previous[2]),
            setattr(api,"JOB_STOP_SIGNALS",previous[3])
        ))
        original_id="eeeeffff00001111"
        job_recovery.save(original_id,"workspace_validation",(),
                          {"dataset_id":"upload_mydata","model":"min_variance"})
        old={"id":original_id,"status":"interrupted","kind":"workspace_validation"}
        with patch.object(api.research_library,"list_job_history",return_value=[old]), \\
             patch.object(api,"RUNNER",worker), \\
             patch.object(api,"_persist_job"), \\
             patch.object(api.research_library,"store_job"):
            board=api.workspace_jobs()
            item=next(x for x in board["jobs"] if x["id"]==original_id)
            self.assertTrue(item["retryable"])
            self.assertIn("Retry",item["next_action"])
            started=api.workspace_retry_job(original_id)
        self.assertEqual(started["status"],"queued")
        self.assertNotEqual(started["job_id"],original_id)
        self.assertEqual(len(worker.pending),1)

    def test_changed_source_blocks_interrupted_api_retry(self):
        job_id="ffffeeee00001111"
        job_recovery.save(job_id,"workspace_validation",(),
                          {"dataset_id":"upload_mydata","model":"min_variance"})
        (self.dataset/"prices.csv").write_text("date,SECURITY_A\\n2020-01-31,80\\n")
        with patch.object(api.research_library,"list_job_history",return_value=[
            {"id":job_id,"status":"interrupted","kind":"workspace_validation"}]):
            with self.assertRaises(HTTPException) as raised:
                api.workspace_retry_job(job_id)
        self.assertEqual(raised.exception.status_code,409)
        self.assertIn("changed",raised.exception.detail)
