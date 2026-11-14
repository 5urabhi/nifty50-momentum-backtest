"""Evidence assistant regression tests: no fabricated alpha, data or vendor calls."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from workstation_api import research_assistant, research_next, result_evidence
from workstation_api.app import app


def evidence():
    return {
        "id": "run_01", "kind": "research_run", "model": "Saved index experiment",
        "evidence_class": "synthetic_demo", "readiness": "research_diagnostic_only",
        "observations": 36, "source": {
            "dataset_id": "synthetic", "dataset_kind": "synthetic",
            "source_hashes": {"prices.csv": "source_file_hash"}},
        "metrics": [
            {"name": "Strategy CAGR", "value": .12, "unit": "fraction per year",
             "detail": "Compounded saved net returns"},
            {"name": "Zero-rate Sharpe", "value": 1.2345, "unit": "ratio",
             "detail": "Explicit zero-rate convention"},
            {"name": "Max drawdown", "value": -.25, "unit": "fraction",
             "detail": "Saved peak-to-trough decline"},
        ],
        "checks": [
            {"name": "Source type", "status": "blocked",
             "detail": "synthetic_demo",
             "next_action": "Use independently sourced historical data."},
            {"name": "Independent PIT and return audit", "status": "blocked",
             "detail": "Missing official dated membership and TRI",
             "next_action": "Audit original point-in-time membership and TRI."},
            {"name": "Publication / live-trading certification", "status": "blocked",
             "detail": "No certification",
             "next_action": "Arrange independent evidence review."},
        ],
        "uncertainty": None,
    }


def explanation():
    return {
        "kind": "research_run", "id": "run_01", "level": "beginner",
        "model": "Multi-Factor Index Research",
        "explanation": "A saved research experiment ranks stocks by source-dated factors.",
        "formula": "score(i,t) = sum(weight_k * factor_k(i,t))",
        "warning": "No causal claim follows from computed returns.",
        "parameters": {"factor_weights": {"momentum": 0.7,
                                          "low_volatility": 0.3}},
        "limitations": ["A matching benchmark convention is required."],
    }


class SourceGroundedAssistantTests(unittest.TestCase):
    def setUp(self):
        self.a = patch.object(result_evidence, "summarize", return_value=evidence())
        self.b = patch.object(research_next, "explain_saved", return_value=explanation())
        self.a.start()
        self.b.start()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        self.b.stop()
        self.a.stop()

    def ask(self, question, level="beginner"):
        return research_assistant.answer("research_run", "run_01", question, level)

    def test_metric_is_exact_archived_value_and_unit(self):
        response = self.ask("What is the Sharpe ratio?")
        self.assertEqual(response["intent"], "metric")
        self.assertEqual(len(response["facts"]), 1)
        self.assertEqual(response["facts"][0]["value"], 1.2345)
        self.assertEqual(response["facts"][0]["unit"], "ratio")
        self.assertEqual(response["facts"][0]["source"], "saved_evidence.metrics")
        self.assertTrue(any(x["tab"] == "diagnostics" for x in response["references"]))
        self.assertEqual(response["engine"], "offline_deterministic_saved_evidence")
        self.assertEqual(response["evidence_class"], "synthetic_demo")

    def test_missing_metric_does_not_produce_a_number(self):
        response = self.ask("Explain the Sortino ratio")
        self.assertEqual(response["facts"], [])
        self.assertIn("no matching numeric metric", response["answer"])
        self.assertNotIn("1.2345", response["answer"])

    def test_returns_keep_raw_fraction_and_declared_horizon(self):
        response = self.ask("What is the CAGR?")
        self.assertEqual(response["facts"][0]["value"], 0.12)
        self.assertEqual(response["facts"][0]["unit"], "fraction per year")
        self.assertIn("10% per year", response["answer"])

    def test_unverified_synthetic_illustration_is_never_certified(self):
        response = self.ask("Can I trust this result?")
        self.assertIn("Synthetic demonstration", response["evidence_label"])
        self.assertIn("not established", response["answer"])
        self.assertTrue(any("observed" in value.lower() or "source" in value.lower()
                            for value in response["next_actions"]))
        self.assertTrue(any(x["tab"] == "validation" for x in response["references"]))

    def test_no_causal_inference_from_configured_factors(self):
        response = self.ask("Why did the strategy perform better?")
        self.assertEqual(response["intent"], "drivers")
        self.assertIn("cannot establish why", response["answer"])
        self.assertTrue(any("Configured momentum factor weight" == f["name"]
                            for f in response["facts"]))
        self.assertTrue(any("NOT observed factor attribution" in f["detail"]
                            for f in response["facts"]))

    def test_source_answer_is_snapshot_only_not_a_vendor_fetch(self):
        response = self.ask("What data is missing?")
        self.assertEqual(response["intent"], "data")
        self.assertIn("Dataset ID: synthetic", response["answer"])
        self.assertIn("not live brokerage coverage", response["answer"])
        self.assertTrue(any(r["tab"] == "evidence" for r in response["references"]))

    def test_comparison_does_not_invent_a_challenger(self):
        response = self.ask("Compare this to another model")
        self.assertEqual(response["intent"], "compare")
        self.assertEqual(response["facts"], [])
        self.assertIn("second run has not been selected", response["answer"])
        self.assertTrue(any(x["tab"] == "compare" for x in response["references"]))

    def test_unknown_questions_fail_with_explained_boundaries(self):
        response = self.ask("Who will win tomorrow's trading session?")
        self.assertEqual(response["intent"], "unsupported")
        self.assertEqual(response["facts"], [])
        self.assertIn("cannot construct a speculative answer", response["answer"])

    def test_method_level_uses_exact_archived_equation(self):
        response = self.ask("Explain the math formula", "mathematical")
        self.assertEqual(response["intent"], "method")
        self.assertIn("score(i,t)", response["answer"])
        self.assertTrue(any(x["tab"] == "evidence" for x in response["references"]))

    def test_api_rejects_extra_fields_long_question_and_bad_context(self):
        url = "/api/workspace/results/research_run/run_01/ask"
        success = self.client.post(url, json={"question": "What is the Sharpe ratio?"})
        self.assertEqual(success.status_code, 200, success.text)
        self.assertNotIn("DHAN_ACCESS_TOKEN", success.text)
        self.assertEqual(success.json()["run_id"], "run_01")
        self.assertEqual(self.client.post(url,json={"question": "?"}).status_code, 422)
        self.assertEqual(self.client.post(url,json={"question": "x"*401}).status_code, 422)
        self.assertEqual(self.client.post(url,json={
            "question": "What is Sharpe?", "access_token": "never"}).status_code, 422)
        self.assertEqual(self.client.post(url,json={
            "question": "What is Sharpe?", "level": "predict_the_future"}).status_code, 422)

    def test_empty_or_invalid_identifier_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError,"Invalid saved run identifier"):
            research_assistant.answer("model_run", "../outside", "What is Sharpe?")
        with self.assertRaisesRegex(ValueError, "2–400"):
            research_assistant.answer("model_run", "run_01", "  ")
        with self.assertRaisesRegex(ValueError, "Select a saved"):
            research_assistant.answer("unknown", "run_01", "What happened?")


if __name__ == "__main__":
    unittest.main()
