"""Offline compact-master regression tests for the Dhan index mapping layer."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
from workstation_api import dhan_workspace as dw, pit_index, service
from workstation_api.app import app


class CompactDhanHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch.object(service, "DATA", Path(self.tmp.name))
        self.patcher.start()
        dw._catalog_cached.cache_clear()
        self.master = service.DATA / "dhan" / "instrument_master.csv"
        self.master.parent.mkdir(parents=True)
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        dw._catalog_cached.cache_clear()
        self.patcher.stop()
        self.tmp.cleanup()

    def test_old_detailed_master_flagged_as_stale(self):
        pd.DataFrame([{
            "EXCH_ID": "NSE", "SEGMENT": "E", "SECURITY_ID": "1333",
            "INSTRUMENT": "EQUITY", "DISPLAY_NAME": "HDFC Bank",
        }]).to_csv(self.master, index=False)
        state = self.client.get("/api/dhan/catalog/health").json()
        self.assertFalse(state["ready"])
        self.assertEqual(state["code"], "outdated_detailed_master")

    def test_compact_symbols_resolve_and_health_is_ready(self):
        major = ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC"]
        rows = major + [f"TESTEQ{i:04d}" for i in range(125)]
        pd.DataFrame([{
            "SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E",
            "SEM_SMST_SECURITY_ID": str(i + 10000),
            "SEM_INSTRUMENT_NAME": "EQUITY", "SEM_TRADING_SYMBOL": symbol,
            "SEM_CUSTOM_SYMBOL": symbol, "SEM_SERIES": "EQ",
        } for i, symbol in enumerate(rows)]).to_csv(self.master, index=False)
        state = self.client.get("/api/dhan/catalog/health").json()
        self.assertTrue(state["ready"], state)
        self.assertEqual(state["verified_nse_tickers"], 131)
        self.assertTrue({"RELIANCE", "HDFCBANK", "ICICIBANK"}.issubset(
            {r["symbol"] for r in dw.catalog()}))

    def test_display_names_without_exchange_symbols_are_not_pit_mappings(self):
        pd.DataFrame([{
            "EXCH_ID": "NSE", "SEGMENT": "E", "SECURITY_ID": "1333",
            "INSTRUMENT": "EQUITY", "DISPLAY_NAME": "HDFCBANK",
            "SERIES": "EQ",
        }]).to_csv(self.master, index=False)
        self.assertFalse(dw.catalog()[0]["trading_symbol_verified"])
        self.assertFalse(dw.catalog_health()["ready"])


if __name__ == "__main__":
    unittest.main()
