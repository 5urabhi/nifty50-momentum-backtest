"""Remaining QuantLab research-depth and vendor-evidence regression tests.

No real Dhan requests. Vendor responses are local mock objects, and tests
verify that read-only comparisons never mutate the canonical market store.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import json
import unittest

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import (dhan_live_verification, research_integrity,
                             research_learning, research_insights, service)
from workstation_api.app import app


class RemainingResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix="quantlab_validation_")
        root=Path(self.tmp.name)
        self.data=patch.object(service,"DATA",root/"data")
        self.results=patch.object(service,"RESULTS",root/"results"/"workstation_runs")
        self.data.start();self.results.start()
        rng=np.random.default_rng(24243)
        self.dates=pd.bdate_range("2023-01-03",periods=365)
        steps=rng.normal(.00025,.01,(len(self.dates),3))
        self.prices=pd.DataFrame(100*np.exp(np.cumsum(steps,axis=0)),
                     index=self.dates,columns=["A","B","C"])
        self.folder=service.DATA/"workstation_imports"/"study"
        self.folder.mkdir(parents=True)
        self.prices.to_csv(self.folder/"daily_prices.csv",index_label="date")
        self.prices.resample("ME").last().to_csv(self.folder/"prices.csv",index_label="date")
        pd.DataFrame({"date":self.dates[::25].date,"ticker":["A"]*len(self.dates[::25]),
                      "eligible":True}).to_csv(self.folder/"membership.csv",index=False)
        pd.DataFrame({"date":self.dates[::25].date,"benchmark":np.zeros(len(self.dates[::25]))}
                     ).to_csv(self.folder/"benchmark.csv",index=False)
        self.dataset="upload_study"
        self.client=TestClient(app,base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        self.data.stop();self.results.stop();self.tmp.cleanup()

    def _mapped_shared(self):
        shared=service.DATA/"dhan"/"monthly_research"/"shared"
        shared.mkdir(parents=True)
        self.prices.to_csv(shared/"daily_prices.csv",index_label="date")
        self.prices.resample("ME").last().to_csv(shared/"prices.csv",index_label="date")
        pd.DataFrame({"date":self.dates[::25].date,"ticker":["A"]*len(self.dates[::25]),
                      "eligible":True}).to_csv(shared/"membership.csv",index=False)
        pd.DataFrame({"date":self.dates[::25].date,"benchmark":np.zeros(len(self.dates[::25]))}
                     ).to_csv(shared/"benchmark.csv",index=False)
        mappings=[{"column":c,"exchange_segment":"NSE_EQ","security_id":str(888+i),
                   "display_symbol":c} for i,c in enumerate(["A","B","C"])]
        (shared/"SHARED_MARKET_PROVENANCE.json").write_text(
            json.dumps({"columns":mappings,"source":"DhanHQ REST API v2"}))
        item={"id":"NSE_EQ:888","symbol":"A","security_id":"888",
              "exchange_segment":"NSE_EQ","instrument":"EQUITY"}
        return shared,item

    def test_research_evidence_is_explicitly_not_a_certification(self):
        result=research_integrity.inspect(self.dataset)
        self.assertEqual(len(result["evidence"]),8)
        self.assertFalse(result["historical_investability_certified"])
        self.assertFalse(result["prospective_trading_certified"])
        self.assertTrue(result["ready_for_descriptive_prices"])
        self.assertIn("benchmark",result["missing_categories"])
        self.assertEqual(result["documented_categories"],1)
        response=self.client.get("/api/workspace/integrity/"+self.dataset)
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()["historical_investability_certified"])
        ref=research_integrity.add_source(self.dataset,"membership",
            "https://www.niftyindices.com/Index_Dashboard/","2024-01-05",
            "Original source must be checked against publication timestamps")
        self.assertEqual(ref["review_status"],"submitted_unverified")
        now=research_integrity.inspect(self.dataset)
        row=next(r for r in now["evidence"] if r["category"]=="membership")
        self.assertEqual(row["status"],"submitted_for_review")
        self.assertFalse(now["historical_investability_certified"])
        with self.assertRaisesRegex(ValueError,"credential"):
            research_integrity.add_source(self.dataset,"prices",
                "https://example.org?access_token=SECRET","2024-01-05")
        # A change in source data invalidates the original submission.
        new_frame=self.prices.copy()
        new_frame.loc[new_frame.index[3],"A"]*=1.001
        new_frame.to_csv(self.folder/"daily_prices.csv",index_label="date")
        stale=research_integrity.inspect(self.dataset)
        ref=next(r for r in stale["evidence"] if r["category"]=="membership")
        self.assertTrue(ref["source_references"][0]["stale"])
        self.assertEqual(ref["status"],"missing")

    def test_dhan_profile_preflight_and_sample_require_explicit_user_approval(self):
        shared,item=self._mapped_shared()
        with patch("workstation_api.model_data_manager._mapping",return_value=([item],None)):
            plan=dhan_live_verification.plan("dhan_shared","A")
            self.assertTrue(plan["available"])
            self.assertEqual(plan["cached_sample_sessions"],10)
            self.assertTrue(plan["will_download"])
            self.assertFalse(plan["will_append"])
            before=hashlib.sha256((shared/"daily_prices.csv").read_bytes()).hexdigest()
            denied=self.client.post("/api/workspace/dhan-live/probe",json={
                "dataset_id":"dhan_shared","column":"A","confirm":False})
            self.assertEqual(denied.status_code,400)
            with self.assertRaisesRegex(ValueError,"confirmation"):
                dhan_live_verification.probe("dhan_shared","A")
            with patch("workstation_api.dhan_auth.check_profile",return_value={
                "ok":False,"message":"No configured live entitlement"}):
                with self.assertRaisesRegex(ValueError,"No configured"):
                    dhan_live_verification.probe("dhan_shared","A",confirm=True)
            self.assertFalse((service.RESULTS.parent/"integrity_evidence"/"dhan_live_dhan_shared.json").exists())
            self.assertEqual(before,hashlib.sha256((shared/"daily_prices.csv").read_bytes()).hexdigest())

    def test_live_dhan_candle_match_and_mismatch_do_not_mutate_cache(self):
        shared,item=self._mapped_shared()
        def vendor(*args,**kwargs):
            last=self.prices.tail(10)
            return pd.DataFrame({
                "datetime":[d.tz_localize("Asia/Kolkata")+pd.Timedelta(hours=15,minutes=30)
                            for d in last.index],
                "close":last["A"].to_numpy(),
            })
        with patch("workstation_api.model_data_manager._mapping",return_value=([item],None)), \
             patch("workstation_api.dhan_auth.check_profile",return_value={"ok":True}), \
             patch("workstation_api.dhan_live_verification.download_candles",side_effect=vendor):
            before=hashlib.sha256((shared/"daily_prices.csv").read_bytes()).hexdigest()
            result=dhan_live_verification.probe("dhan_shared","A",confirm=True)
            self.assertEqual(result["status"],"matched")
            self.assertGreaterEqual(result["compared_sessions"],8)
            self.assertEqual(result["orders_submitted"],0)
            self.assertFalse(result["raw_price_data_modified"])
            self.assertEqual(before,hashlib.sha256((shared/"daily_prices.csv").read_bytes()).hexdigest())
            record=dhan_live_verification.previous("dhan_shared")
            self.assertFalse(record["stale"])
        def wrong(*args,**kwargs):
            out=vendor();out.loc[out.index[-1],"close"]+=17
            return out
        with patch("workstation_api.model_data_manager._mapping",return_value=([item],None)), \
             patch("workstation_api.dhan_auth.check_profile",return_value={"ok":True}), \
             patch("workstation_api.dhan_live_verification.download_candles",side_effect=wrong):
            result=dhan_live_verification.probe("dhan_shared","A",confirm=True)
            self.assertEqual(result["status"],"mismatch")
            self.assertGreater(result["mismatched_sessions"],0)

    def test_no_data_for_synthetic_fixtures(self):
        service.create_synthetic()
        with self.assertRaisesRegex(ValueError,"demonstration fixtures"):
            research_learning.readiness("synthetic","A")

    def test_readiness_and_guardrails(self):
        p=research_learning.readiness(self.dataset,"A")
        self.assertTrue(p["ready"])
        self.assertEqual(p["preferred_samples"],288)
        self.assertEqual(p["missing_minimum"],0)
        self.assertGreater(p["usable_lagged_samples"],300)
        r=self.client.get("/api/workspace/learning/readiness",params={
            "dataset_id":self.dataset,"asset":"A"})
        self.assertEqual(r.status_code,200,r.text)
        denied=self.client.post("/api/workspace/learning/run",json={
            "dataset_id":self.dataset,"asset":"A","method":"ridge","confirm":False})
        self.assertEqual(denied.status_code,400)
        with self.assertRaisesRegex(ValueError,"Unsupported registered learning method"):
            research_learning.run(self.dataset,"A",method="pseudomagic")
        reduced=self.prices.copy()
        reduced.loc[reduced.index[50],"A"]=np.nan
        reduced.to_csv(self.folder/"daily_prices.csv",index_label="date")
        with self.assertRaisesRegex(ValueError,"Internal missing"):
            research_learning.readiness(self.dataset,"A")

    def test_four_trained_research_methods_are_purged_and_exported(self):
        for method in ("ridge","random_forest","hist_gradient_boosting","tabular_q"):
            with self.subTest(method=method):
                result=research_learning.run(self.dataset,"A",method=method,
                                              train_fraction=.7,cost_bps=10,seed=91)
                self.assertLess(result["last_training_label_date"],result["first_test_decision_date"])
                self.assertGreaterEqual(result["train_observations"],120)
                self.assertGreaterEqual(result["test_observations"],40)
                self.assertLessEqual(result["figure_observations"],600)
                self.assertEqual(result["cost_bps"],10)
                self.assertIn("holdout_total_return_net",result)
                self.assertEqual(result["model_settings"]["execution_delay_sessions"],1)
                self.assertIn("source_sha256",result)
                artifact=research_insights.study_returns_path(result["study_id"])
                data=pd.read_csv(artifact)
                self.assertEqual(len(data),result["test_observations"])
                self.assertIn("position_long",data.columns)
                self.assertIn("entry_date",data.columns)
                self.assertTrue(data["position_long"].isin([0,1]).all())
                self.assertTrue((data["decision_date"]<data["entry_date"]).all())
                self.assertTrue((data["entry_date"]<data["date"]).all())
                self.assertTrue((data["strategy"]>=-1).all())

    def test_learning_large_holdout_preview_is_bounded(self):
        # The complete CSV must exist even when the chart contains ≤600 points.
        rng=np.random.default_rng(516)
        dates=pd.bdate_range("2000-01-01",periods=3500)
        frame=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(.0002,.01,len(dates)))),
                           index=dates,columns=["A"])
        frame.to_csv(self.folder/"daily_prices.csv",index_label="date")
        result=research_learning.run(self.dataset,"A",method="ridge",
                                     train_fraction=.6)
        self.assertGreater(result["test_observations"],1000)
        self.assertEqual(result["figure_observations"],600)
        self.assertEqual(len(pd.read_csv(research_insights.study_returns_path(
                        result["study_id"]))),result["test_observations"])


if __name__ == "__main__":
    unittest.main()
