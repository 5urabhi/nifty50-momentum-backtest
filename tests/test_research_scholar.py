"""Source-exact mathematical and API acceptance for QuantLab Research Studio.

All numerical studies run against a clearly SYNTHETIC local fixture. No Dhan
traffic, broker execution or fabricated claims about NIFTY historical returns.
"""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import (active_risk_lab,research_next,research_publication,
                             model_lab,service)
from workstation_api.app import app,RunRequest
from scripts.reproduce_study import reproduce


class ResearchScholarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="quantlab_scholar_")
        self.datapatch=patch.object(service,"DATA",Path(self.tmp.name)/"data")
        self.resultpatch=patch.object(service,"RESULTS",Path(self.tmp.name)/"results"/"runs")
        self.datapatch.start();self.resultpatch.start()
        service.create_synthetic()
        self.folder=service.DATA/"synthetic_example"
        self.client=TestClient(app,base_url="http://127.0.0.1:8765")
        self.config=RunRequest(dataset_id="synthetic",name="Synthetic scientific demo",
            factor_weights={"momentum":.5,"low_volatility":.5},
            top_n=8,max_weight=.2,rebalance_every=3,
            sector_cap=.55,execution_lag=1).model_dump()

    def tearDown(self):
        self.client.close()
        self.datapatch.stop();self.resultpatch.stop()
        self.tmp.cleanup()

    def _run(self)->str:
        return service.execute_run("synthetic",self.config)

    def test_passport_and_preflight_are_never_certifications(self):
        port=research_next.passport("synthetic")
        self.assertEqual(port["research_classification"],"SYNTHETIC DEMONSTRATION ONLY")
        self.assertFalse(port["observed_prices_available"])
        self.assertFalse(port["investability_certified"])
        self.assertTrue(any(f["name"]=="prices.csv" and len(f["sha256"])==64
                            for f in port["available_files"]))
        p=research_next.index_preflight("synthetic",self.config)
        self.assertEqual(p["status"],"ready_to_execute_unverified")
        self.assertFalse(p["blockers"])
        self.assertFalse(p["historical_investability_certified"])
        self.assertTrue(any("SYNTHETIC" in x for x in p["warnings"]))
        r=self.client.get("/api/workspace/passports/synthetic")
        self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(r.json()["investability_certified"])
        coverage=self.client.get("/api/workspace/source-coverage/synthetic")
        self.assertEqual(coverage.status_code,200,coverage.text)
        observed=coverage.json()
        self.assertEqual(observed["benchmark_alignment"],"calendar_matched")
        self.assertFalse(observed["historical_investability_certified"])
        self.assertEqual(observed["missing_eligible_prices"],0)
        self.assertEqual(observed["missing_security_observations_total"],0)
        invalid={**self.config,"factor_weights":{"value":.8}}
        (self.folder/"fundamentals.csv").unlink()
        self.assertTrue(any("fundamentals.csv" in x
                            for x in research_next.index_preflight("synthetic",invalid)["blockers"]))

    def test_archived_index_decisions_use_actual_math_and_source_hash(self):
        run=self._run()
        details=research_next.index_decisions(run)
        self.assertEqual(details["explainability_status"],
                         "exact_reconstruction_from_unchanged_saved_inputs")
        self.assertGreater(len(details["rows"]),0)
        self.assertGreater(details["selected_names"],0)
        for item in details["rows"]:
            self.assertTrue(item["member_at_decision"])
            self.assertTrue(item["selected_in_top_n"] if "selected_in_top_n" in item else True)
            self.assertGreater(item["target_weight"],0)
            self.assertAlmostEqual(sum(v for v in item["weighted_factor_contributions"].values()
                                       if v is not None),item["score"],places=5)
        name=details["rows"][0]["ticker"]
        explain=research_next.index_decisions(run,details["decision_date"],name)
        self.assertEqual(len(explain["rows"]),1)
        self.assertEqual(explain["rows"][0]["ticker"],name)
        deep=research_next.explain_saved("research_run",run,"mathematical")
        self.assertIn("Factor score",deep["formula"])
        self.assertEqual(deep["evidence_class"],"synthetic_demo")
        self.assertEqual(deep["source"]["dataset_id"],"synthetic")
        # Change original source after run: never explain an old result using new values.
        source=pd.read_csv(self.folder/"prices.csv")
        source.loc[5,source.columns[1]]*=1.03
        source.to_csv(self.folder/"prices.csv",index=False)
        with self.assertRaisesRegex(ValueError,"source|input changed"):
            research_next.index_decisions(run)

    def test_preregistration_is_append_only_source_bound(self):
        item=research_publication.preregister(
            "Can factor ranks reduce active tracking error over the frozen holdout?",
            "The earlier sample motivates the ex-ante null hypothesis.",
            "synthetic","information_ratio",
            "Later holdout IR > 0.05 with net modeled costs",
            "Use 70/15/15 chronological split, fixed factor weights and "
            "predeclared monthly cost and no post-test parameter changes.")
        self.assertTrue(item["registration_sha256"])
        self.assertEqual(item["status"],"recorded_before_results_in_this_workflow")
        items=research_publication.list_hypotheses()
        self.assertEqual(len(items),1)
        self.assertTrue(items[0]["content_unchanged"])
        f=research_publication._root()/(item["id"]+".json")
        payload=json.loads(f.read_text());payload["question"]="Retroactively edited question"
        f.write_text(json.dumps(payload))
        self.assertFalse(research_publication.list_hypotheses()[0]["content_unchanged"])

    def test_methodology_safe_zip_and_numeric_recomputation(self):
        run=self._run()
        doc=research_publication.methodology(run)
        self.assertIn("SYNTHETIC",doc["source_status"])
        self.assertFalse(doc["external_research_certified"])
        self.assertTrue(doc["source_unchanged"])
        zipfile=research_publication.bundle_path(run)
        with ZipFile(zipfile) as archive:
            self.assertEqual(set(archive.namelist()),{
                "METHODS_AND_FINDINGS.md","model_config.json",
                "metrics_by_split.json","manifest.json"})
            self.assertNotIn("prices.csv",archive.namelist())
            self.assertNotIn("membership.csv",archive.namelist())
            self.assertIn("SYNTHETIC",archive.read("METHODS_AND_FINDINGS.md").decode())
        result=reproduce(run)
        self.assertTrue(result["verified"],result)
        self.assertFalse(result["investment_evidence_certified"])
        self.assertEqual(set(result["numeric_tables"]),{
            "monthly_results.csv","post_rebalance_weights.csv","factor_scores.csv"})
        api=self.client.get("/api/workspace/methodology/"+run)
        self.assertEqual(api.status_code,200,api.text)
        z=self.client.get("/api/workspace/publications/"+run+".zip")
        self.assertEqual(z.status_code,200,z.text[:200] if z.status_code!=200 else "OK")
        self.assertTrue(z.content.startswith(b"PK"))

    def test_factor_risk_requires_real_factor_inputs_and_benchmark_weights(self):
        run=self._run()
        with self.assertRaisesRegex(ValueError,"benchmark_weights"):
            active_risk_lab.attribution(run)
        prices=pd.read_csv(self.folder/"prices.csv",index_col=0,parse_dates=True)
        benchmark=[{"date":prices.index[-1].date(),"ticker":name,
                    "weight":1./len(prices.columns)} for name in prices.columns]
        pd.DataFrame(benchmark).to_csv(self.folder/"benchmark_weights.csv",index=False)
        factors=pd.DataFrame({
            "date":prices.index,
            "SECTOR_PROXY":prices.iloc[:,0].pct_change(fill_method=None).fillna(0),
            "VALUE_PROXY":prices.iloc[:,5].pct_change(fill_method=None).fillna(0)})
        factors.to_csv(self.folder/"factor_returns.csv",index=False)
        result=active_risk_lab.attribution(run,lookback=36)
        self.assertGreaterEqual(result["fitted_observations"],18)
        self.assertGreaterEqual(result["annualized_active_tracking_error_estimate"],0)
        self.assertEqual(len(result["factor_contributions"]),2)
        self.assertAlmostEqual(
            result["annualized_active_tracking_error_estimate"]**2,
            result["systematic_variance"]+result["specific_variance"],places=9)
        self.assertIn("not licensed",result["warning"])
        r=self.client.get("/api/workspace/active-risk/"+run)
        self.assertEqual(r.status_code,200,r.text)
        bad_benchmark=pd.DataFrame(benchmark[:-1])
        bad_benchmark.to_csv(self.folder/"benchmark_weights.csv",index=False)
        with self.assertRaisesRegex(ValueError,"every modeled security"):
            active_risk_lab.attribution(run)

    def test_import_safe_risk_factor_and_dated_benchmark_files(self):
        prices=pd.read_csv(self.folder/"prices.csv",parse_dates=["date"])
        date=prices["date"].iloc[0].date().isoformat()
        tickers=[c for c in prices if c!="date"]
        weights=pd.DataFrame({"date":[date]*len(tickers),
            "ticker":tickers,"weight":[1./len(tickers)]*len(tickers)})
        factors=pd.DataFrame({"date":prices["date"].dt.date,
            "FACTOR_PROXY":prices[tickers[0]].pct_change(fill_method=None).fillna(0)})
        def bundle(w):
            output=BytesIO()
            with ZipFile(output,"w") as archive:
                for name in ("prices.csv","membership.csv","benchmark.csv"):
                    archive.writestr(name,(self.folder/name).read_bytes())
                archive.writestr("benchmark_weights.csv",w.to_csv(index=False))
                archive.writestr("factor_returns.csv",factors.to_csv(index=False))
            return output.getvalue()
        added=service.import_zip(bundle(weights),"risk-research.zip")
        self.assertEqual(added["kind"],"uploaded")
        folder,_=service.dataset_path(added["id"])
        self.assertTrue((folder/"factor_returns.csv").is_file())
        self.assertTrue((folder/"benchmark_weights.csv").is_file())
        incorrect=weights.copy()
        incorrect.loc[0,"weight"]+=.2
        with self.assertRaisesRegex(ValueError,"sum to one"):
            service.import_zip(bundle(incorrect),"invalid-risk.zip")

    def test_model_explanations_and_explicit_confirmation(self):
        saved=model_lab.save_result(model_lab.run_model("gbm",raw_parameters={
            "seed":21,"paths":30,"steps":24}))
        detail=research_next.explain_saved("model_run",saved["run_id"],"beginner")
        self.assertEqual(detail["evidence_class"],"synthetic")
        self.assertTrue(detail["formula"])
        forbidden=self.client.post("/api/workspace/index-studio/run",json={
            "experiment":self.config,"confirm":False})
        self.assertEqual(forbidden.status_code,400)
        initial=self.client.post("/api/workspace/index-studio/preflight",json=self.config)
        self.assertEqual(initial.status_code,200,initial.text)
        self.assertFalse(initial.json()["historical_investability_certified"])
        self.assertEqual(self.client.get("/api/workspace/explain/research_run/invalid").status_code,400)


if __name__=="__main__":
    unittest.main()
