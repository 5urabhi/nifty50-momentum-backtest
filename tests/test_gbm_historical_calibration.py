"""Historical GBM calibration regressions using clearly synthetic offline fixtures.

Tests never request Dhan data or imply that fitted model paths are forecasts.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import gbm_calibration, model_lab, service
from workstation_api.app import app


class HistoricalGBMTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="quantlab_fit_gbm_")
        self.folder = Path(self.tmp.name)
        self.prices = self.folder / "daily_prices.csv"
        self.benchmark = self.folder / "benchmark.csv"
        rng = np.random.default_rng(555)
        days = pd.bdate_range("2025-01-01", periods=260)
        a = 100 * np.exp(np.cumsum(rng.normal(.0004, .012, size=len(days))))
        b = 200 * np.exp(np.cumsum(rng.normal(.0002, .01, size=len(days))))
        pd.DataFrame({"date": days, "RELIANCE": a, "TCS": b}).to_csv(self.prices, index=False)
        months = pd.date_range("2023-01-31", periods=36, freq="ME")
        value = rng.normal(.012, .025, size=len(months))
        pd.DataFrame({"date":months,"return":value}).to_csv(self.benchmark,index=False)
        (self.folder / "BENCHMARK_SOURCE.json").write_text(json.dumps({
            "index_name":"NIFTY 50","return_convention":"gross_total_return",
            "source_sha256":"a"*64,"level_column":"Total Returns Index"}))
        self.record = {"id":"fixture_model_gbm","label":"SYNTHETIC TEST FIXTURE",
                       "kind":"synthetic","has_prices":True,"has_daily_prices":True,
                       "basis":"Offline random test values only"}
        self.patch = patch.object(service,"dataset_path",
                                  return_value=(self.folder,self.record))
        self.patch.start()
        self.runs_patch = patch.object(service,"RESULTS",self.folder/"results"/"workstation_runs")
        self.runs_patch.start()
        self.client = TestClient(app,base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        self.runs_patch.stop()
        self.patch.stop()
        self.tmp.cleanup()

    def run_model(self, **params):
        return self.client.post("/api/lab/run", json={
            "model_id":"gbm_fit","dataset_id":"fixture_model_gbm",
            "params":{"paths":50,"steps":30,**params},
        })

    def test_benchmark_calibration_and_chronological_holdout(self):
        response = self.run_model()
        self.assertEqual(response.status_code,200,response.text)
        report=response.json()
        self.assertEqual(report["model_id"],"gbm_fit")
        self.assertEqual(report["mode"],"historical")
        self.assertEqual(report["source"]["source_file"],"benchmark.csv")
        self.assertEqual(report["source"]["observations"],36)
        self.assertEqual(report["calibration"]["train_count"],28)
        self.assertEqual(report["calibration"]["test_count"],8)
        self.assertFalse(report["calibration"]["test_used_in_fit"])
        self.assertFalse(report["source"]["simulated_paths_are_market_data"])
        self.assertEqual(report["evidence_type"],
                         "historical_parameter_estimation_with_seeded_scenarios")
        self.assertEqual(len(report["plots"]),3)
        plot=report["plots"][0]
        self.assertEqual(plot["kind"],"fan2d")
        self.assertEqual(len(plot["x"]),9)
        self.assertIn("HOLDOUT",plot["title"])
        self.assertTrue(any("SYNTHETIC FIXTURE" in x for x in report["limitations"]))
        self.assertIn("source_sha256",report)

    def test_never_use_last_20_percent_to_fit_parameters(self):
        before=self.run_model().json()
        df=pd.read_csv(self.benchmark)
        # Alter ONLY held-out values; fitted drift/volatility must be identical.
        df.loc[df.index[-8:],"return"]=.45
        df.to_csv(self.benchmark,index=False)
        after=self.run_model().json()
        self.assertEqual(before["calibration"]["mu"],after["calibration"]["mu"])
        self.assertEqual(before["calibration"]["sigma"],after["calibration"]["sigma"])
        self.assertNotEqual(
            next(m["value"] for m in before["metrics"] if "Held-out one-step" in m["label"]),
            next(m["value"] for m in after["metrics"] if "Held-out one-step" in m["label"]))

    def test_deterministic_seeded_paths_and_source_evidence(self):
        a=self.run_model(seed=7).json()
        b=self.run_model(seed=7).json()
        self.assertEqual(a["plots"],b["plots"])
        self.assertEqual(a["source_sha256"],b["source_sha256"])
        self.assertNotEqual(a["run_id"],b["run_id"])

    def test_explicit_stock_selection_and_missing_symbol_rejection(self):
        fit=self.run_model(target="stock",ticker="RELIANCE")
        self.assertEqual(fit.status_code,200,fit.text)
        item=fit.json()
        self.assertEqual(item["source"]["assets"],["RELIANCE"])
        self.assertEqual(item["source"]["source_file"],"daily_prices.csv")
        self.assertGreater(item["calibration"]["train_count"],200)
        self.assertTrue(any("dividend" in x.lower() for x in item["limitations"]))
        wrong=self.run_model(target="stock",ticker="UNKNOWN")
        self.assertEqual(wrong.status_code,400)
        self.assertIn("not present",wrong.text)
        blank=self.run_model(target="stock",ticker="")
        self.assertEqual(blank.status_code,400)
        self.assertIn("Choose a stock symbol",blank.text)

    def test_no_auto_substitution_or_imputation(self):
        frame=pd.read_csv(self.prices)
        frame.loc[20,"RELIANCE"]=np.nan
        frame.to_csv(self.prices,index=False)
        invalid=self.run_model(target="stock",ticker="RELIANCE")
        self.assertEqual(invalid.status_code,400)
        self.assertIn("missing",invalid.text.lower())
        empty=self.run_model(target="stock",ticker="UNKNOWN")
        self.assertEqual(empty.status_code,400)

    def test_source_readiness_not_confused_with_multi_asset_requirement(self):
        r=self.client.get("/api/lab/data-requirements",params={
            "model_id":"gbm_fit","dataset_id":"fixture_model_gbm",
            "target":"benchmark_tri"})
        self.assertEqual(r.status_code,200,r.text)
        report=r.json()
        self.assertEqual(report["assets_requested"],1)
        self.assertTrue(report["runnable"])
        self.assertEqual(report["common_returns"],36)
        self.assertFalse(report["can_download"])
        bad=self.client.get("/api/lab/data-requirements",params={
            "model_id":"gbm_fit","dataset_id":"fixture_model_gbm",
            "target":"stock","ticker":"NOT_A_SYMBOL"})
        self.assertEqual(bad.status_code,200)
        self.assertFalse(bad.json()["runnable"])
        self.assertIn("not present",bad.json()["message"])

    def test_missing_tri_source_is_a_specific_action_not_approval_problem(self):
        (self.folder/"BENCHMARK_SOURCE.json").unlink()
        response=self.run_model()
        self.assertEqual(response.status_code,400)
        self.assertIn("NIFTY TRI",response.text)
        stock=self.run_model(target="stock",ticker="TCS")
        self.assertEqual(stock.status_code,200,stock.text)

    def test_small_dataset_uses_explicit_exploratory_warning(self):
        frame=pd.read_csv(self.benchmark)
        frame.head(11).to_csv(self.benchmark,index=False)
        report=self.run_model().json()
        self.assertEqual(report["source"]["observations"],11)
        self.assertTrue(any("SHORT SAMPLE" in x for x in report["limitations"]))

    def test_invalid_symbol_parameter_does_not_execute(self):
        response=self.run_model(target="stock",ticker="../.env")
        self.assertEqual(response.status_code,400)
        self.assertIn("stock symbol",response.text)


if __name__=="__main__":
    unittest.main()
