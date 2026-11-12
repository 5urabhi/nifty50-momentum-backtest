"""Offline tests for bulk Dhan catalog, download persistence, cache and provenance.

No broker requests. Tests use deterministic mock candles and a fixture scrip master.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import dhan_workspace as dw, service
from workstation_api.app import app


class BulkDhanWorkstationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dhan_bulk_")
        self.root = Path(self.tmp.name)
        self.data_patch = patch.object(service, "DATA", self.root / "data")
        self.data_patch.start()
        master = service.DATA / "dhan" / "instrument_master.csv"
        master.parent.mkdir(parents=True)
        pd.DataFrame([
            {"SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E",
             "SEM_SMST_SECURITY_ID": "1333", "SEM_INSTRUMENT_NAME": "EQUITY",
             "SEM_TRADING_SYMBOL": "RELIANCE", "SEM_CUSTOM_SYMBOL": "Reliance Industries",
             "SEM_SERIES": "EQ"},
            {"SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E",
             "SEM_SMST_SECURITY_ID": "11536", "SEM_INSTRUMENT_NAME": "EQUITY",
             "SEM_TRADING_SYMBOL": "TCS", "SEM_CUSTOM_SYMBOL": "TCS Ltd",
             "SEM_SERIES": "EQ"},
            {"SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E",
             "SEM_SMST_SECURITY_ID": "221", "SEM_INSTRUMENT_NAME": "EQUITY",
             "SEM_TRADING_SYMBOL": "AUX", "SEM_CUSTOM_SYMBOL": "Auxiliary Company",
             "SEM_SERIES": "BE"},
            {"SEM_EXM_EXCH_ID": "BSE", "SEM_SEGMENT": "E",
             "SEM_SMST_SECURITY_ID": "500325", "SEM_INSTRUMENT_NAME": "EQUITY",
             "SEM_TRADING_SYMBOL": "RELIANCE", "SEM_CUSTOM_SYMBOL": "Reliance Industries",
             "SEM_SERIES": "A"},
            {"SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "D",
             "SEM_SMST_SECURITY_ID": "9999", "SEM_INSTRUMENT_NAME": "FUTIDX",
             "SEM_TRADING_SYMBOL": "NIFTY", "SEM_CUSTOM_SYMBOL": "NIFTY FUT",
             "SEM_SERIES": ""},
        ]).to_csv(master, index=False)
        dw._catalog_cached.cache_clear()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        self.data_patch.stop()
        dw._catalog_cached.cache_clear()
        self.tmp.cleanup()

    @staticmethod
    def _candles(inst, from_date, to_date, **kwargs):
        start = pd.Timestamp(from_date)
        end = pd.Timestamp(to_date)
        days = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
        days = days[days.weekday < 5]
        if not len(days):
            raise ValueError("No candles returned for " + inst.label)
        return pd.DataFrame({
            "datetime": days.tz_localize("Asia/Kolkata"),
            "label": inst.label,
            "security_id": inst.security_id,
            "exchange_segment": inst.exchange_segment,
            "instrument": inst.instrument,
            "open": range(100, 100 + len(days)),
            "high": range(102, 102 + len(days)),
            "low": range(99, 99 + len(days)),
            "close": range(101, 101 + len(days)),
            "volume": [1000] * len(days),
        })

    def test_catalog_understands_dhan_compact_master(self):
        resp = self.client.get("/api/dhan/catalog")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["total"], 2)
        self.assertEqual([row["symbol"] for row in resp.json()["items"]], ["RELIANCE", "TCS"])
        self.assertEqual(self.client.get("/api/dhan/catalog?exchange=BSE").json()["total"], 1)
        self.assertEqual(self.client.get("/api/dhan/catalog?query=TCS").json()["total"], 1)
        all_series = self.client.get("/api/dhan/catalog?regular_only=false").json()
        self.assertEqual(all_series["total"], 3)

    def test_all_nse_selection_is_real_master_only(self):
        created = dw.create_batch("all_nse", [], [], "2025-01-01", "2025-03-01", None, False)
        self.assertEqual(created["total"], 2)
        detail = dw.batch_details(created["id"])
        self.assertEqual({r["id"] for r in detail["items"]}, {"NSE_EQ:1333", "NSE_EQ:11536"})
        self.assertNotIn("DHAN_ACCESS_TOKEN", str(detail))

    def test_watchlist_requires_exact_symbol(self):
        chosen = dw.create_batch("watchlist", [], ["TCS", "RELIANCE", "TCS"],
                                 "2025-01-01", "2025-02-01", None, False)
        self.assertEqual(chosen["total"], 2)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            dw.create_batch("watchlist", [], ["NONEXISTENT"],
                            "2025-01-01", "2025-02-01", None, False)

    def test_cache_is_resumable_and_shared_across_batches(self):
        first = dw.create_batch("all_nse", [], [], "2025-01-01", "2025-03-01", None, False)
        with patch.object(dw, "download_candles", side_effect=self._candles) as http:
            done = dw.run_batch(first["id"])
            self.assertEqual(done["status"], "completed")
            self.assertEqual(done["counts"]["complete"], 2)
            self.assertEqual(http.call_count, 2)
            second = dw.create_batch("all_nse", [], [], "2025-01-01", "2025-03-01", None, False)
            again = dw.run_batch(second["id"])
            self.assertEqual(again["counts"]["cached"], 2)
            self.assertEqual(http.call_count, 2, "Repeat date ranges must not call Dhan")
        rows = dw.preview_history("NSE_EQ:1333")
        self.assertGreater(len(rows["rows"]), 10)
        self.assertEqual(rows["instrument_id"], "NSE_EQ:1333")
        self.assertEqual(rows["rows"][-1]["close"] > 0, True)

    def test_monthly_preparation_does_not_include_extra_cached_history(self):
        old = dw.create_batch("selected", ["NSE_EQ:1333"], [],
                              "2025-01-01", "2025-05-01", None, False)
        recent = dw.create_batch("selected", ["NSE_EQ:1333"], [],
                                 "2026-01-01", "2026-04-01", None, False)
        with patch.object(dw, "download_candles", side_effect=self._candles):
            dw.run_batch(old["id"])
            dw.run_batch(recent["id"])
        data = dw.prepare_batch(recent["id"])
        self.assertEqual(data["securities"], 1)
        self.assertTrue(data["ready_for_backtesting"] is False)
        df = pd.read_csv(service.DATA / "dhan" / "monthly_research" /
                         recent["id"] / "prices.csv")
        self.assertEqual(len(df), 3)
        self.assertTrue(df["date"].str.startswith("2026").all())
        with self.assertRaises(ValueError):
            dw.prepare_batch(recent["id"])

    def test_resume_failed_download_does_not_redownload_success(self):
        created = dw.create_batch("all_nse", [], [], "2025-01-01", "2025-02-01", None, False)
        attempts = {"TCS": 0}
        def sometimes_fail(inst, *args, **kwargs):
            if inst.security_id == "11536":
                attempts["TCS"] += 1
                if attempts["TCS"] == 1:
                    raise RuntimeError("Dhan HTTP 503 (response hidden)")
            return self._candles(inst, *args, **kwargs)
        with patch.object(dw, "download_candles", side_effect=sometimes_fail) as source:
            first = dw.run_batch(created["id"])
            self.assertEqual(first["counts"]["failed"], 1)
            self.assertEqual(first["counts"]["complete"], 1)
            second = dw.run_batch(created["id"])
            self.assertEqual(second["counts"]["complete"], 2)
            self.assertEqual(source.call_count, 3)

    def test_rejects_unsafe_batch_and_instrument_paths(self):
        with self.assertRaises(ValueError):
            dw.preview_history("../../.env")
        with self.assertRaises(ValueError):
            dw.batch_details("../../.env")
        self.assertEqual(self.client.get("/api/dhan/catalog", headers={
            "host": "untrusted.example",
        }).status_code, 403)


if __name__ == "__main__":
    unittest.main()
