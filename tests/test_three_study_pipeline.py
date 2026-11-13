"""Deterministic acceptance for the 3-study CLI; no market-data claims."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

from index_research.experiment import ExperimentConfig
from index_research.fixtures import make_fixture
from scripts.complete_research_studies import (
    research_preflight, study_c, inference_for_final_holdout,
)


class ThreeStudyPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_fixture(Path(self.tmp.name) / "synthetic")
        self.config = ExperimentConfig(
            name="SYNTHETIC TEST ONLY", factor_weights={"momentum": .5,
            "low_volatility": .5}, top_n=10, max_weight=.2,
            validation_start="2020-01-31", final_test_start="2023-01-31",
            execution_lag=1,
        )

    def test_synthetic_data_is_never_certified(self):
        report = research_preflight(self.root, self.config)
        self.assertTrue(report["software_ready"], report)
        self.assertEqual(report["classification"], "SYNTHETIC_DEMONSTRATION")
        self.assertFalse(report["publication_ready"])
        self.assertFalse(report["external_certification"])
        self.assertIn("BENCHMARK_SOURCE.json", report["external_evidence_blockers"])

    def test_no_final_holdout_is_blocked(self):
        bad = replace(self.config, final_test_start=None)
        report = research_preflight(self.root, bad)
        self.assertFalse(report["software_ready"])
        self.assertTrue(any("final_test_start" in x for x in report["configuration_blockers"]))

    def test_missing_source_files_are_reported(self):
        (self.root / "benchmark.csv").unlink()
        result = research_preflight(self.root, self.config)
        self.assertIn("benchmark.csv", result["missing_core_files"])

    def test_static_final_membership_has_zero_disagreement_for_constant_fixture(self):
        out = Path(self.tmp.name) / "result"
        out.mkdir()
        pd.DataFrame({
            "date": ["2020-01-31", "2020-02-29"],
            "strategy_net": [.01, .02], "strategy_gross": [.02, .03],
            "benchmark": [.008, .01],
        }).to_csv(out / "monthly_results.csv", index=False)
        result = study_c(self.root, out, self.config)
        self.assertEqual(result["static_universe_pit_disagreement_security_months"], 0)
        self.assertEqual(result["mean_membership_jaccard_to_final_universe"], 1.)
        self.assertEqual(result["price_only_benchmark"]["status"], "unavailable")
        self.assertAlmostEqual(result["cost_sensitivity"]["mean_model_cost_drag_per_month"], .01)

    def test_inference_requires_ex_ante_later_period(self):
        out = Path(self.tmp.name) / "report"
        out.mkdir()
        pd.DataFrame({
            "date": ["2022-01-31", "2022-02-28"],
            "strategy_net": [.01, .02], "benchmark": [.005, .005],
        }).to_csv(out / "monthly_results.csv", index=False)
        self.assertEqual(inference_for_final_holdout(out, self.config)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
