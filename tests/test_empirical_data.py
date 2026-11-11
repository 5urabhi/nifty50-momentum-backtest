"""Local-only deterministic regression tests for empirical data plumbing.

Tests check formulas and blocking behavior, not real NSE/Dhan data accuracy.
"""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from index_research.total_returns import (
    total_return_index,read_actions,daily_to_monthly_total_return
)
from index_research.fundamental_ingestion import (
    normalize_filing_export,compute_pit_factor_records,export_factor_inputs
)
from index_research.benchmark_ingestion import normalize_benchmark
from index_research.empirical_validation import evidence_gate


class MarketResearchInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.days=pd.date_range("2024-01-02",periods=3,freq="D")

    def tearDown(self):
        self.temp.cleanup()

    def events(self,**kwargs):
        row={"ex_date":"2024-01-03","ticker":"AAA",
             "event_type":"dividend","cash_per_share":2.,
             "share_multiplier":1., "declared_at":"2024-01-02",
             "source_url":"https://example.org/verified_record","verified":True}
        row.update(kwargs)
        return pd.DataFrame([row])

    def test_dividend_reinvestment_vs_price_only(self):
        # Ex-day price declines by 2 but cash dividend is 2: zero total return.
        p=pd.Series([100.,98.,98.],index=self.days)
        total=total_return_index(p,self.events(),
                                 ticker="AAA",price_basis="split_bonus_adjusted")
        self.assertAlmostEqual(total.simple_return.iloc[1],0.,places=10)
        self.assertAlmostEqual(total.wealth_index.iloc[-1],1.,places=10)

    def test_split_raw_and_vendor_adjusted_are_consistent(self):
        events=self.events(event_type="split",cash_per_share=0,share_multiplier=2.)
        raw=pd.Series([100.,50.,55.],index=self.days)
        adjusted=pd.Series([50.,50.,55.],index=self.days)
        r=total_return_index(raw,events,ticker="AAA",price_basis="raw_unadjusted")
        a=total_return_index(adjusted,events,ticker="AAA",price_basis="split_bonus_adjusted")
        self.assertAlmostEqual(r.wealth_index.iloc[-1],1.1)
        self.assertAlmostEqual(a.wealth_index.iloc[-1],1.1)

    def test_presplit_dividend_on_adjusted_share_basis(self):
        dates=pd.date_range("2024-01-02",periods=4,freq="D")
        # Dhan-like backwards adjusted prices (post 2:1 split units).
        adjusted=pd.Series([50.,49.,49.,49.],index=dates)
        dividend=self.events(cash_per_share=2.)
        split=self.events(ex_date="2024-01-04",event_type="split",
                          cash_per_share=0.,share_multiplier=2.)
        events=pd.concat([dividend,split],ignore_index=True)
        wealth=total_return_index(adjusted,events,ticker="AAA",
                                  price_basis="split_bonus_adjusted")
        # Pre-split ₹2 dividend per OLD share = ₹1 per adjusted share.
        self.assertAlmostEqual(wealth.simple_return.iloc[1],0.)

    def test_delisting_recovery_replaces_terminal_price(self):
        p=pd.Series([100.,80.,70.],index=self.days)
        cash=self.events(ex_date="2024-01-04",event_type="delisting_cash",
                         cash_per_share=60.,share_multiplier=1.)
        result=total_return_index(p,cash,ticker="AAA",
                                  price_basis="split_bonus_adjusted")
        self.assertAlmostEqual(result.simple_return.iloc[-1],60/80-1.)
        # Old erroneous approach (70 + 60) / 80 would inflate wealth.

    def test_no_double_dividend_adjustment(self):
        p=pd.Series([100.,102.,104.],index=self.days)
        with self.assertRaises(ValueError):
            total_return_index(p,self.events(),ticker="AAA",
                               price_basis="total_return_adjusted",
                               dividends_already_included=True)

    def test_action_schema_and_unverified_block(self):
        f=self.events(verified=False)
        path=self.root/"actions.csv"
        f.to_csv(path,index=False)
        with self.assertRaises(ValueError):
            read_actions(path)

    def test_pit_value_quality_and_timestamps(self):
        f=pd.DataFrame([{
            "ticker":"AAA","period_end":"2023-12-31",
            "published_at":"2024-02-10","source_url":"https://example.org/filing",
            "filing_id":"AAA-2023","book_equity":200.,"net_income_ttm":20.,
            "revenue_ttm":150.,"operating_income_ttm":30.,
            "total_assets":400.,"total_debt":100.,
            "shares_outstanding":10.,"market_cap":500.,
        }])
        path=self.root/"filings.csv"
        f.to_csv(path,index=False)
        n=normalize_filing_export(path)
        factors=compute_pit_factor_records(n)
        self.assertAlmostEqual(factors.loc[0,"value"],.4)
        self.assertAlmostEqual(factors.loc[0,"quality"],.125)
        self.assertEqual(factors.loc[0,"size"],500.)
        result,_=export_factor_inputs(path,self.root/"scores")
        self.assertTrue(result.exists())

    def test_prepublication_future_data_rejected(self):
        f=pd.DataFrame([{
            "ticker":"AAA","period_end":"2024-05-01","published_at":"2024-01-01",
            "source_url":"source","filing_id":"x","book_equity":1,
            "net_income_ttm":1,"revenue_ttm":1,"operating_income_ttm":1,
            "total_assets":1,"total_debt":1,"shares_outstanding":1,"market_cap":1
        }])
        src=self.root/"invalid.csv"
        f.to_csv(src,index=False)
        with self.assertRaises(ValueError):
            normalize_filing_export(src)

    def test_benchmark_levels_to_returns(self):
        dates=pd.date_range("2024-01-31",periods=4,freq="ME")
        source=self.root/"nifty_tr.csv"
        pd.DataFrame({"Date":dates,"IndexTR":[100.,110.,121.,133.1]}).to_csv(source,index=False)
        path,metadata=normalize_benchmark(
            source,self.root/"benchmark",date_column="Date",
            level_column="IndexTR",index_name="NIFTY 50 TRI",
            return_convention="gross_total_return")
        out=pd.read_csv(path)
        self.assertAlmostEqual(out["return"].iloc[1],.1)
        self.assertEqual(json.loads(metadata.read_text())["return_convention"],"gross_total_return")

    def test_unverified_gate_fails_closed(self):
        root=self.root/"no_evidence"
        root.mkdir()
        declaration=root/"review.json"
        declaration.write_text("{}")
        check=evidence_gate(root,declaration)
        self.assertEqual(check["status"],"BLOCKED")
        self.assertGreater(len(check["missing_input_files"]),0)


if __name__=="__main__":
    unittest.main()
