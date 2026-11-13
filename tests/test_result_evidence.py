"""Regression coverage for source-bound results evidence.

Synthetic fixtures are constructed in isolated temp directories. No market
access, live trading, token exposure, or empirical return claim is involved.
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import model_lab, result_evidence, service
from workstation_api.app import app


class ResultEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="quantlab_result_evidence_")
        self.root = Path(self.tmp.name) / "runs"
        self.root.mkdir()
        self.patched = patch.object(service, "RESULTS", self.root)
        self.patched.start()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        self.patched.stop()
        self.tmp.cleanup()

    def make_run(self, run_id: str, *, months: int = 48, bonus: float = 0.0,
                 dataset_id: str = "synthetic", benchmark_offset: float = 0.,
                 source_hash: str = "same_hash", extra_invalid: bool = False):
        folder = self.root / run_id
        folder.mkdir()
        meta = {
            "generated_utc": "2026-10-01T00:00:00Z",
            "config": {"name": run_id, "validation_start": "2021-06-01",
                       "final_test_start": "2022-01-01"},
            "metrics_by_split": {"development": {"observations": 20},
                                 "final_test": {"observations": 24}},
            "input_sha256": {"prices.csv": source_hash},
        }
        (folder / "research_manifest.json").write_text(json.dumps(meta), encoding="utf-8")
        (folder / "workstation_run.json").write_text(
            json.dumps({"dataset_id": dataset_id, "dataset_kind": "synthetic"}),
            encoding="utf-8")
        dates = pd.date_range("2020-01-31", periods=months, freq="ME")
        rows = []
        for i, date in enumerate(dates):
            rows.append({"date": date.date().isoformat(),
                         "strategy_net": .015 + .009 * math.sin(i * .6) + bonus,
                         "benchmark": .010 + .007 * math.cos(i * .5) + benchmark_offset,
                         "strategy_gross": .02, "turnover": .05})
        if extra_invalid:
            rows[4]["strategy_net"] = None
        pd.DataFrame(rows).to_csv(folder / "monthly_results.csv", index=False)
        return folder

    def test_run_evidence_is_source_bound_and_never_certifies_synthetic(self):
        self.make_run("baseline")
        result = result_evidence.summarize("research_run", "baseline")
        self.assertEqual(result["evidence_class"], "synthetic_demo")
        self.assertEqual(result["readiness"], "research_diagnostic_only")
        self.assertEqual(result["observations"], 48)
        self.assertIn("input_sha256", result["source"].get("source_hashes", {}))
        self.assertIsNotNone(result["uncertainty"])
        self.assertIsNotNone(result["hac"])
        self.assertEqual(result["uncertainty"]["replications"], 1000)
        self.assertTrue(any(x["status"] == "blocked" for x in result["checks"]))
        self.assertTrue(any(x["kind"] == "histogram2d" for x in result["plots"]))
        self.assertTrue(any(x["kind"] == "line2d" for x in result["plots"]))
        self.assertIsNone(result.get("certified"))

    def test_endpoint_exposes_saved_only_and_validates_model_result(self):
        self.make_run("baseline")
        response = self.client.get("/api/workspace/results/research_run/baseline/evidence")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["observations"], 48)
        self.assertNotIn("DHAN_ACCESS_TOKEN", response.text)
        self.assertNotIn("broker_order", response.text)
        invalid = self.client.get("/api/workspace/results/research_run/unknown/evidence")
        self.assertNotEqual(invalid.status_code, 200)
        malformed = self.client.post("/api/workspace/results/paired-comparison",
                                     json={"baseline_id": "baseline", "challenger_ids": []})
        self.assertEqual(malformed.status_code, 422)

    def test_reproducible_block_bootstrap_with_nonzero_uncertainty(self):
        sample = np.array([.02 * math.sin(i * .37) + .004 for i in range(60)])
        a = result_evidence._bootstrap(sample)
        b = result_evidence._bootstrap(sample)
        self.assertEqual(a, b)
        self.assertLess(a["lower_pp_per_year"], a["upper_pp_per_year"])
        self.assertIsNone(result_evidence._bootstrap(sample[:23]))
        self.assertGreaterEqual(a["block_months"], 2)

    def test_partial_returns_are_rejected_explicitly_not_forward_filled(self):
        self.make_run("partial", extra_invalid=True)
        result = result_evidence.summarize("research_run", "partial")
        self.assertEqual(result["observations"], 47)
        self.assertEqual(result["rejected_rows"], 1)
        self.assertEqual(result["checks"][0]["status"], "warning")

    def test_duplicate_months_or_unsorted_records_fail_closed(self):
        path = self.make_run("duplicates") / "monthly_results.csv"
        frame = pd.read_csv(path)
        frame.loc[1, "date"] = frame.loc[0, "date"]
        frame.to_csv(path, index=False)
        with self.assertRaisesRegex(ValueError, "duplicated"):
            result_evidence.summarize("research_run", "duplicates")

    def test_short_samples_do_not_get_fabricated_confidence(self):
        self.make_run("short", months=14)
        result = result_evidence.summarize("research_run", "short")
        self.assertIsNone(result["uncertainty"])
        self.assertIsNone(result["hac"])
        self.assertEqual(result["checks"][1]["status"], "blocked")
        self.assertTrue(all(plot["kind"] != "histogram2d" or
                            len(plot["x"]) > 0 for plot in result["plots"]))

    def test_paired_holm_adjustment_and_source_checks(self):
        self.make_run("baseline")
        self.make_run("challenger1", bonus=.003)
        self.make_run("challenger2", bonus=-.001)
        result = result_evidence.paired_comparison("baseline", ["challenger1", "challenger2"])
        self.assertEqual(result["paired_months"], 48)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["evidence_class"], "synthetic_demo")
        for row in result["rows"]:
            self.assertIsNotNone(row["ci95_low_pp"])
            self.assertIsNotNone(row["ci95_high_pp"])
            if row["hac_p_nominal"] is not None:
                self.assertGreaterEqual(row["holm_adjusted_p"], row["hac_p_nominal"])
        self.assertEqual(len(result["plot"]["traces"]), 3)
        response = self.client.post("/api/workspace/results/paired-comparison", json={
            "baseline_id": "baseline", "challenger_ids": ["challenger1", "challenger2"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["paired_months"], 48)

    def test_paired_comparison_refuses_changed_data_or_benchmark(self):
        self.make_run("base")
        self.make_run("changed", source_hash="changed_hash")
        with self.assertRaisesRegex(ValueError, "checksums"):
            result_evidence.paired_comparison("base", ["changed"])
        self.make_run("different_benchmark", benchmark_offset=.005)
        with self.assertRaisesRegex(ValueError, "benchmark"):
            result_evidence.paired_comparison("base", ["different_benchmark"])
        self.make_run("different_dataset", dataset_id="other")
        with self.assertRaisesRegex(ValueError, "same dataset"):
            result_evidence.paired_comparison("base", ["different_dataset"])
        with self.assertRaisesRegex(ValueError, "distinct"):
            result_evidence.paired_comparison("base", ["base"])

    def test_paired_comparison_requires_common_24_months(self):
        self.make_run("full", months=48)
        small = self.make_run("small", months=14)
        with self.assertRaisesRegex(ValueError, "24 common"):
            result_evidence.paired_comparison("full", ["small"])
        self.assertTrue(small.is_dir())

    def test_model_evidence_does_not_treat_synthetic_fixture_as_observed(self):
        fixture = {"model_id": "rolling_vol", "title": "Rolling volatility",
                   "mode": "historical", "source": {"dataset_id": "synthetic",
                       "dataset_kind": "synthetic", "observations": 70},
                   "metrics": [{"label": "Observed common returns", "value": 70, "unit": ""}],
                   "plots": [], "limitations": ["Fitted in sample"]}
        with patch.object(model_lab, "read_saved_model", return_value=fixture):
            report = result_evidence.summarize("model_run", "demo")
        self.assertEqual(report["evidence_class"], "synthetic_demo")
        self.assertEqual(report["readiness"], "research_diagnostic_only")
        self.assertIsNone(report["uncertainty"])
        self.assertTrue(any(item["status"] == "blocked" for item in report["checks"]))


if __name__ == "__main__":
    unittest.main()
