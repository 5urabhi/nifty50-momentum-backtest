"""Integration-oriented local tests. Not automatically executed in GitHub."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from index_research.fixtures import make_fixture
from index_research.data import load_research_inputs
from index_research.sector_data import (
    read_sector_history,asof_sectors,sector_exposure,concentration_metrics
)
from index_research.research_analytics import (
    benchmark_comparison,rolling_relative_metrics,cost_sensitivity,
    compare_methodologies
)
from index_research.experiment import ExperimentConfig,run_experiment,save_experiment
from index_research.comparison import compare_index_methods
from index_research.pdf_report import generate_pdf_report


class IntegratedResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=make_fixture(self.root/"source")
        self.prices,self.members,self.benchmark,self.fund=load_research_inputs(self.source)
        self.sectors=asof_sectors(
            read_sector_history(str(self.source/"sectors.csv")),
            self.prices.index,self.prices.columns)

    def tearDown(self):
        self.temp.cleanup()

    def test_asof_sector_no_future_leakage(self):
        tickers=self.prices.columns
        events=pd.DataFrame({
            "date":pd.to_datetime(["2014-01-01","2014-01-01","2016-01-01"]),
            "ticker":["SYNTH_00","SYNTH_01","SYNTH_00"],
            "sector":["old","steady","new"],
        })
        dates=pd.DatetimeIndex(pd.to_datetime(["2015-01-31","2017-01-31"]))
        result=asof_sectors(events,dates,tickers)
        self.assertEqual(result.loc[dates[0],"SYNTH_00"],"old")
        self.assertEqual(result.loc[dates[1],"SYNTH_00"],"new")

    def test_sector_caps_and_artifacts(self):
        cfg=ExperimentConfig(
            top_n=12,max_weight=.2,rebalance_every=3,
            sector_cap=.40,factor_weights={"momentum":1},
            dataset_status="static_universe_demo",
            validation_start="2019-01-31",final_test_start="2022-01-31")
        result,scores,metadata=run_experiment(
            self.prices,self.members,self.benchmark,self.fund,cfg,sectors=self.sectors)
        self.assertEqual(len(result.returns),len(self.prices)-1)
        path=save_experiment(result,scores,metadata,self.root/"output",
                             self.source,sectors=self.sectors)
        expected=["sector_exposure.csv","rolling_metrics.csv","concentration.csv",
                  "research_manifest.json","cost_sensitivity.csv"]
        self.assertTrue(all((path/name).exists() for name in expected))
        sector=pd.read_csv(path/"sector_exposure.csv",index_col=0)
        self.assertLessEqual(sector.max().max(),1.000001)
        # Sector caps apply only at reconstitution; weights may drift afterwards.
        manifest=json.loads((path/"research_manifest.json").read_text())
        self.assertTrue(manifest["coverage"]["historical_sector_classification"])
        pdf=generate_pdf_report(path)
        self.assertTrue(pdf.exists())
        self.assertGreater(pdf.stat().st_size,2000)

    def test_concentration_identity(self):
        idx=pd.date_range("2020-01-31",periods=3,freq="ME")
        weights=pd.DataFrame({"a":[.5,.25,1.],"b":[.5,.75,0.]},index=idx)
        c=concentration_metrics(weights)
        self.assertAlmostEqual(c["hhi"].iloc[0],.5)
        self.assertAlmostEqual(c["effective_names"].iloc[0],2)

    def test_metrics_and_costs(self):
        idx=pd.date_range("2021-01-31",periods=24,freq="ME")
        a=pd.Series([.02]*24,index=idx)
        b=pd.Series([.01]*24,index=idx)
        t=pd.Series([0.1]*24,index=idx)
        metrics=benchmark_comparison(a,b,t)
        self.assertGreater(metrics["strategy_cagr"],metrics["benchmark_cagr"])
        roll=rolling_relative_metrics(a,b)
        self.assertEqual(int(roll["rolling_active_return"].notna().sum()),13)
        c=cost_sensitivity(a,t,cost_levels_bps=[0,10,50])
        self.assertTrue(c["annualized_return"].is_monotonic_decreasing)

    def test_multi_method_results_align(self):
        cfg=ExperimentConfig(top_n=10,max_weight=.2,
                             factor_weights={"momentum":1},
                             dataset_status="static_universe_demo")
        results,summary=compare_index_methods(
            self.prices,self.members,self.benchmark,self.fund,cfg,self.sectors)
        self.assertEqual(len(results),len(self.prices)-1)
        self.assertEqual(len(summary),4)
        self.assertTrue(results.index.is_monotonic_increasing)
        self.assertEqual(set(results.columns),set(summary.index))

    def test_missing_sector_constraint_fails(self):
        cfg=ExperimentConfig(top_n=10,max_weight=.2,sector_cap=.4)
        with self.assertRaises(ValueError):
            run_experiment(self.prices,self.members,self.benchmark,self.fund,cfg,sectors=None)


if __name__ == "__main__":
    unittest.main()
