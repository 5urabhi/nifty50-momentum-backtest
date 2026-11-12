"""Local-only tests for strict pre-forecast estimation and factor diagnostics."""
import unittest
import numpy as np
import pandas as pd
from index_research.model_validation import (
    rolling_volatility_forecasts,variance_forecast_scores,
    rolling_covariance_portfolios,grouped_factor_spreads
)


class RollingModelValidationTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(2026)
        self.index=pd.date_range("2014-01-31",periods=120,freq="ME")
        self.prices=pd.DataFrame(rng.normal(.005,.04,(120,8)),
                                 index=self.index,
                                 columns=[f"A{i}" for i in range(8)])

    def test_forecast_no_future_data(self):
        base=rolling_volatility_forecasts(self.prices["A0"],train_window=48)
        modified=self.prices["A0"].copy()
        modified.iloc[-12:]+=5
        later=rolling_volatility_forecasts(modified,train_window=48)
        pd.testing.assert_series_equal(base.loc[self.index[50]].rename(None),
                                       later.loc[self.index[50]].rename(None))
        self.assertEqual(len(base),72)

    def test_variance_scores_and_ordered_windows(self):
        table=rolling_volatility_forecasts(self.prices["A1"],train_window=48)
        result=variance_forecast_scores(table)
        self.assertIn("qlike",result.columns)
        self.assertTrue(np.isfinite(result["qlike"]).all())

    def test_covariance_model_comparison_no_lookahead(self):
        returns=rolling_covariance_portfolios(self.prices,train_window=36,
                                             rebalance_every=3,max_weight=.3)
        self.assertEqual(len(returns),84)
        early=returns.iloc[:30].copy()
        modified=self.prices.copy()
        modified.iloc[-10:]+=2
        later=rolling_covariance_portfolios(modified,train_window=36,
                                             rebalance_every=3,max_weight=.3)
        pd.testing.assert_frame_equal(early,later.iloc[:30])
        self.assertTrue(np.isfinite(returns.to_numpy()).all())

    def test_group_neutral_returns(self):
        date=self.index[:4]
        columns=self.prices.columns
        scores=pd.DataFrame(np.arange(8)[None,:].repeat(4,axis=0),
                             index=date,columns=columns)
        nxt=scores/100
        groups=pd.DataFrame([["X"]*4+["Y"]*4]*4,index=date,columns=columns)
        spread=grouped_factor_spreads(scores,nxt,groups,
                                      top_fraction=.25,minimum_per_group=4)
        self.assertTrue((spread>0).all())


if __name__=="__main__":
    unittest.main()
