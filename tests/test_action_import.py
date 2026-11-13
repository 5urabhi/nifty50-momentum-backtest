"""Read-only broker source + non-destructive corporate-event adjustment tests.

All numerical files in these tests are invented fixtures; never market data.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import corporate_action_import, service
from workstation_api.app import app


class ActionImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="quantlab_action_versions_")
        self.root=Path(self.temp.name)
        self.path=self.root/"data"/"workstation_imports"/"action_fixture"
        self.path.mkdir(parents=True)
        self.data_patch=patch.object(service,"DATA",self.root/"data")
        self.data_patch.start()
        self.client=TestClient(app,base_url="http://127.0.0.1:8765")
        self.days=pd.bdate_range("2024-01-02","2024-04-30")
        t=np.arange(len(self.days))
        closes=pd.DataFrame({"ALFA":100+.1*t, "BETA":70+.15*t},
            index=self.days)
        closes.index.name="date"
        closes.to_csv(self.path/"daily_prices.csv")
        marks=pd.DatetimeIndex(pd.Series(self.days,index=self.days)
            .groupby(self.days.to_period("M")).max().to_list(),name="date")
        closes.loc[marks].to_csv(self.path/"prices.csv")
        self.ledger=pd.DataFrame([{
            "ex_date":self.days[35].date().isoformat(), "ticker":"ALFA",
            "event_type":"dividend","cash_per_share":2.0,
            "share_multiplier":1.0,
            "declared_at":self.days[30].date().isoformat(),
            "source_url":"https://example.org/invented-fixture",
            "verified":True,
        }])
        self.original=(self.path/"prices.csv").read_bytes()
        (self.path/"EVIDENCE_REVIEW.json").write_text(json.dumps({"old_review":"does not apply to new actions"}))

    def tearDown(self):
        self.client.close()
        self.data_patch.stop()
        self.temp.cleanup()

    def payload(self,rows=None):
        return (self.ledger if rows is None else rows).to_csv(index=False).encode()

    def test_new_total_return_view_keeps_parent_immutable(self):
        out=corporate_action_import.import_adjusted(
            "upload_action_fixture",self.payload())
        self.assertFalse(out["independent_source_certified"])
        self.assertEqual(out["parent_dataset_id"],"upload_action_fixture")
        self.assertEqual(out["corporate_action_rows"],1)
        self.assertEqual((self.path/"prices.csv").read_bytes(),self.original)
        derived=self.root/"data"/"workstation_imports"/out["dataset_id"].removeprefix("upload_")
        values=pd.read_csv(derived/"prices.csv")
        self.assertEqual(len(values),4)
        raw=pd.read_csv(self.path/"prices.csv")
        self.assertGreater(values["ALFA"].iloc[-1]/values["ALFA"].iloc[0],
                           raw["ALFA"].iloc[-1]/raw["ALFA"].iloc[0])
        policy=json.loads((derived/"RETURN_METHODOLOGY.json").read_text())
        self.assertEqual(policy["price_basis"],"split_bonus_adjusted")
        self.assertFalse(policy["event_completeness_reviewed_independently"])
        self.assertTrue((derived/"daily_prices.csv").is_file())
        self.assertFalse((derived/"EVIDENCE_REVIEW.json").exists(),
                         "New economic data version must require fresh independent review")

    def test_api_can_create_new_provisional_view(self):
        response=self.client.post("/api/datasets/upload_action_fixture/add-actions",
            data={"price_basis":"split_bonus_adjusted","acknowledge_unverified":"true"},
            files={"file":("real-actions.csv",self.payload(),"text/csv")})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()["dataset_id"].startswith("upload_actions_"))
        self.assertFalse(response.json()["independent_source_certified"])

    def test_opt_in_required(self):
        response=self.client.post("/api/datasets/upload_action_fixture/add-actions",
            data={"price_basis":"split_bonus_adjusted","acknowledge_unverified":"false"},
            files={"file":("actions.csv",self.payload(),"text/csv")})
        self.assertEqual(response.status_code,400)

    def test_unverified_or_unsupported_events_fail_closed(self):
        unverified=self.ledger.copy()
        unverified["verified"]=False
        with self.assertRaisesRegex(ValueError,"unverified"):
            corporate_action_import.import_adjusted("upload_action_fixture",
                self.payload(unverified))
        unsupported=self.ledger.copy()
        unsupported["event_type"]="spin_off"
        with self.assertRaisesRegex(ValueError,"invalid"):
            corporate_action_import.import_adjusted("upload_action_fixture",
                self.payload(unsupported))
        with self.assertRaisesRegex(ValueError,"security identities"):
            outside=self.ledger.copy()
            outside["ticker"]="UNKNOWN"
            corporate_action_import.import_adjusted("upload_action_fixture",
                self.payload(outside))

    def test_missing_interior_daily_security_prices_block_conversion(self):
        daily=self.path/"daily_prices.csv"
        frame=pd.read_csv(daily)
        frame.loc[11,"BETA"]=np.nan
        frame.to_csv(daily,index=False)
        with self.assertRaisesRegex(ValueError,"Interior missing daily"):
            corporate_action_import.import_adjusted(
                "upload_action_fixture",self.payload())

    def test_raw_mode_rejected_when_dhan_adjusted_policy_known(self):
        (self.path/"DAILY_AGGREGATION_PROVENANCE.json").write_text(
            json.dumps({"source":"Dhan","source_interval_minutes":1}))
        with self.assertRaisesRegex(ValueError,"already split/bonus adjusted"):
            corporate_action_import.import_adjusted(
                "upload_action_fixture",self.payload(),
                price_basis="raw_unadjusted")

    def test_partial_calendar_months_block(self):
        source=self.path/"daily_prices.csv"
        daily=pd.read_csv(source)
        daily=daily.loc[daily["date"].str.startswith("2024-01")].iloc[-5:]
        daily.to_csv(source,index=False)
        with self.assertRaisesRegex(ValueError,"Original monthly trading sessions|Fewer than eight"):
            corporate_action_import.import_adjusted(
                "upload_action_fixture",self.payload())


if __name__ == "__main__":
    unittest.main()
