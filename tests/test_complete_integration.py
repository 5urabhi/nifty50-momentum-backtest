"""Local-only integrated regression checks for completed research/UI backend."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from index_research.fixtures import make_fixture
from index_research.data import load_research_inputs
from index_research.sector_data import read_sector_history, asof_sectors, sector_exposure
from index_research.index import construct_weights
from index_research.factors import composite_scores
from index_research.experiment import ExperimentConfig, run_from_directory
from index_research.diagnostics import evaluate_factor_panel, exposure_panel, data_quality_report
from index_research.comparison import compare_index_methods


class CompletedIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.input=make_fixture(self.folder/"inputs")
        self.prices,self.members,self.benchmark,self.fundamentals=load_research_inputs(self.input)
        self.sectors=asof_sectors(
            read_sector_history(str(self.input/"sectors.csv")),
            self.prices.index,self.prices.columns)

    def tearDown(self):
        self.temp.cleanup()

    def test_asof_sector_rollforward_and_constraint(self):
        self.assertTrue(self.sectors.notna().all().all())
        scores=composite_scores(self.prices,self.members,{"momentum":1.0})
        targets=construct_weights(scores,self.members,top_n=10,
            cap=0.2,rebalance_every=3,sectors=self.sectors,sector_cap=0.50)
        for date in targets.index:
            row=targets.loc[date]
            if row.isna().all():
                continue
            selected=row[row>1e-12]
            group=self.sectors.loc[date,selected.index]
            cap_total=selected.groupby(group).sum()
            self.assertTrue((cap_total<=0.500001).all())

    def test_factor_specific_ic_and_asof_exposures(self):
        cfg=ExperimentConfig(factor_weights={"momentum":0.5,
                                              "low_volatility":0.5},
                             dataset_status="static_universe_demo")
        from index_research.experiment import run_experiment
        result,_,_=run_experiment(self.prices,self.members,self.benchmark,
                                  self.fundamentals,cfg,sectors=self.sectors)
        ic,scores=evaluate_factor_panel(self.prices,self.members,self.fundamentals)
        self.assertTrue({"momentum","low_volatility","value","quality","size"}.issubset(ic.columns))
        exposures,sector=exposure_panel(result.weights,scores,self.sectors)
        self.assertTrue(exposures.index.equals(result.weights.index))
        self.assertTrue(sector.index.equals(result.weights.index))
        self.assertTrue((sector.sum(axis=1)<=1.00001).all())

    def test_data_quality_has_no_false_provenance_claim(self):
        report=data_quality_report(self.prices,self.members,self.fundamentals,self.sectors)
        self.assertFalse(report["independent_provenance_verified"])
        self.assertGreater(report["eligible_price_coverage"],0)

    def test_methodology_variants_same_dates(self):
        config=ExperimentConfig(factor_weights={"momentum":1.0},
                                dataset_status="static_universe_demo")
        returns,summary=compare_index_methods(
            self.prices,self.members,self.benchmark,self.fundamentals,
            config,sectors=self.sectors)
        self.assertEqual(returns.shape[1],4)
        self.assertEqual(len(summary),4)
        self.assertFalse(returns.isna().any().any())

    def test_complete_cli_output_without_external_data(self):
        output=self.folder/"results"
        config=ExperimentConfig(factor_weights={"momentum":0.5,
                                                "quality":0.5},
                                dataset_status="static_universe_demo",
                                sector_cap=0.6,
                                top_n=10,
                                max_weight=0.2)
        run_from_directory(self.input,output,config)
        for name in [
            "monthly_results.csv","factor_scores.csv","factor_rank_ic.csv",
            "portfolio_factor_exposures.csv","data_quality.json",
            "research_manifest.json","sector_exposure.csv",
            "concentration.csv","rolling_metrics.csv",
        ]:
            self.assertTrue((output/name).is_file(),name)
        metadata=json.loads((output/"research_manifest.json").read_text())
        self.assertTrue(metadata["coverage"]["historical_sector_classification"])
        self.assertEqual(metadata["config"]["sector_cap"],0.6)
        self.assertFalse(json.loads((output/"data_quality.json").read_text())
                         ["independent_provenance_verified"])


if __name__=="__main__":
    unittest.main()
