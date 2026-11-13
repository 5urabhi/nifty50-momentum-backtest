"""Source-gated end-to-end research acceptance on deterministic synthetic inputs."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from index_research.data import load_research_inputs
from index_research.experiment import ExperimentConfig, run_experiment
from index_research.factors import composite_scores
from index_research.fixtures import make_fixture
from index_research.institutional_index import read_benchmark_history
from index_research.liquidity import read_liquidity


class InstitutionalEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=make_fixture(Path(self.temp.name)/"fixture")
        self.prices,self.members,self.benchmark,self.fund=load_research_inputs(self.folder)
        self.prices=self.prices.iloc[:46]
        self.members=self.members.iloc[:46]
        self.benchmark=self.benchmark.iloc[:46]
        self.config=ExperimentConfig(
            name="SYNTHETIC BENCHMARK OPTIMIZATION TEST",
            factor_weights={"momentum":.6,"low_volatility":.4},
            top_n=10,max_weight=.2,rebalance_every=3,
            weighting="benchmark_relative",optimizer_risk_aversion=4,
            optimizer_turnover_penalty=.01)

    def _history(self):
        source=[]
        for date in self.prices.index[::3]:
            for ticker in self.prices.columns:
                source.append({"date":date,"ticker":ticker,
                               "weight":1/len(self.prices.columns)})
        filename=self.folder/"benchmark_weights.csv"
        pd.DataFrame(source).to_csv(filename,index=False)
        return read_benchmark_history(filename)

    def test_benchmark_relative_run_and_exact_source_constraints(self):
        hist=self._history()
        result,scores,meta=run_experiment(
            self.prices,self.members,self.benchmark,self.fund,
            self.config,benchmark_history=hist)
        self.assertEqual(len(result.returns),len(self.prices)-1)
        self.assertEqual(meta["config"]["weighting"],"benchmark_relative")
        self.assertTrue((result.weights.sum(axis=1)<=1+1e-7).all())
        self.assertTrue((result.weights.max(axis=1)<=.200001).all())
        self.assertGreater(result.weights.gt(0).any(axis=1).sum(),0)

    def test_missing_benchmark_history_blocks_optimizer(self):
        with self.assertRaisesRegex(ValueError,"benchmark_weights.csv"):
            run_experiment(self.prices,self.members,self.benchmark,self.fund,
                           self.config)

    def test_yield_needs_historical_source_and_preserves_missing(self):
        with self.assertRaises(ValueError):
            composite_scores(self.prices,self.members,{"yield":1},None)
        priced=self.fund.copy()
        priced["yield"]=.018
        research=composite_scores(self.prices,self.members,{"yield":1},priced)
        self.assertTrue(research.iloc[8:].notna().any().any())
        # Without supplied yield, never silently synthesize a zero observation.
        missing=composite_scores(self.prices,self.members,{"yield":1},self.fund)
        self.assertTrue(missing.isna().all().all())

    def test_capacity_scenario_blocks_without_dated_liquidity(self):
        conf=replace(self.config,weighting="equal",liquidity_aum=100_000)
        with self.assertRaisesRegex(ValueError,"liquidity.csv"):
            run_experiment(self.prices,self.members,self.benchmark,self.fund,
                           conf)

    def test_read_source_liquidity_and_cost_impact(self):
        raw=[]
        for date in self.prices.index[::2]:
            for name in self.prices.columns:
                raw.append({"date":date,"ticker":name,
                    "adv_currency":1_000_000_000.,"half_spread_bps":5.})
        pd.DataFrame(raw).to_csv(self.folder/"liquidity.csv",index=False)
        observed=read_liquidity(self.folder/"liquidity.csv")
        cfg=replace(self.config,weighting="equal",liquidity_aum=100_000)
        result,scores,meta=run_experiment(
            self.prices,self.members,self.benchmark,self.fund,cfg,
            liquidity_records=observed)
        self.assertIn("liquidity_costs_by_period",meta)
        self.assertEqual(len(meta["liquidity_costs_by_period"]),len(result.returns))
        self.assertTrue((result.costs>=0).all())
        self.assertGreater(sum(x["additional_spread_impact_fraction"]
                               for x in meta["liquidity_costs_by_period"]),0.)
