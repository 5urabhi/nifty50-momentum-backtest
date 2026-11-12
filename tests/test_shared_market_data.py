"""Offline acceptance for canonical instrument-keyed shared market history.

No Dhan credentials, broker order routes or live vendor network calls.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import model_data_manager as planner
from workstation_api import service
from workstation_api import shared_market_data as shared
from workstation_api import dhan_workspace as dw
from workstation_api.app import app


class SharedMarketDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quantlab_shared_data_")
        self.data_patch = patch.object(service, "DATA", Path(self.temp.name) / "data")
        self.data_patch.start()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.dates = pd.bdate_range("2024-01-02", periods=90)
        self.mapping = {
            "exchange_segment": "NSE_EQ", "security_id": "1333",
            "column": "RELIANCE", "display_symbol": "RELIANCE",
            "source_sha256": "a" * 64,
        }
        self.prices = pd.DataFrame({"close": [100 + i * 0.3 for i in range(90)]},
                                   index=self.dates)

    def tearDown(self):
        self.client.close()
        self.data_patch.stop()
        self.temp.cleanup()

    def test_one_canonical_identity_idempotent_and_appended(self):
        first = shared.ingest([(self.mapping, self.prices.iloc[:40])], origin="batch_alpha")
        self.assertEqual(first["rows_appended"], 40)
        replay = shared.ingest([(self.mapping, self.prices.iloc[:40])], origin="batch_beta")
        self.assertEqual(replay["rows_appended"], 0)
        self.assertEqual(replay["rows_reused"], 40)
        extension = shared.ingest([(self.mapping, self.prices)], origin="batch_gamma")
        self.assertEqual(extension["rows_appended"], 50)
        self.assertEqual(extension["rows_reused"], 40)
        self.assertEqual(extension["securities"], 1)
        self.assertEqual(extension["daily_sessions"], 90)
        folder, record = service.dataset_path("dhan_shared")
        self.assertTrue(record["has_daily_prices"])
        panel = pd.read_csv(folder / "daily_prices.csv")
        self.assertEqual(len(panel), 90)
        self.assertIn("NSE_EQ_1333", panel.columns)
        self.assertEqual(panel["NSE_EQ_1333"].iloc[-1], self.prices["close"].iloc[-1])

    def test_conflicting_existing_observation_rejected_without_mutation(self):
        shared.ingest([(self.mapping, self.prices)], origin="base")
        altered = self.prices.copy()
        altered.iloc[20, 0] += 10
        with self.assertRaisesRegex(ValueError, "Conflicting Dhan closes"):
            shared.ingest([(self.mapping, altered)], origin="conflict")
        with shared._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM daily_closes").fetchone()[0]
            close = conn.execute("SELECT close FROM daily_closes WHERE session_date=?",
                                 (self.dates[20].date().isoformat(),)).fetchone()[0]
        self.assertEqual(count, 90)
        self.assertAlmostEqual(close, self.prices["close"].iloc[20])

    def test_instruments_same_name_different_exchange_remain_distinct(self):
        alternate = {**self.mapping, "exchange_segment": "BSE_EQ",
                     "security_id": "500325", "source_sha256": "b" * 64}
        result = shared.ingest([(self.mapping, self.prices),
                                (alternate, self.prices)], origin="duality")
        self.assertEqual(result["securities"], 2)
        self.assertEqual(result["rows_appended"], 180)

    def test_coverage_is_common_returns_not_raw_price_rows(self):
        other = {**self.mapping, "security_id": "11536", "column": "TCS",
                 "source_sha256": "c" * 64}
        sparse = self.prices.iloc[25:].copy()
        shared.ingest([(self.mapping, self.prices), (other, sparse)], origin="sparse")
        plan = planner.inspect("garch", "dhan_shared", {"assets": 2})
        self.assertEqual(plan["min_returns"], 60)
        self.assertEqual(plan["target_returns"], 72)
        self.assertEqual(plan["common_returns"], len(sparse) - 1)
        self.assertEqual(plan["missing_to_target"], 72 - (len(sparse) - 1))
        self.assertFalse(plan["runnable"] is False and plan["common_returns"] >= 60)

    def test_guard_refuses_unconfirmed_download(self):
        response = self.client.post("/api/lab/data-requirements/extend", json={
            "model_id": "garch", "dataset_id": "dhan_shared",
            "params": {"assets": 2}, "confirm_download": False,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("confirmation", response.json()["detail"])

    def test_read_only_coverage_works_without_broker_data(self):
        response = self.client.get("/api/lab/data-requirements",
                                   params={"model_id": "gbm", "dataset_id": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_applicable")
        self.assertEqual(response.json()["min_returns"], 0)
        self.assertEqual(response.json()["target_returns"], 0)

    def test_cached_span_difference_detects_only_missing_intervals(self):
        uncovered = dw._uncovered(date(2024, 1, 1), date(2024, 6, 1), [
            ["2024-01-01", "2024-02-01"],
            ["2024-02-01", "2024-04-01"],
            ["2024-05-01", "2024-06-01"],
        ])
        self.assertEqual(uncovered, [(date(2024, 4, 1), date(2024, 5, 1))])


if __name__ == "__main__":
    unittest.main()
