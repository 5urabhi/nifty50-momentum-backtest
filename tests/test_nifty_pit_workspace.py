"""Offline acceptance tests for dated NIFTY 50/BANK NIFTY membership and Dhan mapping.

No GitHub, NSE, Dhan, or brokerage account is accessed by these tests.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import dhan_benchmark, dhan_workspace as dw, index_spot, pit_index as pit, service
from workstation_api.app import app


def record(index, symbol, first, last="", source="snapshot_floor",
           note="", source_url=""):
    return {
        "index_name": index, "symbol": symbol, "valid_from": first,
        "valid_to": last, "source": source, "notes": note,
        "source_url": source_url,
    }


class DatedIndexMembershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nifty_pit_test_")
        self.root = Path(self.tmp.name)
        self.patch_data = patch.object(service, "DATA", self.root / "data")
        self.patch_data.start()
        self.master = service.DATA / "dhan" / "instrument_master.csv"
        self.master.parent.mkdir(parents=True)
        self.stocks = ["STK" + str(i).zfill(2) for i in range(50)]
        self.bank = [
            "HDFCBANK", "ICICIBANK", "SBIN", "PNB", "AXISBANK",
            "KOTAKBANK", "FEDERALBNK", "IDFCFIRSTB", "AUBANK",
            "BANKBARODA", "CANBK", "INDUSINDBK",
        ]
        symbols = self.stocks + ["NEWCO"] + self.bank + ["UNIONBANK", "YESBANK"]
        pd.DataFrame([
            {
                "SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E",
                "SEM_SMST_SECURITY_ID": str(i + 100),
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_TRADING_SYMBOL": symbol,
                "SEM_CUSTOM_SYMBOL": symbol,
                "SEM_SERIES": "EQ",
            } for i, symbol in enumerate(symbols)
        ]).to_csv(self.master, index=False)
        dw._catalog_cached.cache_clear()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        rows = [record("Nifty 50", s, "2014-01-01") for s in self.stocks[1:]]
        rows += [
            record("Nifty 50", self.stocks[0], "2014-01-01", "2025-09-30"),
            record("Nifty 50", "NEWCO", "2025-09-30",
                   source="press_release", source_url="https://niftyindices.com/example"),
        ]
        rows += [record("Nifty Bank", s, "2014-01-01") for s in self.bank]
        rows += [
            record("Nifty Bank", "UNIONBANK", "2014-01-01", "2014-03-28"),
            record("Nifty Bank", "YESBANK", "2014-01-01", "2020-03-27"),
            record("Nifty Bank", "UNIONBANK", "2026-09-30",
                   source="snapshot", note="inferred-include: source date guessed"),
            record("Nifty Bank", "YESBANK", "2026-09-30",
                   source="snapshot", note="inferred-include: source date guessed"),
        ]
        self.csv = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
        self.meta = b"# Coverage\n| Dataset | Freshness |\n| Index membership | data through **2026-10-13** |\n"
        self.sha = "c" * 40

    def tearDown(self):
        self.client.close()
        dw._catalog_cached.cache_clear()
        self.patch_data.stop()
        self.tmp.cleanup()

    def _fetch_mock(self, url, *_args):
        if url == pit.SOURCE_API:
            return json.dumps({"ref": "refs/heads/main",
                               "object": {"type": "commit", "sha": self.sha}}).encode("utf-8")
        if url.endswith(pit.MEMBERS_FILE):
            return self.csv
        if url.endswith(pit.COVERAGE_FILE):
            return self.meta
        raise AssertionError("Unexpected external request: " + url)

    def _sync(self):
        with patch.object(pit, "_fetch", side_effect=self._fetch_mock):
            return pit.sync()

    @staticmethod
    def _candles(inst, from_date, to_date, **_kwargs):
        start, stop = pd.Timestamp(from_date), pd.Timestamp(to_date)
        days = pd.date_range(start, stop - pd.Timedelta(days=1), freq="B")
        if days.empty:
            raise ValueError("No candles returned for " + inst.label)
        return pd.DataFrame({
            "datetime": days.tz_localize("Asia/Kolkata"),
            "label": [inst.label] * len(days),
            "security_id": [inst.security_id] * len(days),
            "exchange_segment": [inst.exchange_segment] * len(days),
            "instrument": [inst.instrument] * len(days),
            "open": [100.0] * len(days),
            "high": [102.0] * len(days),
            "low": [99.0] * len(days),
            "close": [101.0] * len(days),
            "volume": [1000] * len(days),
        })

    def test_large_git_commit_not_requested_during_sync(self):
        # GitHub's /commits/main response can exceed the former 200 KiB cap.
        # Only lightweight /git/ref/heads/main is allowed for SHA resolution;
        # no request may retrieve the full commit detail.
        urls = []
        def pinned(url, *args):
            urls.append(url)
            self.assertNotIn("/commits/main", url)
            return self._fetch_mock(url, *args)
        with patch.object(pit, "_fetch", side_effect=pinned):
            result = pit.sync()
        self.assertTrue(result["available"])
        self.assertEqual(urls[0], pit.SOURCE_API)
        self.assertIn("/git/ref/heads/main", urls[0])
        self.assertEqual(len(urls), 3)

    def test_index_history_sync_has_a_checksum_and_official_date_reconciliation(self):
        synced = self._sync()
        self.assertTrue(synced["available"])
        self.assertEqual(synced["covered_through"], "2026-10-13")
        self.assertEqual(len(synced["corrections"]), 2)
        history = self.client.get("/api/indices/preview", params={
            "index_id": "banknifty_pit", "from_date": "2025-11-01",
            "to_date": "2026-04-01", "as_of_date": "2025-12-30",
        })
        self.assertEqual(history.status_code, 200, history.text)
        before = history.json()
        self.assertNotIn("YESBANK", before["asof_members"])
        self.assertNotIn("UNIONBANK", before["asof_members"])
        after = self.client.get("/api/indices/preview", params={
            "index_id": "banknifty_pit", "from_date": "2025-11-01",
            "to_date": "2026-04-01", "as_of_date": "2025-12-31",
        }).json()
        self.assertIn("YESBANK", after["asof_members"])
        self.assertIn("UNIONBANK", after["asof_members"])
        self.assertEqual(before["change_count"], 2)
        self.assertEqual(after["end_count"], 14)

    def test_midperiod_membership_gap_is_blocked_at_every_effective_event(self):
        # The 2014, 2020 and Jan-2025 snapshots still have fifty members;
        # a gap created in June 2025 must also be detected before syncing.
        table = pd.read_csv(BytesIO(self.csv), dtype=str, keep_default_na=False)
        mask = ((table["index_name"] == "Nifty 50")
                & (table["symbol"] == "STK02"))
        self.assertEqual(int(mask.sum()), 1)
        table.loc[mask, "valid_to"] = "2025-06-01"
        table = pd.concat([table, pd.DataFrame([record(
            "Nifty 50", "STK02", "2025-07-01"
        )])], ignore_index=True)
        self.csv = table.to_csv(index=False).encode("utf-8")
        with patch.object(pit, "_fetch", side_effect=self._fetch_mock):
            with self.assertRaisesRegex(ValueError, "cardinality mismatch on 2025-06-01"):
                pit.sync()
        self.assertFalse(pit.status()["available"])

    def test_nifty_membership_replacements_do_not_leak_into_earlier_dates(self):
        self._sync()
        pre = pit.query("nifty50_pit", "2024-01-01", "2024-07-01", dw.catalog())
        self.assertEqual(pre["start_count"], 50)
        self.assertNotIn("NEWCO", pre["union_members"])
        later = pit.query("nifty50_pit", "2025-07-01", "2026-04-01", dw.catalog(),
                          as_of="2025-09-29")
        self.assertEqual(later["union_count"], 51)
        self.assertNotIn("NEWCO", later["asof_members"])
        on_event = pit.query("nifty50_pit", "2025-07-01", "2026-04-01",
                             dw.catalog(), as_of="2025-09-30")
        self.assertIn("NEWCO", on_event["asof_members"])
        self.assertNotIn(self.stocks[0], on_event["asof_members"])
        self.assertEqual(on_event["end_count"], 50)

    def test_detailed_master_display_names_cannot_masquerade_as_trading_symbols(self):
        self._sync()
        detailed = pd.DataFrame([
            {"EXCH_ID": "NSE", "SEGMENT": "E", "SECURITY_ID": "19585",
             "INSTRUMENT": "EQUITY", "SYMBOL_NAME": "BSE",
             "DISPLAY_NAME": "BSE LTD", "SERIES": "EQ"}
        ])
        detailed.to_csv(self.master, index=False)
        dw._catalog_cached.cache_clear()
        rows = dw.catalog()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["trading_symbol_verified"])
        plan = pit.query("nifty50_pit", "2025-01-01", "2025-06-01", rows)
        self.assertEqual(plan["resolved_count"], 0)
        self.assertTrue(all(item["reason"] == "refresh_compact_dhan_scrip_master"
                            for item in plan["unresolved"]))
        self.assertTrue(any("compact CSV" in warning for warning in plan["warnings"]))

    def test_never_extrapolate_after_source_cover_date_or_before_start(self):
        self._sync()
        with self.assertRaisesRegex(ValueError, "documents coverage only through"):
            pit.query("nifty50_pit", "2026-01-01", "2026-11-13", dw.catalog())
        with self.assertRaisesRegex(ValueError, "begins at"):
            pit.query("nifty50_pit", "2010-01-01", "2015-01-01", dw.catalog())
        with self.assertRaisesRegex(ValueError, "As-of date"):
            pit.query("nifty50_pit", "2025-01-01", "2025-06-01", dw.catalog(),
                      as_of="2026-01-01")

    def test_missing_current_dhan_id_is_visible_and_requires_explicit_consent(self):
        self._sync()
        master = pd.read_csv(self.master)
        master = master[master["SEM_TRADING_SYMBOL"] != self.stocks[0]]
        master.to_csv(self.master, index=False)
        dw._catalog_cached.cache_clear()
        plan = pit.query("nifty50_pit", "2024-01-01", "2024-06-01", dw.catalog())
        self.assertEqual(plan["unresolved_count"], 1)
        self.assertEqual(plan["unresolved"][0]["symbol"], self.stocks[0])
        with self.assertRaisesRegex(ValueError, "explicitly acknowledge"):
            dw.create_batch("nifty50_pit", [], [], "2024-01-01", "2024-06-01",
                            None, False)
        partial = dw.create_batch("nifty50_pit", [], [],
                                  "2024-01-01", "2024-06-01", None, False, True)
        self.assertEqual(partial["total"], 49)
        self.assertEqual(partial["historical_union_count"], 50)
        self.assertEqual(len(partial["historical_unresolved"]), 1)

    def test_published_dhan_spot_index_ids_are_attributed_fallbacks(self):
        from workstation_api import index_spot
        # A cash-only Dhan master may omit IDX_I rows entirely. Published
        # exchange index identifiers are allowed only with explicit provenance.
        nifty, source = index_spot.resolve_with_evidence("nifty50_pit")
        self.assertIsNotNone(nifty)
        self.assertEqual(nifty.security_id, "13")
        self.assertEqual(nifty.exchange_segment, "IDX_I")
        self.assertEqual(source, "dhan_oss_published_idx_i_reference_fallback")
        bank, source = index_spot.resolve_with_evidence("banknifty_pit")
        self.assertIsNotNone(bank)
        self.assertEqual(bank.security_id, "25")
        self.assertEqual(source, "dhan_oss_published_idx_i_reference_fallback")
        # An ambiguous current master is an evidence conflict, not permission
        # to silently choose a published ID over two possible alternatives.
        master = pd.read_csv(self.master, dtype=str)
        extra = pd.DataFrame([
            {"SEM_EXM_EXCH_ID": "IDX", "SEM_SEGMENT": "I",
             "SEM_SMST_SECURITY_ID": id_, "SEM_INSTRUMENT_NAME": "INDEX",
             "SEM_TRADING_SYMBOL": "NIFTY", "SEM_CUSTOM_SYMBOL": "NIFTY 50",
             "SEM_SERIES": ""}
            for id_ in ["13", "9999"]
        ])
        pd.concat([master, extra], ignore_index=True).to_csv(self.master, index=False)
        unknown, status = index_spot.resolve_with_evidence("nifty50_pit")
        self.assertIsNone(unknown)
        self.assertEqual(status, "conflicting_index_sids_in_dhan_master")

    def test_optional_index_spot_uses_verified_idx_i_mapping(self):
        self._sync()
        master = pd.read_csv(self.master, dtype=str)
        master = pd.concat([master, pd.DataFrame([{
            "SEM_EXM_EXCH_ID": "IDX", "SEM_SEGMENT": "I",
            "SEM_SMST_SECURITY_ID": "13", "SEM_INSTRUMENT_NAME": "INDEX",
            "SEM_TRADING_SYMBOL": "NIFTY", "SEM_CUSTOM_SYMBOL": "NIFTY 50",
            "SEM_SERIES": "",
        }])], ignore_index=True)
        master.to_csv(self.master, index=False)
        dw._catalog_cached.cache_clear()
        batch = dw.create_batch("nifty50_pit", [], [], "2025-01-01",
                                "2025-03-01", None, False, include_index_spot=True)
        with patch.object(dw, "download_candles", side_effect=self._candles), patch(
                "workstation_api.index_spot.download_candles",
                side_effect=self._candles):
            done = dw.run_batch(batch["id"])
        spot = done["index_spot"]
        self.assertEqual(spot["status"], "complete")
        self.assertEqual(spot["security_id"], "13")
        self.assertEqual(spot["identity_source"], "verified_unique_dhan_scrip_master_match")
        self.assertGreater(spot["rows"], 1)
        self.assertTrue((service.DATA / spot["file"]).is_file())
        self.assertIn("not a dividend-reinvested", spot["warning"])

    def test_membership_month_end_uses_last_trading_day_without_stale_prices(self):
        # 2025-11-30 is a Sunday. Mark the 2025-11-28 trading close,
        # and expose any security missing that session rather than carrying
        # its earlier November close forward.
        self._sync()
        securities = dw.catalog()
        missing_id = next(item["security_id"] for item in securities
                          if item["symbol"] == "HDFCBANK")
        batch = dw.create_batch("banknifty_pit", [], [],
                                "2025-10-01", "2025-12-01", None, False)

        def one_missing_close(inst, first, stop, **kwargs):
            frame = self._candles(inst, first, stop, **kwargs)
            if inst.security_id == missing_id:
                frame = frame.loc[
                    frame["datetime"].dt.date != date(2025, 11, 28)
                ].reset_index(drop=True)
            return frame

        with patch.object(dw, "download_candles", side_effect=one_missing_close):
            self.assertEqual(dw.run_batch(batch["id"])["counts"]["failed"], 0)
        outcome = dw.prepare_batch(batch["id"])
        self.assertEqual(outcome["months"], 2)
        self.assertEqual(outcome["missing_eligible_price_observations"], 1)
        path = service.DATA / "dhan" / "monthly_research" / batch["id"]
        matrix = pd.read_csv(path / "prices.csv")
        self.assertEqual(matrix["date"].tolist(), ["2025-10-31", "2025-11-28"])
        self.assertTrue(pd.isna(matrix.loc[1, "HDFCBANK"]))
        self.assertFalse(pd.isna(matrix.loc[0, "HDFCBANK"]))
        membership = pd.read_csv(path / "membership.csv")
        self.assertTrue(bool(membership.loc[
            (membership["date"] == "2025-11-28")
            & (membership["ticker"] == "HDFCBANK"), "eligible",
        ].iloc[0]))
        metadata = json.loads((path / "PIT_MEMBERSHIP_PROVENANCE.json").read_text())
        self.assertIn("last observed", metadata["month_marks"])
        registry = next(item for item in service.datasets()
                        if item["id"] == outcome["dataset_id"])
        self.assertFalse(registry["ready"])
        self.assertIn("missing_eligible_price_observations", registry["missing"])

    def test_saved_index_spot_creates_price_only_benchmark_with_real_previous_month_baseline(self):
        self._sync()
        # Mid-month start ensures an observed baseline before the first
        # fully-covered calendar month used by the PIT stock-price matrix.
        batch = dw.create_batch("nifty50_pit", [], [],
                                "2025-06-10", "2026-02-01", 1, False)
        with patch.object(dw, "download_candles", side_effect=self._candles), \\
             patch.object(index_spot, "download_candles", side_effect=self._candles):
            done = dw.run_batch(batch["id"])
        self.assertEqual(done["counts"]["complete"], 51)
        self.assertEqual(done["index_spot"]["status"], "complete")
        with patch.object(dw, "download_candles",
                          side_effect=AssertionError("No broker calls during preparation")), \\
             patch.object(index_spot, "download_candles",
                          side_effect=AssertionError("No index broker calls during preparation")):
            prepared = dw.prepare_batch(batch["id"])
            benchmark = dhan_benchmark.prepare_price_benchmark(batch["id"])
        self.assertEqual(prepared["source_interval_minutes"], 1)
        self.assertEqual(benchmark["benchmark_kind"], "price_index_spot_only")
        folder = service.DATA / "dhan" / "monthly_research" / batch["id"]
        returns = pd.read_csv(folder / "benchmark.csv")
        stock_marks = pd.read_csv(folder / "prices.csv")
        self.assertEqual(returns["date"].tolist(), stock_marks["date"].tolist())
        self.assertTrue((returns["return"] == 0).all())  # constant mocked spot
        evidence = json.loads((folder / "BENCHMARK_PROVENANCE.json").read_text())
        self.assertFalse(evidence["is_total_return_index"])
        self.assertFalse(evidence["is_dividend_reinvested"])
        self.assertEqual(evidence["month_marks"][0]["previous_month_close_date"], "2025-06-30")
        registered = next(d for d in service.datasets() if d["id"] == benchmark["dataset_id"])
        self.assertTrue(registered["ready"])
        self.assertTrue(registered["has_prices"])
        self.assertFalse(registered["benchmark_is_total_return"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            dhan_benchmark.prepare_price_benchmark(batch["id"])

    def test_cached_minute_batch_prepares_daily_and_pit_monthly_without_new_dhan_calls(self):
        # This is the downloaded-data workflow from the React screenshot:
        # 51 downloaded minute histories, no daily broker download.
        self._sync()
        batch = dw.create_batch("nifty50_pit", [], [],
                                "2025-07-01", "2026-02-01", 1, False)
        with patch.object(dw, "download_candles", side_effect=self._candles):
            finished = dw.run_batch(batch["id"])
        self.assertEqual(finished["counts"]["complete"], 51)
        with patch.object(dw, "download_candles", side_effect=AssertionError(
                "Preparation must not call Dhan again")):
            prepared = dw.prepare_batch(batch["id"])
        self.assertEqual(prepared["source_interval_minutes"], 1)
        self.assertTrue(prepared["daily_aggregation_generated"])
        self.assertTrue(prepared["membership_generated"])
        self.assertFalse(prepared["ready_for_backtesting"])
        folder = service.DATA / "dhan" / "monthly_research" / batch["id"]
        self.assertTrue((folder / "daily_prices.csv").is_file())
        self.assertTrue((folder / "daily_ohlcv" / "STK00.csv").is_file())
        self.assertTrue((folder / "prices.csv").is_file())
        self.assertTrue((folder / "membership.csv").is_file())
        evidence = json.loads((folder / "DAILY_AGGREGATION_PROVENANCE.json").read_text())
        self.assertEqual(evidence["source_interval_minutes"], 1)
        matrix = pd.read_csv(folder / "prices.csv")
        self.assertEqual(len(matrix), 7)
        registered = next(item for item in service.datasets()
                          if item["id"] == prepared["dataset_id"])
        self.assertTrue(registered["has_prices"])
        self.assertIn("benchmark.csv", registered["missing"])

    def test_membership_matrix_uses_pinned_intervals_not_later_catalog(self):
        self._sync()
        batch = dw.create_batch("nifty50_pit", [], [],
                                "2025-07-01", "2026-02-01", None, False)
        # The historical union includes both the removed and added names.
        self.assertEqual(batch["total"], 51)
        with patch.object(dw, "download_candles", side_effect=self._candles):
            done = dw.run_batch(batch["id"])
        self.assertEqual(done["counts"]["complete"], 51)
        output = dw.prepare_batch(batch["id"])
        self.assertTrue(output["membership_generated"])
        self.assertFalse(output["ready_for_backtesting"])
        path = service.DATA / "dhan" / "monthly_research" / batch["id"]
        prices = pd.read_csv(path / "prices.csv")
        self.assertTrue((path / "membership.csv").is_file())
        states = pd.read_csv(path / "membership.csv")
        self.assertEqual(len(states), 7 * 51)
        sept = states.loc[(states["date"] == "2025-09-30")]
        self.assertTrue(bool(sept.loc[sept["ticker"] == "NEWCO", "eligible"].iloc[0]))
        self.assertFalse(bool(sept.loc[sept["ticker"] == self.stocks[0], "eligible"].iloc[0]))
        self.assertEqual(len(prices), 7)
        provenance = json.loads((path / "PIT_MEMBERSHIP_PROVENANCE.json").read_text())
        self.assertEqual(provenance["source_commit"], self.sha)
        self.assertEqual(output["missing"], ["benchmark.csv"])
        with self.assertRaises(ValueError):
            dw.prepare_batch(batch["id"])


if __name__ == "__main__":
    unittest.main()
