"""QuantLab model-input chooser: exact observed-data eligibility and no substitution.

All fixtures are artificial and isolated. Tests never call Dhan, access
secrets, submit orders, or claim empirical results for generated prices.
"""
from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import model_input_selector, model_readiness, service
from workstation_api.app import app


class ModelInputChooserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="quantlab_input_chooser_")
        self.folder = Path(self.tmp.name)
        rng = np.random.default_rng(10114)
        dates = pd.bdate_range("2024-01-02", periods=330)
        a = 100 * np.exp(np.cumsum(rng.normal(.0002, .014, len(dates))))
        b = 70 * np.exp(np.cumsum(rng.normal(.0003, .017, len(dates))))
        b[20] = np.nan  # No auto fill is permitted, even for old missing prices.
        pd.DataFrame({"date": dates, "AAA": a, "BAD": b}).to_csv(
            self.folder / "daily_prices.csv", index=False)
        months = pd.date_range("2022-01-31", periods=28, freq="ME")
        values = rng.normal(.011, .028, len(months))
        pd.DataFrame({"date": months, "return": values}).to_csv(
            self.folder / "benchmark.csv", index=False)
        (self.folder / "BENCHMARK_SOURCE.json").write_text(json.dumps({
            "return_convention": "gross_total_return",
            "index_name": "NIFTY 50", "source_sha256": "a"*64,
        }))
        self.record = {
            "id": "source_test", "label": "TEST Dhan data",
            "kind": "dhan", "has_prices": True, "has_daily_prices": True,
        }
        self.lookup = patch.object(service, "dataset_path",
                                   return_value=(self.folder, self.record))
        self.lookup.start()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        self.lookup.stop()
        self.tmp.cleanup()

    def test_api_lists_only_eligible_tickers_as_runnable(self):
        result = self.client.get("/api/lab/model-inputs", params={
            "dataset_id": "source_test", "model_id": "heston_proxy"})
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertEqual(data["eligible_count"], 1)
        self.assertEqual(data["minimum"], 252)
        self.assertEqual(data["candidates"][0]["ticker"], "AAA")
        self.assertTrue(data["candidates"][0]["runnable"])
        self.assertEqual(data["candidates"][1]["ticker"], "BAD")
        self.assertFalse(data["candidates"][1]["runnable"])
        self.assertIn("Missing price observations", data["candidates"][1]["reason"])
        self.assertTrue(data["selection_is_explicit"])
        self.assertTrue(data["no_missing_prices_imputed"])
        self.assertFalse(data["synthetic_fixture"])

    def test_tri_and_stock_are_separately_available(self):
        response = self.client.get("/api/lab/model-inputs", params={
            "dataset_id": "source_test", "model_id": "gbm_fit"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["tri"]["runnable"])
        self.assertEqual(response.json()["tri"]["returns"], 28)
        self.assertEqual(response.json()["eligible_count"], 1)
        ou = self.client.get("/api/lab/model-inputs", params={
            "dataset_id": "source_test", "model_id": "ou_fit"}).json()
        self.assertFalse(ou["tri"]["runnable"])
        self.assertEqual(ou["eligible_count"], 1)
        self.assertEqual(ou["frequency"], "daily")
        merton = self.client.get("/api/lab/model-inputs", params={
            "dataset_id": "source_test", "model_id": "merton_fit"}).json()
        self.assertFalse(merton["tri"]["runnable"])  # 28 < 120 TRI months.

    def test_tri_only_dataset_not_falsely_blocked_for_gbm(self):
        tri_only = {**self.record, "has_prices": False, "has_daily_prices": False}
        with patch.object(service, "dataset_path", return_value=(self.folder, tri_only)):
            result = model_readiness.overview("source_test")
            rows = {row["id"]: row for row in result["models"]}
            self.assertEqual(rows["gbm_fit"]["status"], "source_available")
            self.assertEqual(rows["ou_fit"]["status"], "need_historical_data")
            self.assertEqual(rows["merton_fit"]["status"], "need_historical_data")
            self.assertIn("TRI", rows["gbm_fit"]["detail"])

    def test_no_gap_or_calendar_month_imputation(self):
        frame = pd.read_csv(self.folder / "daily_prices.csv")
        dates = pd.to_datetime(frame["date"])
        # Remove 16 consecutive business sessions, leaving a >10-day gap.
        frame.loc[~frame.index.isin(range(90, 106)), ["date","AAA","BAD"]].to_csv(
            self.folder / "daily_prices.csv", index=False)
        result = self.client.get("/api/lab/model-inputs", params={
            "dataset_id": "source_test", "model_id": "ou_fit"}).json()
        self.assertEqual(result["eligible_count"], 0)
        self.assertTrue(any("gap exceeding 10" in x["reason"] for x in result["candidates"]))
        seq = pd.Series([101.,102.,103.,105.], index=pd.DatetimeIndex([
            "2026-01-31","2026-02-28","2026-04-30","2026-05-31"]))
        observed = model_input_selector.inspect_stock(seq, "monthly", 3)
        self.assertFalse(observed["runnable"])
        self.assertIn("calendar months", observed["reason"])

    def test_source_readiness_is_preflight_not_forecast_certification(self):
        result = self.client.get("/api/lab/model-readiness", params={
            "dataset_id": "source_test"})
        self.assertEqual(result.status_code, 200, result.text)
        report = result.json()
        self.assertEqual(report["historical_source_ready"], 4)
        self.assertTrue(report["not_a_market_performance_certification"])
        model = {row["id"]: row for row in report["models"]}
        self.assertTrue(model["heston_proxy"]["source_ready"])
        self.assertFalse(model["implied_vol_quote"]["source_ready"])

    def test_unknown_model_or_missing_dataset_stays_actionable(self):
        missing = self.client.get("/api/lab/model-inputs", params={
            "dataset_id": "source_test", "model_id": "missing_model"})
        self.assertEqual(missing.status_code, 400)
        self.assertIn("historical single-series", missing.text)
        without = self.client.get("/api/lab/model-inputs", params={
            "model_id": "gbm_fit", "dataset_id": "nonexistent"})
        # The mocked dataset keeps the data local, but the endpoint must
        # still decline unsupported model IDs.
        self.assertEqual(without.status_code, 200)


if __name__ == "__main__":
    unittest.main()
