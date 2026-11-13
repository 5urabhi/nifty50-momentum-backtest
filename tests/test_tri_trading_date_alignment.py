"""No-lookahead alignment of original NSE daily TRI to observed Dhan months.

All values below are synthetic fixtures. Never use them for market claims.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from index_research.benchmark_ingestion import align_daily_tri_to_stock_dates
from index_research.data import load_research_inputs
from workstation_api import service


class TRISessionAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="quantlab_tri_date_alignment_")
        self.root = Path(self.temporary.name)
        self.src = self.root / "nifty50_original_tri.csv"
        # Original vendor files often descend and use daily actual session dates.
        self.days = ["2025-11-28", "2025-12-31", "2026-01-30",
                     "2026-02-27", "2026-03-30", "2026-04-30", "2026-05-29",
                     "2026-06-30"]
        self.levels = [100., 101., 105., 104., 106., 108., 110., 111.]
        self._vendor()
        self.labels = self.days[1:]
        self.prices = self.root / "prices.csv"
        self._prices()

    def tearDown(self):
        self.temporary.cleanup()

    def _vendor(self, *, index_name="NIFTY 50"):
        pd.DataFrame({
            "IndexName": [index_name] * len(self.days),
            "Date": [pd.Timestamp(x).strftime("%d %b %Y") for x in reversed(self.days)],
            "Total Returns Index": list(reversed(self.levels)),
            "Net Total Return Index": list(reversed([v * .9 for v in self.levels])),
        }).to_csv(self.src, index=False)

    def _prices(self):
        pd.DataFrame({"date": self.labels, "AAA": range(100, 100+len(self.labels)),
                      "BBB": range(200, 200+len(self.labels))}).to_csv(
                          self.prices, index=False)

    def align(self):
        return align_daily_tri_to_stock_dates(
            self.src, self.prices, self.root/"output",
            date_column="Date", level_column="Total Returns Index",
            index_name="NIFTY 50 TRI", return_convention="gross_total_return")

    def test_exact_source_sessions_keep_all_months_including_previous_failure(self):
        out, receipt, audit_file = self.align()
        frame = pd.read_csv(out)
        self.assertEqual(frame["date"].tolist(), self.labels)
        self.assertAlmostEqual(frame["return"].iloc[0], 101./100.-1.)
        self.assertAlmostEqual(frame["return"].iloc[1], 105./101.-1.)
        self.assertAlmostEqual(frame["return"].iloc[4], 108./106.-1.)
        audit=json.loads(audit_file.read_text())
        self.assertEqual(audit["stock_calendar_months"],len(self.labels))
        self.assertEqual(audit["exact_trading_date_matches"],len(self.labels))
        self.assertEqual(audit["calendar_end_label_matches"],0)
        self.assertFalse(audit["source_has_future_observations_used"])
        self.assertEqual(json.loads(receipt.read_text())["source_index_name"],"NIFTY 50")
        self.assertEqual(audit["missing_months_imputed"],0)

    def test_calendar_end_labels_resolve_to_actual_observed_sessions(self):
        self.labels = ["2025-12-31", "2026-01-31", "2026-02-28",
                       "2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30"]
        self._prices()
        out, _, audit_file = self.align()
        frame = pd.read_csv(out)
        self.assertEqual(frame["date"].tolist(), self.labels)
        self.assertEqual(len(frame),7)
        audit=json.loads(audit_file.read_text())
        self.assertEqual(audit["calendar_end_label_matches"],4)
        january = next(x for x in audit["alignment_rows"] if x["study_month"]=="2026-01")
        self.assertEqual(january["tri_observed_trading_date"],"2026-01-30")
        self.assertEqual(january["stock_observation_label"],"2026-01-31")
        self.assertEqual(january["date_lag_calendar_days"],1)
        self.assertEqual(audit["missing_months_imputed"],0)

    def test_missing_real_session_is_not_filled_by_earlier_or_future_session(self):
        self.labels[1]="2026-01-29"
        self._prices()
        with self.assertRaisesRegex(ValueError,"exact stock observation date 2026-01-29"):
            self.align()

    def test_missing_prior_month_is_explicit_and_never_fabricates_initial_return(self):
        self.days=self.days[1:]
        self.levels=self.levels[1:]
        self._vendor()
        with self.assertRaisesRegex(ValueError,"preceding month \\(2025-11\\)"):
            self.align()

    def test_missing_whole_source_month_and_wrong_index_are_blocked(self):
        self.days.remove("2026-03-30")
        self.levels.remove(106.)
        self._vendor()
        with self.assertRaisesRegex(ValueError,"no observed trading level|missing the exact stock observation date"):
            self.align()
        self.days.append("2026-03-30")
        self.levels.append(106.)
        self._vendor(index_name="NIFTY BANK")
        with self.assertRaisesRegex(ValueError,"contains NIFTY BANK"):
            self.align()

    def test_price_index_close_cannot_be_labeled_tri(self):
        with self.assertRaisesRegex(ValueError,"OHLC column"):
            align_daily_tri_to_stock_dates(self.src,self.prices,self.root/"other",
                date_column="Date",level_column="Close",
                index_name="NIFTY 50 TRI")

    def test_service_upload_keeps_original_data_and_provenance(self):
        data_root=self.root/"data"
        batch=data_root/"dhan"/"monthly_research"/"batch_tri"
        batch.mkdir(parents=True)
        for name in ("prices.csv",):
            (batch/name).write_bytes((self.root/name).read_bytes())
        pd.DataFrame([{"date":"2025-11-27","ticker":name,"eligible":True}
                      for name in ("AAA","BBB")]).to_csv(
                          batch/"membership.csv",index=False)
        (batch/"EVIDENCE_REVIEW.json").write_text('{"previous_human_review":true}')
        with patch.object(service,"DATA",data_root):
            saved=service.attach_tri_benchmark(
                "dhan_batch_tri",self.src.read_bytes(),self.src.name,
                date_column="Date",level_column="Total Returns Index",
                index_name="NIFTY 50 TRI",convention="gross_total_return")
            self.assertTrue(saved["ready"])
            self.assertEqual(saved["benchmark_alignment"]["matched_months"],len(self.labels))
            target=data_root/"workstation_imports"/saved["id"].removeprefix("upload_")
            _, _, benchmark, _ = load_research_inputs(target)
            self.assertEqual(benchmark.index.strftime("%Y-%m-%d").tolist(),self.labels)
            self.assertTrue((target/"BENCHMARK_ALIGNMENT_PROVENANCE.json").exists())
            self.assertFalse((target/"EVIDENCE_REVIEW.json").exists())
            self.assertFalse(saved["independently_verified"])
            self.assertFalse((batch/"benchmark.csv").exists())


if __name__=="__main__":
    unittest.main()
