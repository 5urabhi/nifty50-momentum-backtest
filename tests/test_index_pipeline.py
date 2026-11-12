"""Local regression checks; not executed via GitHub Actions."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from index_research.fixtures import make_fixture
from index_research.data import load_research_inputs, asof_fundamentals, read_membership
from index_research.factors import composite_scores
from index_research.index import construct_weights, backtest_index
from index_research.experiment import ExperimentConfig, run_experiment, save_experiment
from index_research.reports import build_html_report
from index_research.advanced_models import simulate_ou, principal_components, fit_garch11


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.input=make_fixture(self.root/"input")
        self.prices,self.members,self.benchmark,self.fund=load_research_inputs(self.input)

    def tearDown(self):
        self.tmp.cleanup()

    def test_asof_fundamentals_no_future_leakage(self):
        first=self.fund["available_at"].min()
        prior=asof_fundamentals(self.fund,first,self.prices.columns)
        self.assertTrue(prior.isna().all().all())
        later=asof_fundamentals(self.fund,first+pd.Timedelta(days=1),self.prices.columns)
        self.assertTrue(later["value"].notna().all())

    def test_factor_and_index_weights(self):
        scores=composite_scores(self.prices,self.members,{
            "momentum":0.3,"low_volatility":0.2,"value":0.2,"quality":0.2,"size":0.1},
            self.fund)
        targets=construct_weights(scores,self.members,top_n=10,cap=0.2,
                                   weighting="score",rebalance_every=3)
        valid=targets.dropna(how="all")
        self.assertTrue((valid.sum(axis=1)<=1+1e-8).all())
        self.assertTrue((valid.max(axis=1)<=0.2+1e-6).all())

    def test_drift_aware_turnover(self):
        ix=pd.date_range("2020-01-31",periods=4,freq="ME")
        prices=pd.DataFrame({"A":[100,110,121,133.1],"B":[100,100,100,100]},index=ix)
        target=pd.DataFrame(np.nan,index=ix,columns=prices.columns)
        target.loc[ix[0]]=[0.5,0.5]
        target.loc[ix[1]]=[0.5,0.5]
        back=backtest_index(prices,target,pd.Series(0.,index=ix),cost_bps=0)
        self.assertAlmostEqual(back.gross_returns.iloc[0],0.05)
        # pre-rebalance weights at the second interval: 0.55/1.05, 0.5/1.05
        self.assertAlmostEqual(back.pre_trade_weights.iloc[1]["A"],0.55/1.05)
        self.assertAlmostEqual(back.turnover.iloc[1],2*abs(0.55/1.05-0.5))
        self.assertAlmostEqual(back.gross_returns.iloc[1],0.05)

    def test_lag_avoids_lookahead(self):
        ix=pd.date_range("2020-01-31",periods=4,freq="ME")
        price=pd.DataFrame({"A":[100,110,121,133.1],"B":[100,100,100,100]},index=ix)
        target=pd.DataFrame(np.nan,index=ix,columns=price.columns)
        target.loc[ix[0]]=[1.0,0.0]
        res=backtest_index(price,target,pd.Series(0.,index=ix),execution_lag=1,cost_bps=0)
        self.assertAlmostEqual(res.returns.iloc[0],0.0)
        self.assertAlmostEqual(res.returns.iloc[1],0.1)

    def test_end_to_end_saved_report(self):
        cfg=ExperimentConfig(dataset_status="static_universe_demo",
                             factor_weights={"momentum":1},top_n=10,
                             max_weight=0.2,validation_start="2019-01-31")
        result,scores,meta=run_experiment(self.prices,self.members,self.benchmark,self.fund,cfg)
        path=save_experiment(result,scores,meta,self.root/"out",self.input)
        html=build_html_report(path)
        self.assertTrue(html.exists())
        self.assertIn("NOT",html.read_text().upper())
        self.assertEqual(len(meta["metrics_by_split"]),2)
        self.assertGreater(len(meta["coverage"]),0)

    def test_no_missing_held_prices_silently_filled(self):
        ix=pd.date_range("2020-01-31",periods=3,freq="ME")
        price=pd.DataFrame({"A":[100,np.nan,110],"B":[100,101,102]},index=ix)
        target=pd.DataFrame(np.nan,index=ix,columns=price.columns)
        target.loc[ix[0]]=[1.,0.]
        with self.assertRaises(ValueError):
            backtest_index(price,target,pd.Series(0.,index=ix))

    def test_advanced_analytical_models(self):
        paths=simulate_ou(7,7,0.5,0,0.1,10,3)
        self.assertTrue(np.allclose(paths,7))
        rng=np.random.default_rng(11)
        r=pd.DataFrame(rng.normal(size=(100,3)),columns=list("ABC"))
        pca=principal_components(r,2)
        self.assertEqual(pca["scores"].shape,(100,2))
        self.assertAlmostEqual(pca["explained_variance_ratio"].sum(),sum(pca["explained_variance_ratio"]))
        g=fit_garch11(pd.Series(r["A"]/100))
        self.assertTrue(g.next_variance>0)


if __name__=="__main__":
    unittest.main()
