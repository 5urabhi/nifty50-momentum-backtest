"""NSE source-audited snapshots and observed market-session calendar acceptance."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from index_research.data import load_research_inputs
from index_research.institutional_index import read_benchmark_history
from index_research.nse_weights import import_nifty_weight_snapshots
from index_research.research_calendar import align_research_calendar


class NSESourceAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="quantlab_nse_sources_")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def make_observed(self):
        source=self.root/"dhan"
        source.mkdir()
        days=pd.to_datetime(["2024-01-31","2024-02-29","2024-03-28"])
        pd.DataFrame({"date":days,"A":[100.,105.,108.],"B":[90.,95.,96.]}).to_csv(
            source/"prices.csv",index=False)
        pd.DataFrame({
            "date":["2024-01-31","2024-01-31","2024-03-30"],
            "ticker":["A","B","A"],"eligible":[True,True,False]}).to_csv(
                source/"membership.csv",index=False)
        pd.DataFrame({"date":pd.to_datetime(["2024-01-31","2024-02-29","2024-03-31"]),
                      "return":[.01,.02,-.03]}).to_csv(
                          source/"benchmark.csv",index=False)
        return source

    def test_relabel_actual_close_never_relabel_future_eligibility(self):
        source=self.make_observed()
        folder=self.root/"aligned"
        report=align_research_calendar(source,folder)
        self.assertEqual(report["months"],3)
        self.assertFalse(report["publication_certified"])
        prices, membership, benchmark, _=load_research_inputs(folder)
        self.assertEqual(list(prices.index.strftime("%Y-%m-%d")),
                         ["2024-01-31","2024-02-29","2024-03-31"])
        self.assertAlmostEqual(prices.loc["2024-03-31","A"],108.)
        self.assertTrue(membership.loc["2024-03-31","A"],
                        "March 30 membership exit is after observed March 28 close")
        self.assertTrue(benchmark.index.equals(prices.index))
        observed=pd.read_csv(folder/"OBSERVED_MARKET_SESSIONS.csv")
        self.assertEqual(observed.loc[2,"observed_market_session"][:10],"2024-03-28")
        with self.assertRaises(FileExistsError):
            align_research_calendar(source,folder)

    def test_no_missing_benchmark_month_is_forward_filled(self):
        source=self.make_observed()
        bench=pd.read_csv(source/"benchmark.csv")
        bench.iloc[1:].to_csv(source/"benchmark.csv",index=False)
        with self.assertRaisesRegex(ValueError,"one month EARLIER"):
            align_research_calendar(source,self.root/"bad_benchmark")

    def test_stale_actual_close_is_rejected(self):
        source=self.make_observed()
        prices=pd.read_csv(source/"prices.csv")
        prices.loc[2,"date"]="2024-03-10"
        prices.to_csv(source/"prices.csv",index=False)
        with self.assertRaisesRegex(ValueError,"stale"):
            align_research_calendar(source,self.root/"stale_month")

    def make_weights(self,unknown=False,early=False):
        source=self.root/"nse_snapshots"
        source.mkdir()
        universe=["TICK_%02d"%i for i in range(51)]
        pd.DataFrame({"date":["2024-01-31","2024-02-29"],
                      **{symbol:[100.,102.] for symbol in universe}}).to_csv(
                          source/"prices.csv",index=False)
        constituents=universe[:50].copy()
        if unknown:
            constituents[0]="MISSING_DELISTED_OR_RENAMED"
        pd.DataFrame({"Symbol":constituents,
                      "Weightage (%)":[2.]*len(constituents)}).to_csv(
                          source/"jan.csv",index=False)
        pd.DataFrame({
            "file":["jan.csv"],
            "snapshot_date":["2024-01-31"],
            "published_at":["2024-01-30" if early else "2024-02-02"],
            "source_url":["https://www.niftyindices.com/reports/monthly-reports"]
        }).to_csv(source/"manifest.csv",index=False)
        return source

    def test_source_only_benchmark_explicit_zeros_after_publication(self):
        source=self.make_weights()
        target=self.root/"benchmark_source"
        result=import_nifty_weight_snapshots(
            source/"manifest.csv",source/"prices.csv",target,weight_unit="percent")
        self.assertEqual(result["snapshots"],1)
        self.assertFalse(result["publication_certified"])
        weights=read_benchmark_history(target/"benchmark_weights.csv")
        self.assertEqual(len(weights),51)
        self.assertEqual(weights["date"].iloc[0],pd.Timestamp("2024-02-03"))
        self.assertAlmostEqual(weights["weight"].sum(),1.)
        missing=weights.loc[weights["ticker"]=="TICK_50","weight"]
        self.assertAlmostEqual(float(missing.iloc[0]),0.)
        audit=json.loads((target/"NSE_WEIGHTAGE_SOURCE_MANIFEST.json").read_text())
        self.assertEqual(len(audit["observed_source_snapshots"][0]["original_sha256"]),64)
        self.assertFalse(audit["source_publication_times_independently_verified"])

    def test_never_drop_unmapped_historical_security(self):
        source=self.make_weights(unknown=True)
        with self.assertRaisesRegex(ValueError,"Never drop delisted"):
            import_nifty_weight_snapshots(
                source/"manifest.csv",source/"prices.csv",
                self.root/"unknowns",weight_unit="percent")

    def test_no_source_data_before_snapshot(self):
        source=self.make_weights(early=True)
        with self.assertRaisesRegex(ValueError,"chronologically invalid"):
            import_nifty_weight_snapshots(
                source/"manifest.csv",source/"prices.csv",
                self.root/"early",weight_unit="percent")

    def test_bad_weightage_sum_is_not_renormalized(self):
        source=self.make_weights()
        frame=pd.read_csv(source/"jan.csv")
        frame.loc[0,"Weightage (%)"]=10.
        frame.to_csv(source/"jan.csv",index=False)
        with self.assertRaisesRegex(ValueError,"differs from 100"):
            import_nifty_weight_snapshots(
                source/"manifest.csv",source/"prices.csv",
                self.root/"weight_errors",weight_unit="percent")
