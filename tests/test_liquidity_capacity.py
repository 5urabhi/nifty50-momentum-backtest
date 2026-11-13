"""Capacity model unit checks on synthetic, explicitly hypothetical liquidity."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from index_research.index import IndexBacktest
from index_research.liquidity import read_liquidity,capacity_overlay


class LiquidityTests(unittest.TestCase):
    def setUp(self):
        self.days=pd.date_range("2024-01-31",periods=3,freq="ME")
        self.names=pd.Index(["A","B"])
        self.held=pd.DataFrame([[.7,.3],[.7,.3]],index=self.days[1:],columns=self.names)
        self.old=pd.DataFrame([[.5,.5],[.7,.3]],index=self.days[1:],columns=self.names)
        self.result=IndexBacktest(
            pd.Series([.0199,.01],index=self.days[1:]),
            pd.Series([.02,.01],index=self.days[1:]),
            pd.Series([.01,.01],index=self.days[1:]),
            pd.Series([.4,0.],index=self.days[1:]),
            self.held,self.old,pd.Series([.0001,0.],index=self.days[1:]))
        self.rows=pd.DataFrame({
            "date":pd.to_datetime(["2024-01-20"]*2),
            "ticker":["A","B"],"adv_currency":[10_000_000,10_000_000],
            "half_spread_bps":[8.,8.]})

    def test_spread_impact_overlay_is_nonnegative_and_zero_for_no_trade(self):
        revised,detail=capacity_overlay(self.result,self.days,self.rows,capital=100_000,
                   max_participation=.05,execution_days=3,impact_coefficient_bps=50.)
        self.assertGreater(revised.costs.iloc[0],self.result.costs.iloc[0])
        self.assertAlmostEqual(revised.costs.iloc[1],0.)
        self.assertAlmostEqual(revised.returns.iloc[1],self.result.gross_returns.iloc[1])
        self.assertEqual(len(detail),2)
        self.assertGreater(detail["additional_spread_impact_fraction"].iloc[0],0.)

    def test_missing_security_and_future_liquidity_block(self):
        with self.assertRaisesRegex(ValueError,"Missing as-of"):
            capacity_overlay(self.result,self.days,self.rows.iloc[:1],capital=100_000)
        future=self.rows.copy()
        future["date"]=pd.Timestamp("2024-08-01")
        with self.assertRaisesRegex(ValueError,"No dated liquidity"):
            capacity_overlay(self.result,self.days,future,capital=100_000)

    def test_capacity_enforced(self):
        with self.assertRaisesRegex(ValueError,"capacity exceeded"):
            capacity_overlay(self.result,self.days,self.rows,capital=100_000_000)

    def test_csv_rejects_duplicate_and_invalid_adv(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"liquidity.csv"
            pd.concat([self.rows,self.rows.iloc[:1]]).to_csv(p,index=False)
            with self.assertRaises(ValueError):
                read_liquidity(p)
            invalid=self.rows.copy()
            invalid.loc[0,"adv_currency"]=0
            invalid.to_csv(p,index=False)
            with self.assertRaises(ValueError):
                read_liquidity(p)
