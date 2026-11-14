"""Data coverage is numerical evidence, not certification of NSE original sources."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from index_research.evidence_coverage import (
    inspect_empirical_coverage,export_empirical_coverage,
)
from index_research.fixtures import make_fixture


class DataEvidenceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="quantlab_coverage_")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.data=make_fixture(self.root/"synthetic")
        self.config={
            "validation_start":"2020-01-31",
            "final_test_start":"2023-01-31",
            "factor_weights":{"momentum":.5,"low_volatility":.5},
        }

    def test_complete_synthetic_matrix_is_not_independently_validated(self):
        check=inspect_empirical_coverage(self.data,self.config)
        self.assertEqual(check["securities_in_observed_panel"],20)
        self.assertEqual(check["missing_eligible_prices"],0)
        self.assertEqual(check["missing_eligible_forward_returns"],0)
        self.assertEqual(check["benchmark_alignment"],"calendar_matched")
        self.assertFalse(check["historical_investability_certified"])
        self.assertTrue(any("SYNTHETIC" in x for x in check["warnings"]))
        self.assertGreater(check["observed_prevalidation_months"],44)

    def test_precise_ticker_and_date_missing_without_zero_imputation(self):
        price=pd.read_csv(self.data/"prices.csv")
        column=price.columns[1]
        raw_date=str(price.loc[10,"date"])[:10]
        price.loc[10,column]=float("nan")
        price.to_csv(self.data/"prices.csv",index=False)
        check=inspect_empirical_coverage(self.data,self.config)
        self.assertEqual(check["missing_eligible_prices"],1)
        self.assertGreaterEqual(check["missing_eligible_forward_returns"],1)
        self.assertIn({
            "date":raw_date,
            "ticker":column,
            "problem":"eligible_price_unavailable",
        },check["missing_security_observation_rows"])
        path=self.root/"coverage"
        saved=export_empirical_coverage(self.data,path,self.config)
        self.assertFalse(saved["publication_certified"])
        rows=pd.read_csv(path/"MISSING_SECURITY_MONTHS.csv")
        self.assertTrue(((rows.ticker==column)&
                         (rows.problem=="eligible_price_unavailable")).any())
        with self.assertRaises(FileExistsError):
            export_empirical_coverage(self.data,path,self.config)

    def test_dhan_source_monthly_date_does_not_equal_tri_month_end(self):
        bench=pd.read_csv(self.data/"benchmark.csv")
        original=bench["date"].iloc[2]
        bench.loc[2,"date"]="2015-03-30"
        # Other rows are all standard calendar month ends, so index is still sorted.
        bench.to_csv(self.data/"benchmark.csv",index=False)
        check=inspect_empirical_coverage(self.data,self.config)
        self.assertEqual(check["benchmark_alignment"],
                         "same_month_different_label_use_calendar_align")

    def test_sample_buffer_shortage_is_reported(self):
        check=inspect_empirical_coverage(self.data,{
            "validation_start":"2015-11-30",
            "final_test_start":"2016-06-30",
        })
        self.assertLess(check["observed_prevalidation_months"],44)
        self.assertTrue(any("20% estimation" in x for x in check["warnings"]))
        self.assertEqual(check["preferred_prevalidation_months_with_20_percent_buffer"],44)

    def test_final_test_uses_realized_return_labels_not_price_row_count(self):
        prices=pd.read_csv(self.data/"prices.csv")
        dates=pd.to_datetime(prices["date"])
        check=inspect_empirical_coverage(self.data,self.config)
        final=pd.Timestamp(self.config["final_test_start"])
        self.assertEqual(check["observed_final_test_months"],
                         int((dates.iloc[1:]>=final).sum()))
        after_last=inspect_empirical_coverage(self.data,{
            **self.config,"final_test_start":"2090-01-31"})
        self.assertEqual(after_last["observed_final_test_months"],0,
                         "A future final-test window cannot have -1 realized returns")
        at_beginning=inspect_empirical_coverage(self.data,{
            **self.config,"final_test_start":str(dates.iloc[0].date())})
        self.assertEqual(at_beginning["observed_final_test_months"],len(dates)-1)

    def test_missing_PIT_blocks_membership_coverage(self):
        (self.data/"membership.csv").unlink()
        check=inspect_empirical_coverage(self.data,self.config)
        self.assertIsNone(check["eligible_security_months"])
        self.assertIsNone(check["missing_eligible_prices"])
        self.assertFalse(check["independent_source_audit"])
