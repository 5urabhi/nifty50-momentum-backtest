"""Source completion is explicit, exact, local-only and never market-data certification."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import csv
import json
import unittest

import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import service, source_completion
from workstation_api.app import app


class SourceCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="quantlab_source_worklist_")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.data = root / "data"
        self.folder = self.data / "workstation_imports" / "source_worklist_test"
        self.folder.mkdir(parents=True)
        self.id = "upload_source_worklist_test"
        self.patch_data = patch.object(service, "DATA", self.data)
        self.patch_data.start()
        self.addCleanup(self.patch_data.stop)
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.addCleanup(self.client.close)
        self.dates = pd.date_range("2023-01-31", periods=16, freq="ME")
        pd.DataFrame({
            "date": self.dates,
            "A": [100.0 + i for i in range(16)],
            "B": [200.0 + i if i != 4 else None for i in range(16)],
        }).to_csv(self.folder / "prices.csv", index=False)
        pd.DataFrame({
            "date": [self.dates[0], self.dates[0]],
            "ticker": ["A", "B"],
            "eligible": [True, True],
        }).to_csv(self.folder / "membership.csv", index=False)
        pd.DataFrame({"date": self.dates, "return": [0.01] * 16}).to_csv(
            self.folder / "benchmark.csv", index=False)

    def test_exact_missing_observations_and_20_percent_policy(self):
        work = source_completion.worklist(
            self.id, validation_start="2023-09-30",
            final_test_start="2024-01-31", selected_factors=["momentum", "value"])
        self.assertEqual(work["dataset_id"], self.id)
        self.assertFalse(work["readiness"]["independent_source_certified"])
        self.assertFalse(work["summary"]["publication_certified"])
        self.assertEqual(work["summary"]["missing_eligible_prices"], 1)
        self.assertGreaterEqual(work["summary"]["missing_eligible_forward_returns"], 1)
        self.assertEqual(work["summary"]["preferred_prevalidation_months_with_20pct_buffer"], 44)
        self.assertGreater(work["summary"]["prevalidation_shortfall_to_buffer"], 0)
        self.assertIn("eligible_price_unavailable",
                      {x["problem"] for x in work["missing_security_month_preview"]})
        self.assertTrue(any(x["status"] == "blocked" and
                            x["category"] == "Point-in-time source reconciliation"
                            for x in work["actions"]))
        self.assertTrue(any("niftyindices.com" in x["official_source_url"]
                            for x in work["actions"]))
        self.assertFalse(work["downloadable_original_market_data"])

    def test_zip_contains_all_gap_rows_and_zero_original_price_data(self):
        bundle = source_completion.export_zip(
            self.id, validation_start="2023-09-30", final_test_start="2024-01-31")
        with ZipFile(BytesIO(bundle)) as zip:
            self.assertEqual(set(zip.namelist()), {
                "SOURCE_WORKLIST.json", "MISSING_SECURITY_MONTHS.csv",
                "MISSING_CALENDAR_MONTHS.csv", "UNRESOLVED_HISTORICAL_IDENTITIES.csv",
                "SOURCE_ACTIONS.csv", "README.txt",
            })
            report = json.loads(zip.read("SOURCE_WORKLIST.json"))
            missing = list(csv.DictReader(
                zip.read("MISSING_SECURITY_MONTHS.csv").decode("utf-8").splitlines()))
            self.assertEqual(len(missing), report["missing_security_month_count"])
            self.assertTrue(any(r["ticker"] == "B" for r in missing))
            for name in zip.namelist():
                self.assertNotIn("2023-01-31,100.0,200.0",
                                 zip.read(name).decode("utf-8"))
            self.assertIn("NOT", zip.read("README.txt").decode("utf-8"))

    def test_missing_price_matrix_still_explains_what_is_blocked(self):
        (self.folder / "prices.csv").unlink()
        work = source_completion.worklist(self.id)
        self.assertIsNone(work["summary"]["price_months"])
        self.assertIsNone(work["summary"]["missing_eligible_prices"])
        self.assertTrue(any(x["category"] == "Monthly price panel" and
                            x["status"] == "blocked" for x in work["actions"]))
        with ZipFile(BytesIO(source_completion.export_zip(self.id))) as zip:
            self.assertIn("date,ticker,problem", zip.read(
                "MISSING_SECURITY_MONTHS.csv").decode("utf-8"))
            self.assertNotIn("prices.csv", zip.namelist())

    def test_corrupt_price_calendar_keeps_worklist_actionable(self):
        raw=pd.read_csv(self.folder / "prices.csv")
        raw.loc[2,"date"]=raw.loc[1,"date"]
        raw.to_csv(self.folder / "prices.csv",index=False)
        report=source_completion.worklist(self.id)
        self.assertFalse(report["exact_gap_calculation_available"])
        self.assertIn("Coverage calculation blocked:",report["coverage_warnings"][0])
        self.assertTrue(any(x["category"]=="Monthly price panel" and
                            x["status"]=="blocked" for x in report["actions"]))
        self.assertFalse(report["summary"]["publication_certified"])

    def test_source_status_is_never_promoted_by_reviewer_flag_or_filename(self):
        (self.folder / "EVIDENCE_REVIEW.json").write_text(
            '{"verified":true,"licensed":true,"independent":true}')
        work = source_completion.worklist(self.id)
        self.assertFalse(work["summary"]["independent_original_source_certified"])
        self.assertFalse(work["readiness"]["publication_certified"])
        self.assertFalse(work["summary"]["historical_structural_run_ready"])

    def test_csv_output_sanitizes_spreadsheet_formula_cells(self):
        example = source_completion._csv(
            ["date", "ticker", "problem"], [{
                "date":"2024-01-31", "ticker":'=HYPERLINK("http://x")',
                "problem":"+SUM(1,1)",
            }])
        record = next(csv.DictReader(example.splitlines()))
        self.assertTrue(record["ticker"].startswith("'="))
        self.assertTrue(record["problem"].startswith("'+"))

    def test_http_worklist_and_export_are_readonly_and_validated(self):
        query = {"validation_start":"2023-09-30", "final_test_start":"2024-01-31"}
        r = self.client.get("/api/workspace/historical-sources/"+self.id, params=query)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreater(r.json()["missing_security_month_count"], 0)
        zipresponse = self.client.get(
            "/api/workspace/historical-sources/"+self.id+"/worklist.zip", params=query)
        self.assertEqual(zipresponse.status_code, 200, zipresponse.text)
        self.assertIn("application/zip", zipresponse.headers["content-type"])
        self.assertEqual(zipresponse.headers["cache-control"], "no-store")
        with ZipFile(BytesIO(zipresponse.content)) as data:
            self.assertIn("SOURCE_WORKLIST.json", data.namelist())
        bad = self.client.get(
            "/api/workspace/historical-sources/"+self.id, params={"factors":"fake_factor"})
        self.assertEqual(bad.status_code, 400)
        unknown = self.client.get("/api/workspace/historical-sources/unknown_source")
        self.assertEqual(unknown.status_code, 400)


if __name__ == "__main__":
    unittest.main()
