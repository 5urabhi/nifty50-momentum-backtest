"""Portable research evidence ZIP: exact archived bytes, not source certification."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import io
import json
import subprocess
import sys
import unittest

from fastapi.testclient import TestClient

from workstation_api import evidence_bundle, model_lab, research_library, research_next, result_evidence, service
from workstation_api.app import app


class EvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="quantlab_evidence_bundle_")
        self.root = Path(self.temp.name)
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.models = [{
            "model_id":"gbm","title":"Synthetic model","mode":"synthetic",
            "generated_utc":"2026-11-14T00:00:00Z","source":None,
            "source_sha256":None, "params":{"seed":2026,"volatility":.2},
            "metrics":[{"label":"Scenario VaR","value":.15,"unit":"decimal fraction"}],
            "plots":[],"table":[],"notes":[],"limitations":["Model generated seeded paths"],
        }]
        self.report = {
            "evidence_class":"synthetic_demo","readiness":"research_diagnostic_only",
            "metrics":[],"checks":[{"status":"blocked","name":"Source verification"}],
        }
        self.explanation = {"kind":"model_run","level":"researcher","formula":"dS = ..."}
        self.patches = [
            patch.object(research_library,"root",return_value=self.root),
            patch.object(model_lab,"read_saved_model",return_value=self.models[0]),
            patch.object(result_evidence,"summarize",return_value=self.report),
            patch.object(research_next,"explain_saved",return_value=self.explanation),
            patch.object(evidence_bundle,"_git_sha",return_value="a"*40),
        ]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.client.close()
        self.temp.cleanup()

    def test_model_bundle_contains_exact_saved_evidence(self):
        response=self.client.get("/api/workspace/evidence-bundles/model_run/test_model.zip")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers["content-type"],"application/zip")
        with ZipFile(io.BytesIO(response.content)) as archive:
            names=set(archive.namelist())
            self.assertIn("saved_result.json",names)
            self.assertIn("evidence_audit.json",names)
            self.assertIn("source_integrity.json",names)
            self.assertIn("verify_bundle.py",names)
            manifest=json.loads(archive.read("manifest.json"))
            self.assertFalse(manifest["raw_licensed_vendor_data_included"])
            self.assertFalse(manifest["independent_source_audit"])
            self.assertEqual(manifest["evidence_class"],"synthetic_demo")
            self.assertEqual(manifest["git_sha"],"a"*40)
            self.assertEqual(json.loads(archive.read("saved_result.json"))["params"]["seed"],2026)
            self.assertNotIn(b"DHAN_ACCESS_TOKEN",response.content)
            self.assertNotIn(b"bearer",response.content.lower())
            for filename,digest in manifest["member_sha256"].items():
                self.assertEqual(sha256(archive.read(filename)).hexdigest(),digest)

    def test_extracted_package_verifier_detects_corruption(self):
        path=evidence_bundle.bundle_path("model_run","test_model")
        extracted=self.root/"verified"
        extracted.mkdir()
        with ZipFile(path) as archive:archive.extractall(extracted)
        first=subprocess.run([sys.executable,str(extracted/"verify_bundle.py")],
                             cwd=extracted,capture_output=True,text=True)
        self.assertEqual(first.returncode,0,first.stdout+first.stderr)
        (extracted/"saved_result.json").write_text('{"tampered":true}')
        second=subprocess.run([sys.executable,str(extracted/"verify_bundle.py")],
                              cwd=extracted,capture_output=True,text=True)
        self.assertEqual(second.returncode,2)
        self.assertIn("CHANGED saved_result.json",second.stdout)

    def test_invalid_run_id_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"Select an existing"):
            evidence_bundle.bundle_path("model_run","../etc/passwd")
        with self.assertRaisesRegex(ValueError,"Select an existing"):
            evidence_bundle.bundle_path("bad-kind","test_model")

    def test_changed_original_source_is_reported_not_fabricated(self):
        path=self.root/"source"
        path.mkdir()
        original=path/"prices.csv"
        original.write_text("date,x\n2026-01-01,5\n")
        fingerprint=sha256(original.read_bytes()).hexdigest()
        mock=patch.object(service,"dataset_path",return_value=(path,{"label":"Observed"}))
        mock.start()
        try:
            verified=evidence_bundle._source_integrity(
                {"dataset_id":"upload_example"},{"prices.csv":fingerprint})
            self.assertTrue(verified["observations_replayable"])
            original.write_text("date,x\n2026-01-01,9\n")
            changed=evidence_bundle._source_integrity(
                {"dataset_id":"upload_example"},{"prices.csv":fingerprint})
            self.assertFalse(changed["observations_replayable"])
            self.assertEqual(changed["files"][0]["status"],"changed")
        finally:mock.stop()
