"""NSE MCP is used in the in-app API; provider errors are never valid zero-events."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile
import json
import unittest

from fastapi.testclient import TestClient

from workstation_api import nse_mcp_workspace, nse_source_automation, service
from workstation_api.app import app


class FakeMCP:
    calls = []
    corporate_failure = False
    history_failure = False

    def __init__(self, server="bhavcopy"):
        if server != "bhavcopy":
            raise AssertionError("An unexpected remote server was requested")
        self.server = server

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def initialize(self):
        return {"protocolVersion": "2025-06-18"}

    def tools(self):
        return [{"name": t["tool"], "informational_lookup_only": True}
                for t in nse_mcp_workspace.TASKS]

    def one_lookup(self, tool, arguments):
        type(self).calls.append((tool, arguments))
        if tool == "get_corporate_actions" and type(self).corporate_failure:
            payload = {"error": "Corporate actions could not be fetched from NSE right now. "
                                "This does NOT mean there are none."}
        elif tool == "get_stock_history" and type(self).history_failure:
            payload = {"error": "Stock history unavailable"}
        elif tool == "get_corporate_actions":
            payload = {"events": [{"symbol": arguments["symbol"], "exDate": "2026-06-03"}]}
        elif tool == "get_stock_history":
            payload = {"prices": [{"date": "2026-11-10", "close": 151.5}]}
        elif tool == "get_index_history":
            payload = {"levels": [{"date": "2026-11-10", "close": 26123.2}]}
        else:
            payload = {"symbols": ["RELIANCE", "TATASTEEL"]}
        return {"content": [{"type": "text", "text": json.dumps(payload)}],
                "isError": False}


class NSEInAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="quantlab_nse_ui_test_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        patcher = patch.object(service, "DATA", self.data)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher2 = patch.object(nse_mcp_workspace.nse, "NSEInfoMCP", FakeMCP)
        patcher2.start()
        self.addCleanup(patcher2.stop)
        patcher3 = patch.object(nse_mcp_workspace, "MIN_INTERVAL_SECONDS", 0.0)
        patcher3.start()
        self.addCleanup(patcher3.stop)
        nse_mcp_workspace._NEXT_REMOTE_AT = 0.0
        FakeMCP.calls = []
        FakeMCP.corporate_failure = False
        FakeMCP.history_failure = False
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.addCleanup(self.client.close)

    def test_capabilities_auto_load_never_contact_nse_or_modify_data(self):
        response = self.client.get("/api/workspace/nse-sources/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["connection"], "not_checked")
        self.assertFalse(body["research_data_write_allowed"])
        self.assertEqual(len(body["tasks"]), 4)
        self.assertEqual(FakeMCP.calls, [])
        self.assertEqual(list(self.data.iterdir()), [])

    def test_provider_nested_error_is_unavailable_not_no_actions(self):
        self.assertRaisesRegex(ValueError, "could not fetch",
            nse_mcp_workspace._read_result,
            {"content": [{"type": "text", "text": json.dumps({
                "error": "Corporate actions for RELIANCE could not be fetched from NSE"
            })}], "isError": False})
        FakeMCP.corporate_failure = True
        response = self.client.post("/api/workspace/nse-sources/query", json={
            "task": "corporate_actions", "symbol": "RELIANCE",
            "from_date": "2026-01-01", "to_date": "2026-11-14",
        })
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "provider_unavailable")
        self.assertIsNone(payload["data"])
        self.assertFalse(payload["no_events_verified"])
        self.assertFalse(payload["research_data_updated"])
        self.assertIn("not zero", payload["message"])
        self.assertEqual(FakeMCP.calls[0][0], "get_corporate_actions")

    def test_stock_history_auto_checks_corporate_actions_before_raw_prices(self):
        FakeMCP.corporate_failure = True
        response = self.client.post("/api/workspace/nse-sources/query", json={
            "task": "stock_history", "symbol": "RELIANCE", "months": 3,
            "end_date": "2026-11-14",
        })
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["status"], "available")
        self.assertEqual([x[0] for x in FakeMCP.calls],
                         ["get_corporate_actions", "get_stock_history"])
        self.assertTrue(any("unavailable" in warning.lower()
                            for warning in data["warnings"]))
        self.assertTrue(any("not a dividend-inclusive" in warning
                            for warning in data["warnings"]))
        self.assertIsNone(data["corporate_actions_context"])
        self.assertFalse(data["research_data_updated"])
        self.assertEqual(data["data"]["prices"][0]["close"], 151.5)

    def test_stock_history_failure_never_reports_success_or_zero(self):
        FakeMCP.history_failure = True
        response = self.client.post("/api/workspace/nse-sources/query", json={
            "task": "stock_history", "symbol": "RELIANCE",
            "end_date": "2026-11-14",
        })
        self.assertEqual(response.json()["status"], "provider_unavailable")
        self.assertFalse(response.json()["no_events_verified"])
        self.assertFalse(response.json()["research_data_updated"])

    def test_connection_and_index_are_informational(self):
        response = self.client.post("/api/workspace/nse-sources/check", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "connected")
        idx = self.client.post("/api/workspace/nse-sources/query", json={
            "task": "index_history", "index_name": "Nifty 50",
            "months": 6, "end_date": "2026-11-14"})
        self.assertEqual(idx.status_code, 200, idx.text)
        self.assertEqual(idx.json()["status"], "available")
        self.assertTrue(any("not the NIFTY 50 TRI" in warning
                            for warning in idx.json()["warnings"]))

    def test_in_app_input_bounds_and_local_origin_security(self):
        invalid = self.client.post("/api/workspace/nse-sources/query", json={
            "task": "stock_history", "symbol": "../DANGEROUS", "months": 3})
        self.assertEqual(invalid.status_code, 400)
        too_many = self.client.post("/api/workspace/nse-sources/query", json={
            "task": "stock_history", "symbol": "RELIANCE", "months": 20})
        self.assertEqual(too_many.status_code, 422)
        external = self.client.post("/api/workspace/nse-sources/query",
                                    headers={"Origin": "https://arbitrary-site.example"},
                                    json={"task": "symbol_search", "query": "TATA"})
        self.assertEqual(external.status_code, 403)
        self.assertEqual(FakeMCP.calls, [])

    def test_browser_upload_intakes_safe_zip_no_tri_or_research_replacement(self):
        original = BytesIO()
        with ZipFile(original, "w", ZIP_DEFLATED) as zip:
            zip.writestr("report/weights.csv", "Symbol,Weightage (%)\nA,50\nB,50\n")
            zip.writestr("README.txt", "Publisher's note")
        answer = self.client.post("/api/workspace/nse-sources/intake", files=[
            ("files", ("monthly.zip", original.getvalue(), "application/zip"))])
        self.assertEqual(answer.status_code, 200, answer.text)
        result = answer.json()
        self.assertEqual(result["status"], "prepared_unverified")
        self.assertTrue(result["tri_preserved"])
        self.assertFalse(result["research_data_updated"])
        self.assertEqual(result["receipt"]["weightage_csv_candidates"], 1)
        folder = Path(result["receipt"]["directory"])
        self.assertTrue(folder.is_dir())
        self.assertTrue((folder / "originals/monthly.zip").is_file())
        self.assertIn("weights.csv", [x.name for x in folder.iterdir()])
        self.assertTrue((folder / "WEIGHTAGE_MANIFEST_TEMPLATE.csv").is_file())
        self.assertFalse((self.data / "workstation_imports").exists())

    def test_browser_upload_rejects_zip_slip_without_partial_saved_source(self):
        archive = BytesIO()
        with ZipFile(archive, "w", ZIP_DEFLATED) as zip:
            zip.writestr("../secret.csv", "secret")
        answer = self.client.post("/api/workspace/nse-sources/intake", files=[
            ("files", ("evil.zip", archive.getvalue(), "application/zip"))])
        self.assertEqual(answer.status_code, 400)
        base = self.data / "nse/authorized_intake"
        self.assertFalse(base.exists() and list(base.iterdir()))
        self.assertFalse((self.root / "secret.csv").exists())


if __name__ == "__main__":
    unittest.main()
