"""Official NSE MCP is informational-only; local file intake is offline and source-preserving."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED
import json
import stat
import unittest

import httpx

from workstation_api import nse_source_automation as nse


class NSESourceAutomationTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="quantlab_nse_intake_test_")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.input = self.base / "downloads"
        self.input.mkdir()
        self.output = self.base / "local_private"

    def _zip(self, name, members):
        bio = BytesIO()
        with ZipFile(bio, "w", ZIP_DEFLATED) as archive:
            for member, content in members.items():
                archive.writestr(member, content)
        file = self.input / name
        file.write_bytes(bio.getvalue())
        return file

    def test_offline_intake_preserves_raw_zip_and_creates_unverified_manifest(self):
        csv = b"Symbol,Weightage (%)\nA,60\nB,40\n"
        zipfile = self._zip("nifty_monthly.zip", {"jan.csv": csv})
        result = nse.intake_local_exports([zipfile], root=self.output)
        folder = Path(result["directory"])
        self.assertTrue((folder / "originals" / zipfile.name).is_file())
        self.assertEqual((folder / "jan.csv").read_bytes(), csv)
        self.assertEqual(result["weightage_csv_candidates"], 1)
        self.assertFalse(result["source_verified_by_nse"])
        self.assertFalse(result["license_verified"])
        self.assertFalse(result["tri_overwritten"])
        template = (folder / "WEIGHTAGE_MANIFEST_TEMPLATE.csv").read_text()
        self.assertIn("file,snapshot_date,published_at,source_url", template)
        self.assertIn("jan.csv,,,https://www.niftyindices.com", template)
        self.assertEqual(zipfile.read_bytes(), (folder / "originals" / zipfile.name).read_bytes())
        self.assertTrue((folder / "SOURCE_INTAKE.json").exists())

    def test_detect_zip_slip_duplicate_members_and_symlink(self):
        cases = [
            {"../out.csv": b"date,close\n2026-01-01,9\n"},
            {"nested/out.csv": b"a,b\n1,2\n"},
            {"bad.csv": b"date,x\n1,2\n"},
        ]
        for idx, contents in enumerate(cases):
            file = self._zip("file_%d.zip" % idx, contents)
            if idx == 2:
                continue
            with self.assertRaisesRegex(ValueError, "flat|not hidden|extension"):
                nse.intake_local_exports([file], root=self.output)
        symlink = self.input / "link.csv"
        symlink.symlink_to(self.input / "file_2.zip")
        with self.assertRaises(ValueError):
            nse.intake_local_exports([symlink], root=self.output)
        self.assertEqual(list(self.output.glob(".*.pending")), [])

    def test_malformed_zip_and_duplicate_csv_names_do_not_leave_partial_intake(self):
        broken = self.input / "bad.zip"
        broken.write_bytes(b"not a zip")
        with self.assertRaisesRegex(ValueError, "Invalid ZIP"):
            nse.intake_local_exports([broken], root=self.output)
        left = self.input / "weights.csv"
        left.write_text("Symbol,Weightage (%)\nA,100\n")
        archive = self._zip("combined.zip", {"weights.csv": b"Symbol,Weightage (%)\nB,100\n"})
        with self.assertRaisesRegex(ValueError, "Two reports share"):
            nse.intake_local_exports([left, archive], root=self.output)
        self.assertFalse(any(self.output.iterdir()))

    def test_recognized_empty_or_unsupported_files_fail_closed(self):
        bad = self.input / "a.html"
        bad.write_text("html")
        with self.assertRaisesRegex(ValueError, "not supported"):
            nse.intake_local_exports([bad], root=self.output)
        too_many = [bad] * 21
        with self.assertRaisesRegex(ValueError, "1-20"):
            nse.intake_local_exports(too_many, root=self.output)

    def _transport(self, *, rate_limited=False, use_sse=False):
        calls = []

        def handle(request):
            message = json.loads(request.content.decode("utf-8"))
            calls.append((request, message))
            if rate_limited and message["method"] == "tools/list":
                return httpx.Response(429)
            method = message["method"]
            if method == "initialize":
                result = {"protocolVersion": nse.PROTOCOL,
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "nse-bhavcopy", "version": "1"}}
            elif method == "notifications/initialized":
                return httpx.Response(202)
            elif method == "tools/list":
                result = {"tools": [
                    {"name": "get_corporate_actions", "description": "Read actions",
                     "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}}},
                    {"name": "do_orders", "description": "unsupported",
                     "inputSchema": {}}]}
            elif method == "tools/call":
                self.assertEqual(message["params"]["name"], "get_corporate_actions")
                result = {"content": [{"type": "text", "text": "Informational company action"}],
                          "isError": False}
            else:
                raise AssertionError("Unexpected method " + method)
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": result}
            if use_sse:
                body = ("event: message\n"
                        "data: " + json.dumps(reply) + "\n\n").encode("utf-8")
                return httpx.Response(200, content=body,
                                      headers={"content-type": "text/event-stream"})
            return httpx.Response(200, json=reply,
                                  headers={"mcp-session-id": "testing-only"})
        return httpx.MockTransport(handle), calls

    def test_mcp_discover_and_single_informational_lookup_no_download_or_orders(self):
        transport, calls = self._transport()
        with nse.NSEInfoMCP(transport=transport) as client:
            session = client.initialize()
            self.assertEqual(session["serverInfo"]["name"], "nse-bhavcopy")
            tools = client.tools()
            self.assertEqual(len(tools), 2)
            self.assertTrue(tools[0]["informational_lookup_only"])
            self.assertFalse(tools[1]["informational_lookup_only"])
            reply = client.one_lookup("get_corporate_actions", {"symbol": "RELIANCE"})
            self.assertFalse(reply["isError"])
            with self.assertRaisesRegex(ValueError, "allowlisted"):
                client.one_lookup("do_orders", {})
            self.assertEqual(client.session, "testing-only")
        self.assertEqual([x[1]["method"] for x in calls], [
            "initialize", "notifications/initialized", "tools/list",
            "tools/list", "tools/call"])
        self.assertEqual(calls[0][0].url.host, "mcp.nseindia.in")
        self.assertEqual(calls[1][0].headers["mcp-protocol-version"], nse.PROTOCOL)
        self.assertEqual(calls[4][0].headers["mcp-session-id"], "testing-only")

    def test_mcp_sse_response_and_provider_throttling(self):
        transport, _ = self._transport(use_sse=True)
        with nse.NSEInfoMCP("bhavcopy", transport=transport) as client:
            client.initialize()
            self.assertEqual(client.tools()[0]["name"], "get_corporate_actions")
        blocked, _ = self._transport(rate_limited=True)
        with nse.NSEInfoMCP(transport=blocked) as client:
            client.initialize()
            with self.assertRaisesRegex(ValueError, "rate-limited"):
                client.tools()

    def test_mcp_cannot_request_unapproved_host_or_bulk_calls(self):
        with self.assertRaisesRegex(ValueError, "official"):
            nse.NSEInfoMCP("arbitrary_url")
        transport, _ = self._transport()
        with nse.NSEInfoMCP(transport=transport) as client:
            client.initialize()
            with self.assertRaisesRegex(ValueError, "too large"):
                client.one_lookup("get_stock_history", {"symbol": "A"*6000})


if __name__ == "__main__":
    unittest.main()
