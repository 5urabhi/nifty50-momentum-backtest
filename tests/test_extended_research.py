"""Local-only acceptance coverage for additional research integrations."""
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from index_research.fixtures import make_fixture
from index_research.data import load_research_inputs
from index_research.data_audit import audit_dataset
from index_research.sector_data import asof_sectors,read_sector_history
from index_research.factors import composite_scores
from index_research.index import construct_weights
from index_research.robustness import sensitivity_grid,parameter_dispersion
from index_research.experiment import ExperimentConfig


class ExtendedResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=make_fixture(Path(self.tmp.name)/"input")
        self.prices,self.members,self.benchmark,self.fund=load_research_inputs(self.root)
        self.sectors=asof_sectors(read_sector_history(str(self.root/"sectors.csv")),
                                  self.prices.index,self.prices.columns)

    def tearDown(self):
        self.tmp.cleanup()

    def test_data_readiness_audit(self):
        audit=audit_dataset(self.root)
        self.assertEqual(audit["number_of_monthly_marks"],len(self.prices))
        self.assertTrue(audit["historical_sector_classifications_supplied"])
        self.assertEqual(audit["missing_prices_when_eligible"],0)
        self.assertTrue(any("corporate-action" in s for s in audit["warnings"]))

    def test_risk_weighting_respects_constraints(self):
        scores=composite_scores(self.prices,self.members,{"momentum":1},self.fund)
        for method in ["minimum_variance","risk_parity"]:
            targets=construct_weights(scores,self.members,top_n=10,
                                      weighting=method,cap=.3,
                                      rebalance_every=3,prices=self.prices)
            valid=targets.dropna(how="all")
            self.assertTrue((valid.sum(axis=1)<=1+1e-7).all())
            self.assertTrue((valid.max(axis=1)<=.300001).all())

    def test_robustness_grid_does_not_optimize_final_test(self):
        config=ExperimentConfig(top_n=10,max_weight=.2,
                factor_weights={"momentum":1},validation_start="2020-01-31",
                final_test_start="2023-01-31")
        grid=sensitivity_grid(self.prices,self.members,self.benchmark,self.fund,
                config,sectors=self.sectors,costs_bps=(0.,10.),
                rebalance_months=(1,3),execution_lags=(0,1),
                segment="validation")
        self.assertEqual(len(grid),8)
        self.assertIn("strategy_cagr",grid.columns)
        dispersion=parameter_dispersion(grid,"strategy_cagr")
        self.assertEqual(dispersion["runs_with_metric"],8)
        with self.assertRaises(ValueError):
            sensitivity_grid(self.prices,self.members,self.benchmark,self.fund,
                config,segment="final_test")


if __name__=="__main__":
    unittest.main()
