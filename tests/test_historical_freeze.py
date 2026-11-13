"""Synthetic-only regression of historical readiness and frozen study gates.

No actual NSE claims or Dhan tokens: invented fixture values test rejection
and byte-for-byte locking, not market accuracy.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import frozen_study, historical_readiness, service
from workstation_api.app import app


class HistoricalFrozenResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="quantlab_frozen_sources_")
        root = Path(self.tmp.name)
        self.data = root / "data"
        self.results = root / "results" / "workstation_runs"
        self.results.mkdir(parents=True)
        self.dataset = self.data / "workstation_imports" / "audit_fixture"
        self.dataset.mkdir(parents=True)
        self.data_patch = patch.object(service, "DATA", self.data)
        self.results_patch = patch.object(service, "RESULTS", self.results)
        self.data_patch.start()
        self.results_patch.start()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.dates = pd.date_range("2017-01-31", periods=80, freq="ME")
        self.tickers = ["ALFA", "BETA", "GAMMA", "DELTA", "EPS"]
        self._write_data()
        self.config = {
            "name": "synthetic_unit_fixture_not_empirical",
            "factor_weights": {"momentum": 1.0},
            "top_n": 5, "weighting": "equal", "max_weight": .25,
            "rebalance_every": 3, "cost_bps": 10, "execution_lag": 1,
            "momentum_formation": 12, "momentum_skip": 1,
            "volatility_lookback": 12, "sector_cap": None,
            "validation_start": self.dates[50].date().isoformat(),
            "final_test_start": self.dates[60].date().isoformat(),
        }

    def tearDown(self):
        self.client.close()
        self.results_patch.stop()
        self.data_patch.stop()
        self.tmp.cleanup()

    def _write_data(self):
        t = np.arange(len(self.dates))
        prices = pd.DataFrame(
            {name:100 * np.exp((.007 + j*.0007)*t) for j,name in enumerate(self.tickers)},
            index=self.dates)
        prices.to_csv(self.dataset / "prices.csv", index_label="date")
        event_date = (self.dates[0] - pd.Timedelta(days=4)).date().isoformat()
        members = [{"date": event_date, "ticker": name, "eligible": True}
                   for name in self.tickers]
        pd.DataFrame(members).to_csv(self.dataset / "membership.csv", index=False)
        pd.DataFrame({"date": self.dates, "return": [.006] * len(self.dates)}).to_csv(
            self.dataset / "benchmark.csv", index=False)
        intervals = [{"symbol":name, "valid_from": event_date, "valid_to": "",
                      "index_name": "Fixture Example", "source": "synthetic_unit_test",
                      "source_url":"https://example.org/fake-not-source"} for name in self.tickers]
        digest = hashlib.sha256(json.dumps(intervals, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        (self.dataset/"PIT_MEMBERSHIP_PROVENANCE.json").write_text(json.dumps({
            "index_name": "Fixture Example", "index_id": "unit_test_only",
            "intervals": intervals, "intervals_sha256": digest,
            "source_sha256": hashlib.sha256(b"unit test only").hexdigest(),
            "source_commit": "a"*40,
            "covered_through": self.dates[-1].date().isoformat(),
            "missing_historical_symbols": [],
            "missing_eligible_price_observations": 0,
        }))
        (self.dataset/"BENCHMARK_PROVENANCE.json").write_text(json.dumps({
            "basis": "user_supplied_total_return_index",
            "is_total_return_index": True, "index_name": "Fixture Example",
            "return_convention":"gross_total_return",
            "is_independently_verified": False,
        }))
        (self.dataset/"BENCHMARK_SOURCE.json").write_text(json.dumps({
            "source_sha256":hashlib.sha256(b"mock index levels").hexdigest(),
            "index_name": "Fixture Example", "return_convention":"gross_total_return",
        }))
        pd.DataFrame(columns=[
            "ex_date","ticker","event_type","cash_per_share","share_multiplier",
            "declared_at","source_url","verified"]).to_csv(
            self.dataset/"corporate_actions.csv",index=False)
        (self.dataset/"RETURN_METHODOLOGY.json").write_text(json.dumps({
            "price_basis": "split_bonus_adjusted",
            "dividend_adjustment": "verified dated events where available",
            "validation":"UNVERIFIED market event completeness",
        }))

    def audit(self):
        return historical_readiness.inspect("upload_audit_fixture",
            validation_start=self.config["validation_start"],
            final_test_start=self.config["final_test_start"])

    def checks(self):
        return {x["name"]:x for x in self.audit()["checks"]}

    def test_complete_structural_fixtures_remain_uncertified(self):
        report = self.audit()
        self.assertTrue(report["structural_run_ready"])
        self.assertFalse(report["independent_source_certified"])
        self.assertFalse(report["publication_certified"])
        self.assertEqual(report["timing"]["months_before_validation"],50)
        self.assertEqual(report["timing"]["months_in_final_test"],20)
        categories = {x["name"]:x["status"] for x in report["checks"]}
        self.assertEqual(categories["Point-in-time source reconciliation"],"review")
        self.assertEqual(categories["Corporate-action return parity"],"review")
        self.assertEqual(categories["Total-return benchmark provenance"],"review")
        self.assertEqual(categories["Independent original-source and licensing review"],"blocked")

    def test_pit_intervals_are_checked_against_every_month(self):
        mismatch = self.dataset / "membership.csv"
        frame = pd.read_csv(mismatch)
        frame.loc[len(frame)] = [self.dates[10].date().isoformat(),"ALFA",False]
        frame.to_csv(mismatch,index=False)
        self.assertEqual(self.checks()["Point-in-time source reconciliation"]["status"],"blocked")
        self.assertFalse(self.audit()["publication_certified"])

    def test_pit_hash_tamper_and_unresolved_delisting_are_blocked(self):
        file = self.dataset / "PIT_MEMBERSHIP_PROVENANCE.json"
        doc = json.loads(file.read_text())
        doc["intervals"][0]["valid_to"] = self.dates[6].date().isoformat()
        file.write_text(json.dumps(doc))
        self.assertEqual(self.checks()["Point-in-time source reconciliation"]["status"],"blocked")

    def test_price_only_benchmark_never_passes_tri_review(self):
        path=self.dataset/"BENCHMARK_PROVENANCE.json"
        meta=json.loads(path.read_text())
        meta["is_total_return_index"]=False
        meta["basis"]="price_index_spot_only"
        path.write_text(json.dumps(meta))
        self.assertEqual(self.checks()["Total-return benchmark provenance"]["status"],"blocked")

    def test_missing_dividend_ledger_never_implies_no_events(self):
        (self.dataset/"corporate_actions.csv").unlink()
        result=self.checks()["Corporate-action return parity"]
        self.assertEqual(result["status"],"blocked")
        self.assertIn("ledger",result["detail"])

    def test_historical_test_needs_44_training_and_12_final_months(self):
        self.config["validation_start"]=self.dates[10].date().isoformat()
        report=self.audit()
        self.assertFalse(report["structural_run_ready"])
        self.assertEqual(self.checks()["Chronological frozen test design"]["status"],"blocked")
        with self.assertRaisesRegex(ValueError,"Frozen exploratory evaluation blocked"):
            frozen_study.create("upload_audit_fixture",dict(self.config))

    def test_one_use_protocol_pins_inputs_and_blocks_changed_dataset(self):
        rec=frozen_study.create("upload_audit_fixture",dict(self.config))
        self.assertEqual(rec["state"],"available")
        self.assertFalse(rec["publication_certified"])
        self.assertEqual(frozen_study.read(rec["id"])["sha256"],rec["sha256"])
        path=self.dataset/"prices.csv"
        frame=pd.read_csv(path)
        frame.loc[0,"ALFA"]=202
        frame.to_csv(path,index=False)
        with self.assertRaisesRegex(ValueError,"changed since freezing"):
            frozen_study.execute(rec["id"])
        self.assertEqual(frozen_study.read(rec["id"])["state"],"consumed")
        with self.assertRaisesRegex(ValueError,"already consumed"):
            frozen_study.execute(rec["id"])

    def test_protocol_corruption_is_rejected(self):
        rec=frozen_study.create("upload_audit_fixture",dict(self.config))
        path=frozen_study._path(rec["id"])
        payload=json.loads(path.read_text())
        payload["config"]["top_n"]=2
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,"altered"):
            frozen_study.read(rec["id"])

    def test_successful_one_use_receipt_is_still_not_certification(self):
        rec=frozen_study.create("upload_audit_fixture",dict(self.config))
        run_id="frozen_test_001"
        folder=self.results/run_id
        folder.mkdir()
        manifest={"input_sha256":{k:v for k,v in rec["source_sha256"].items()
                                   if k.endswith(".csv")}, "config":self.config}
        (folder/"research_manifest.json").write_text(json.dumps(manifest))
        with patch.object(service,"execute_run",return_value=run_id) as execute:
            output=frozen_study.execute(rec["id"])
        self.assertEqual(output,run_id)
        execute.assert_called_once()
        receipt=frozen_study.run_receipt(run_id)
        self.assertEqual(receipt["state"],"software_frozen_exploratory")
        self.assertTrue(receipt["source_unchanged_now"])
        self.assertFalse(receipt["independent_holdout_certified"])
        self.assertFalse(receipt["publication_certified"])
        (self.dataset/"benchmark.csv").write_text("date,return\n")
        self.assertEqual(frozen_study.run_receipt(run_id)["state"],"invalidated")

    def test_api_exposes_readiness_and_requires_confirmation(self):
        response=self.client.get("/api/workspace/historical-readiness/upload_audit_fixture",
            params={"validation_start":self.config["validation_start"],
                    "final_test_start":self.config["final_test_start"]})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()["publication_certified"])
        made=self.client.post("/api/workspace/frozen/create",json={
            "dataset_id":"upload_audit_fixture", **self.config})
        self.assertEqual(made.status_code,200,made.text)
        runid=made.json()["id"]
        self.assertEqual(self.client.get("/api/workspace/frozen/"+runid).status_code,200)
        denial=self.client.post("/api/workspace/frozen/"+runid+"/execute",
                                json={"confirm":False})
        self.assertEqual(denial.status_code,400)
        self.assertEqual(frozen_study.read(runid)["state"],"available")

if __name__ == "__main__":
    unittest.main()
