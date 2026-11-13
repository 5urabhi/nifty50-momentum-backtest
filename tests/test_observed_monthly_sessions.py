"""Point-in-time session preservation across daily wealth and monthly TRI."""
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from index_research.dhan_data import Instrument
from index_research.research_calendar import align_research_calendar
from index_research.total_returns import build_research_total_returns
from index_research.data import load_research_inputs


class ObservedTradingSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="quantlab_monthly_sessions_")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.raw=self.root/"daily_source"
        self.raw.mkdir()
        self.stocks=[
            Instrument(label="AAA",security_id="12345"),
            Instrument(label="BBB",security_id="67890"),
        ]
        for n,stock in enumerate(self.stocks):
            pd.DataFrame({
                "datetime":[
                    "2024-01-31T10:00:00+05:30",
                    "2024-02-29T10:00:00+05:30",
                    "2024-03-28T10:00:00+05:30",
                ],
                "close":[100+n,101+n,102+n],
                "security_id":[stock.security_id]*3,
                "label":[stock.label]*3,
            }).to_csv(self.raw/(stock.label+"_daily.csv"),index=False)
        self.actions=self.root/"corporate_actions.csv"
        self.actions.write_text(
            "ex_date,ticker,event_type,cash_per_share,share_multiplier,"
            "declared_at,source_url,verified\n")
        self.membership=self.root/"membership.csv"
        pd.DataFrame({
            "date":["2024-01-31","2024-01-31","2024-03-30"],
            "ticker":["AAA","BBB","AAA"],
            "eligible":[True,True,False],
        }).to_csv(self.membership,index=False)
        self.tri=self.root/"official_tri"
        self.tri.mkdir()
        pd.DataFrame({"date":["2024-01-31","2024-02-29","2024-03-31"],
                      "return":[.01,.02,-.03]}).to_csv(
                          self.tri/"benchmark.csv",index=False)
        (self.tri/"BENCHMARK_SOURCE.json").write_text(json.dumps({
            "return_convention":"gross_total_return",
            "initial_level_policy":"Original prior observation required",
        }))
        (self.root/"PIT_MEMBERSHIP_PROVENANCE.json").write_text(
            json.dumps({"status":"not independently reviewed"}))

    def test_daily_wealth_preserves_source_sessions_and_original_membership(self):
        source=self.root/"stock_wealth"
        build_research_total_returns(self.raw,self.stocks,self.actions,source)
        prices=pd.read_csv(source/"prices.csv")
        self.assertEqual(prices["date"].iloc[-1][:10],"2024-03-31")
        actual=pd.read_csv(source/"OBSERVED_MARKET_SESSIONS.csv")
        self.assertEqual(actual["observed_market_session"].iloc[-1][:10],
                         "2024-03-28")
        self.assertEqual(int(actual["calendar_days_between"].iloc[-1]),3)
        sessions=pd.read_csv(source/"PER_SECURITY_LAST_OBSERVED_SESSIONS.csv")
        self.assertEqual(sessions["AAA"].iloc[-1][:10],"2024-03-28")
        aligned=self.root/"aligned"
        result=align_research_calendar(
            source,aligned,self.tri/"benchmark.csv",
            membership_csv=self.membership)
        self.assertFalse(result["publication_certified"])
        px,eligible,benchmark,fund=load_research_inputs(aligned)
        self.assertTrue(eligible.loc["2024-03-31","AAA"],
            "March 30 member removal is after March 28 actual trading close")
        self.assertTrue(benchmark.index.equals(px.index))
        self.assertTrue((aligned/"RETURN_METHODOLOGY.json").exists())
        self.assertTrue((aligned/"BENCHMARK_SOURCE.json").exists())
        self.assertTrue((aligned/"PIT_MEMBERSHIP_PROVENANCE.json").exists())
        receipt=json.loads((aligned/"CALENDAR_ALIGNMENT_PROVENANCE.json").read_text())
        self.assertIsNotNone(receipt["source_observed_market_session_sha256"])
        self.assertEqual(receipt["original_last_formation"],"2024-03-28")

    def test_without_actual_session_mapping_weekend_month_end_is_blocked(self):
        original=self.root/"stock_wealth"
        build_research_total_returns(self.raw,self.stocks,self.actions,original)
        unproven=self.root/"unproven"
        unproven.mkdir()
        (unproven/"prices.csv").write_bytes((original/"prices.csv").read_bytes())
        with self.assertRaisesRegex(ValueError,"Weekend month-end"):
            align_research_calendar(unproven,self.root/"bad_alignment",
                                    self.tri/"benchmark.csv",
                                    membership_csv=self.membership)
        self.assertFalse((self.root/"bad_alignment").exists())
