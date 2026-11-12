"""Local FastAPI research workstation smoke tests.

No network, brokerage credentials, or live market data required.
"""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from workstation_api import service
from workstation_api.app import RunRequest, app


class ResearchWorkstationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="react_quantlab_test_")
        self.data_patch = patch.object(service, "DATA", Path(self.temp.name) / "data")
        self.result_patch = patch.object(service, "RESULTS", Path(self.temp.name) / "results")
        self.data_patch.start()
        self.result_patch.start()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        self.result_patch.stop()
        self.data_patch.stop()
        self.temp.cleanup()

    def test_local_health_and_no_order_api(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["read_only_market_data"])
        self.assertFalse(body["broker_orders_enabled"])
        self.assertNotIn("DHAN_ACCESS_TOKEN", response.text)

    def test_rejects_remote_host_and_origin(self):
        remote = self.client.get("/api/health", headers={"host": "malicious.example"})
        self.assertEqual(remote.status_code, 403)
        origin = self.client.post("/api/datasets/synthetic",
                                  headers={"origin": "https://malicious.example"})
        self.assertEqual(origin.status_code, 403)

    def test_explicit_synthetic_dataset_and_python_optimization(self):
        made = self.client.post("/api/datasets/synthetic")
        self.assertEqual(made.status_code, 200, made.text)
        self.assertEqual(made.json()["kind"], "synthetic")
        listing = self.client.get("/api/datasets").json()["datasets"]
        self.assertTrue(any(r["id"] == "synthetic" and r["ready"] for r in listing))
        audit = self.client.get("/api/datasets/synthetic/audit")
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertGreaterEqual(audit.json()["number_of_securities"], 10)
        model = self.client.post("/api/models/minimum-variance", json={
            "dataset_id": "synthetic", "method": "shrinkage", "max_weight": 0.3,
        })
        self.assertEqual(model.status_code, 200, model.text)
        weights = model.json()["weights"]
        self.assertAlmostEqual(sum(item["weight"] for item in weights), 1.0, places=5)
        self.assertTrue(all(0 <= item["weight"] <= 0.30001 for item in weights))

    def test_backtest_request_rejects_infeasible_caps(self):
        with self.assertRaises(ValidationError):
            RunRequest(dataset_id="synthetic", top_n=3, max_weight=.2)
        with self.assertRaises(ValidationError):
            RunRequest(dataset_id="synthetic", factor_weights={"momentum": 0})

    def test_invalid_archive_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("../prices.csv", "date,FOO\n2026-01-01,1\n")
            z.writestr("membership.csv", "date,ticker,eligible\n")
            z.writestr("benchmark.csv", "date,return\n")
        response = self.client.post("/api/datasets/import", files={
            "file": ("research.zip", buffer.getvalue(), "application/zip")
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(any((service.DATA / "workstation_imports").glob("*/prices.csv"))
                         if (service.DATA / "workstation_imports").exists() else False)

    def test_artifact_lookup_is_strict(self):
        with self.assertRaises(ValueError):
            service.artifact_path("../secret", "research_manifest.json")
        with self.assertRaises(ValueError):
            service.artifact_path("irrelevant", "../../.env")


if __name__ == "__main__":
    unittest.main()
