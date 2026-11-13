"""Numerical regression for improved three-study robustness and testing."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from index_research.data import load_research_inputs
from index_research.experiment import ExperimentConfig,run_experiment
from index_research.fixtures import make_fixture
from scripts.complete_research_studies import (
    study_c,validation_familywise_tests
)


class StudyDepthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=make_fixture(Path(self.temp.name)/"source")
        self.results=Path(self.temp.name)/"result"
        self.results.mkdir()
        self.config=ExperimentConfig(
            name="SYNTHETIC STUDY DEPTH",
            factor_weights={"momentum":.5,"low_volatility":.5},
            top_n=10,max_weight=.2,rebalance_every=3,
            validation_start="2020-01-31",final_test_start="2023-01-31")

    def test_holm_correction_on_validation_period_not_final(self):
        dates=pd.date_range("2020-01-31",periods=42,freq="ME")
        rng=np.random.default_rng(42)
        b=pd.Series(rng.normal(.004,.02,len(dates)),index=dates)
        methods=pd.DataFrame({
            "candidate_A":b.to_numpy()+rng.normal(.002,.015,len(dates)),
            "candidate_B":b.to_numpy()+rng.normal(.004,.015,len(dates)),
            "candidate_C":b.to_numpy()+rng.normal(-.001,.015,len(dates)),
        },index=dates)
        methods.to_csv(self.results/"methodology_returns.csv",index_label="date")
        pd.DataFrame({"date":dates,"strategy_net":methods["candidate_A"].to_numpy(),
                      "benchmark":b.to_numpy()}).to_csv(
                          self.results/"monthly_results.csv",index=False)
        tested=validation_familywise_tests(self.results,self.config)
        self.assertEqual(tested["status"],"exploratory_validation_only")
        self.assertEqual(tested["family_size"],3)
        p=[row["holm_familywise_adjusted_p"] for row in tested["tests"]]
        self.assertTrue(all(0<=value<=1 for value in p))
        self.assertTrue(all(x["holm_familywise_adjusted_p"]>=x["uncorrected_p"]
                            for x in tested["tests"]))
        self.assertEqual(p,sorted(p))

    def test_mismatched_static_universe_produces_labeled_counterfactual(self):
        events=pd.read_csv(self.folder/"membership.csv")
        events=pd.concat([events,pd.DataFrame([{
            "date":"2017-01-31","ticker":"SYNTH_00","eligible":False
        }])],ignore_index=True)
        events.to_csv(self.folder/"membership.csv",index=False)
        prices,membership,benchmark,fundamentals=load_research_inputs(self.folder)
        actual,_,_=run_experiment(prices,membership,benchmark,fundamentals,self.config)
        pd.DataFrame({"date":actual.returns.index,"strategy_net":actual.returns,
                      "strategy_gross":actual.gross_returns,
                      "benchmark":actual.benchmark_returns}).to_csv(
                           self.results/"monthly_results.csv",index=False)
        report=study_c(self.folder,self.results,self.config)
        self.assertGreater(report["static_universe_pit_disagreement_security_months"],0)
        status=report["static_universe_counterfactual"]["status"]
        self.assertEqual(status,"exploratory_lookahead_contaminated_counterfactual",report)
        artifact=pd.read_csv(self.results/"static_universe_counterfactual.csv")
        self.assertEqual(len(artifact),len(actual.returns))
        self.assertIn("static_minus_pit_return",artifact)
