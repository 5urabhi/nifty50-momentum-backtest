"""Tests preserve source-vintage boundaries, no certification, safe exports."""
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from zipfile import ZipFile

from index_research.experiment import ExperimentConfig
from index_research.fixtures import make_fixture
from scripts.research_release import inspect, generate


class ResearchReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quantlab_release_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = make_fixture(self.root / "source")
        config = ExperimentConfig(name="SYNTHETIC RELEASE VALIDATION",
            factor_weights={"momentum": .5, "low_volatility": .5},
            top_n=10, max_weight=.2, rebalance_every=3, execution_lag=1,
            validation_start="2020-01-31", final_test_start="2023-01-31")
        self.settings = self.root / "config.json"
        self.settings.write_text(json.dumps(asdict(config)))

    def test_preflight_is_not_independent_market_certification(self):
        status = inspect(self.source, self.settings)
        self.assertTrue(status["software_ready"])
        self.assertEqual(status["classification"], "SYNTHETIC_DEMONSTRATION")
        self.assertFalse(status["publication_certified"])
        self.assertFalse(status["independent_reviewer_certified"])
        self.assertIn("BENCHMARK_SOURCE.json", status["missing_sources"])
        self.assertEqual(len(status["source_sha256"]["prices.csv"]), 64)

    def test_missing_benchmark_emits_official_acquisition_instructions(self):
        (self.source / "benchmark.csv").unlink()
        status = inspect(self.source, self.settings)
        self.assertFalse(status["software_ready"])
        benchmark = next(x for x in status["required_sources"]
                         if x["file"] == "benchmark.csv")
        self.assertFalse(benchmark["source_present"])
        self.assertIn("NIFTY 50 TRI", benchmark["next_action"])
        self.assertTrue(benchmark["official_source_start"].startswith("https://"))

    def test_immutable_source_safe_release(self):
        destination = self.root / "report"
        written = generate(self.source, self.settings, destination)
        self.assertTrue(written["software_ready"])
        self.assertFalse(written["publication_certified"])
        summary = json.loads((destination / "RESEARCH_RELEASE_STATUS.json").read_text())
        self.assertFalse(summary["study_execution"]["requested"])
        html = (destination / "RESEARCH_RELEASE.html").read_text()
        self.assertIn("Independent financial research certification: NO", html)
        with ZipFile(destination / "RESEARCH_RELEASE_SAFE.zip") as package:
            archived = set(package.namelist())
        self.assertNotIn("prices.csv", archived)
        self.assertEqual(archived, {"RESEARCH_RELEASE_STATUS.json",
                "RESEARCH_RELEASE_MEMO.md", "RESEARCH_RELEASE.html"})
        with self.assertRaises(FileExistsError):
            generate(self.source, self.settings, destination)

    def test_blocked_inputs_do_not_create_fake_study(self):
        (self.source / "membership.csv").unlink()
        destination = self.root / "blocked"
        result = generate(self.source, self.settings, destination, execute=True)
        self.assertFalse(result["software_ready"])
        self.assertFalse(result["studies_executed"])
        self.assertIn("membership.csv",
            (destination / "RESEARCH_RELEASE_MEMO.md").read_text())

    def test_synthetic_studies_can_run_but_never_get_certified(self):
        destination = self.root / "computed"
        result = generate(self.source, self.settings, destination, execute=True)
        self.assertTrue(result["studies_executed"])
        self.assertFalse(result["publication_certified"])
        findings = json.loads((destination / "studies" /
                               "THREE_STUDIES_RESULTS.json").read_text())
        self.assertFalse(findings["external_research_certified"])
        self.assertIn("simulated index net wealth",
            (destination / "RESEARCH_RELEASE.html").read_text())
