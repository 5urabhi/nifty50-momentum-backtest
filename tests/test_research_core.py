import unittest
import numpy as np
import pandas as pd

from index_research.core import (
    equal_weight_top_n, momentum_scores, run_monthly_backtest, summary_metrics
)


class ResearchCoreTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.date_range("2020-01-31", periods=30, freq="ME")
        self.prices = pd.DataFrame({
            "A": 100.0 * 1.02 ** np.arange(30),
            "B": 100.0 * 1.01 ** np.arange(30),
        }, index=self.dates)

    def test_momentum_uses_only_past(self):
        base = momentum_scores(self.prices, formation=3, skip=1)
        changed = self.prices.copy()
        changed.loc[self.dates[18]:, "A"] *= 100
        later = momentum_scores(changed, formation=3, skip=1)
        pd.testing.assert_series_equal(base.loc[self.dates[15]], later.loc[self.dates[15]])
        self.assertAlmostEqual(base.loc[self.dates[5], "A"], 1.02 ** 3 - 1)

    def test_membership_excludes_ineligible_winner(self):
        scores = momentum_scores(self.prices, formation=3, skip=1)
        eligible = pd.DataFrame(True, index=self.dates, columns=self.prices.columns)
        eligible["A"] = False
        weights = equal_weight_top_n(scores, eligible, n=1)
        self.assertEqual(weights["A"].sum(), 0)
        self.assertEqual(weights.loc[self.dates[8], "B"], 1.0)

    def test_missing_membership_rejected(self):
        scores = momentum_scores(self.prices, 3, 1)
        eligible = pd.DataFrame(True, index=self.dates, columns=self.prices.columns)
        eligible.iloc[3, 0] = np.nan
        with self.assertRaises(ValueError):
            equal_weight_top_n(scores, eligible)

    def test_lookahead_and_turnover_cost(self):
        weights = pd.DataFrame(0.0, index=self.dates, columns=self.prices.columns)
        weights.loc[:, "A"] = 1.0
        benchmark = pd.Series(0.0, index=self.dates)
        result = run_monthly_backtest(self.prices, weights, benchmark, cost_bps=100)
        self.assertAlmostEqual(result.gross_returns.iloc[0], 0.02)
        self.assertAlmostEqual(result.returns.iloc[0], 0.01)
        self.assertAlmostEqual(result.returns.iloc[1], 0.02)
        self.assertAlmostEqual(result.turnover.iloc[0], 1.0)
        self.assertAlmostEqual(result.turnover.iloc[1], 0.0)
        self.assertEqual(result.returns.index[0], self.dates[1])

    def test_unpriced_holdings_rejected(self):
        prices = self.prices.copy()
        prices.iloc[8, 0] = np.nan
        weights = pd.DataFrame(0.0, index=self.dates, columns=prices.columns)
        weights.loc[:, "A"] = 1.0
        with self.assertRaises(ValueError):
            run_monthly_backtest(prices, weights, pd.Series(0.0, index=self.dates))

    def test_metrics(self):
        weights = pd.DataFrame(0.0, index=self.dates, columns=self.prices.columns)
        weights.loc[:, "A"] = 1.0
        result = run_monthly_backtest(self.prices, weights, pd.Series(0.01, index=self.dates), cost_bps=0)
        m = summary_metrics(result)
        self.assertEqual(m["observations"], 29)
        self.assertGreater(m["annualized_return"], 0)
        self.assertGreaterEqual(m["tracking_error"], 0)


if __name__ == "__main__":
    unittest.main()
