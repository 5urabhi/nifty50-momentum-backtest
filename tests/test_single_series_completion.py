"""Complete historical model inputs with real Dhan-source preservation.

Fixtures are explicitly synthetic. No live provider HTTP calls, network
downloads, order submissions or invented history take place in CI.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import (gbm_calibration, model_data_manager,
                              model_input_selector, shared_market_data,
                              single_series_completion, service)
from workstation_api.app import app


class OneClickModelHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="quantlab_backfill_test_")
        self.root=Path(self.temp.name)
        self.original=self.root/"prepared"
        self.shared=self.root/"shared"
        self.original.mkdir();self.shared.mkdir()
        rng=np.random.default_rng(6282)
        self.original_dates=pd.bdate_range("2024-01-02",periods=225)
        original=100*np.exp(np.cumsum(rng.normal(.0001,.013,225)))
        other=70*np.exp(np.cumsum(rng.normal(.0001,.01,225)))
        other[:45]=np.nan
        pd.DataFrame({"date":self.original_dates,"STOCK":original,
                      "OTHER":other}).to_csv(
            self.original/"daily_prices.csv",index=False)
        self.shared_dates=pd.bdate_range("2023-09-01",periods=355)
        target=100*np.exp(np.cumsum(rng.normal(.0001,.015,355)))
        pd.DataFrame({"date":self.shared_dates,
                      "NSE_EQ_12345":target}).to_csv(
            self.shared/"daily_prices.csv",index=False)
        self.record={"id":"source","kind":"dhan","label":"Synthetic Dhan-formatted fixture",
                     "has_prices":True,"has_daily_prices":True}
        self.shared_record={**self.record,"id":shared_market_data.SHARED_ID}
        self.row={"id":"NSE_EQ:12345","security_id":"12345",
                  "exchange_segment":"NSE_EQ","symbol":"STOCK"}
        def lookup(dataset_id):
            if dataset_id=="source":return self.original,self.record
            if dataset_id==shared_market_data.SHARED_ID:
                return self.shared,self.shared_record
            raise ValueError("Dataset is unavailable")
        self.source_patch=patch.object(service,"dataset_path",side_effect=lookup)
        self.map_patch=patch.object(model_data_manager,"_mapping",
                 return_value=([self.row],None))
        self.spans_patch=patch.object(shared_market_data,"cached_spans",
                 return_value=[])
        for p in (self.source_patch,self.map_patch,self.spans_patch):p.start()
        self.client=TestClient(app,base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        for p in (self.spans_patch,self.map_patch,self.source_patch):p.stop()
        self.temp.cleanup()

    def plan(self,model="heston_proxy",ticker="STOCK",dataset="source"):
        return model_data_manager.inspect(
            model,dataset,{"target":"stock","ticker":ticker})

    def test_screenshot_heston_225_dates_means_224_returns_not_zero(self):
        selected=self.plan()
        self.assertEqual(selected["available_price_dates"],225)
        self.assertEqual(selected["common_returns"],224)
        self.assertEqual(selected["min_returns"],252)
        self.assertEqual(selected["target_returns"],303)
        self.assertEqual(selected["missing_minimum"],28)
        self.assertEqual(selected["missing_to_target"],79)
        self.assertTrue(selected["can_download"])
        self.assertEqual(selected["selected_assets"],["STOCK"])
        self.assertEqual(selected["shared_ticker"],"NSE_EQ_12345")
        self.assertGreaterEqual(selected["estimated_vendor_daily_requests"],1)
        self.assertLessEqual(
            date.fromisoformat(selected["suggested_end_exclusive"]),
            date.today()+timedelta(days=1))

        missing=self.plan(ticker="")
        self.assertEqual(missing["status"],"select_ticker")
        self.assertIsNone(missing["common_returns"])
        self.assertIsNone(missing["missing_to_target"])
        self.assertIn("225 source price dates",missing["message"])
        self.assertEqual(missing["suggested_ticker"],"STOCK")
        self.assertFalse(missing["can_download"])

    def test_get_model_inputs_shows_incomplete_but_extendable_tickers(self):
        response=self.client.get("/api/lab/model-inputs",params={
            "dataset_id":"source","model_id":"heston_proxy"})
        self.assertEqual(response.status_code,200,response.text)
        obj=response.json()
        self.assertEqual(obj["eligible_count"],0)
        self.assertEqual(obj["recommended_ticker"],"STOCK")
        self.assertGreaterEqual(obj["extendable_count"],1)
        candidate=obj["candidates"][0]
        self.assertEqual(candidate["returns"],224)
        self.assertEqual(candidate["missing_to_target"],79)
        self.assertTrue(candidate["extendable"])

    def test_readonly_api_requires_explicit_click_before_any_download(self):
        body={"model_id":"heston_proxy","dataset_id":"source",
              "params":{"target":"stock","ticker":"STOCK"},"confirm_download":False}
        denied=self.client.post("/api/lab/data-requirements/extend",json=body)
        self.assertEqual(denied.status_code,400)
        with patch("workstation_api.app._spawn",return_value={
            "job_id":"test-backfill","status":"queued"}) as spawn:
            accepted=self.client.post("/api/lab/data-requirements/extend",
                                     json={**body,"confirm_download":True})
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(accepted.json()["status"],"queued")
        self.assertEqual(accepted.json()["planned"]["target_returns"],303)
        self.assertEqual(spawn.call_args.args[0],"lab_shared_data_extension")

    def test_existing_cache_satisfies_buffer_without_provider_connection(self):
        p={"target":"stock","ticker":"STOCK"}
        called=[]
        def progress(percent,stage):
            called.append((percent,stage))
        with patch.object(shared_market_data,"reuse_cached",
                          return_value={"rows_appended":35}) as cached:
            with patch("workstation_api.dhan_workspace._fetch_history",
                       side_effect=AssertionError("No Dhan call permitted")):
                with patch("workstation_api.dhan_auth.check_profile",
                           side_effect=AssertionError("No token needed for complete cache")):
                    result=model_data_manager.execute(
                        "heston_proxy","source",p,progress=progress)
        self.assertTrue(cached.called)
        self.assertEqual(result["status"],"ready")
        self.assertTrue(result["buffer_complete"])
        self.assertEqual(result["selected_ticker"],"NSE_EQ_12345")
        self.assertEqual(result["original_ticker"],"STOCK")
        self.assertEqual(result["dataset_id"],shared_market_data.SHARED_ID)
        self.assertGreaterEqual(result["actual_returns"],303)
        self.assertEqual(result["missing_to_target"],0)
        self.assertEqual(called[-1][0],100)

    def test_provider_cannot_supply_more_sessions_does_not_claim_ready(self):
        limited=self.shared_dates[:225]
        fewer=90*np.exp(np.cumsum(np.random.default_rng(333).normal(.0001,.018,225)))
        pd.DataFrame({"date":limited,"NSE_EQ_12345":fewer}).to_csv(
            self.shared/"daily_prices.csv",index=False)
        stages=[]
        with patch.object(shared_market_data,"reuse_cached",
                          return_value={"rows_appended":0}):
            with patch("workstation_api.dhan_auth.check_profile",
                       return_value={"ok":True}):
                with patch("workstation_api.dhan_workspace._fetch_history",
                           return_value={"rows_added":0}) as fetch:
                    response=single_series_completion.execute(
                        "heston_proxy","source",
                        {"target":"stock","ticker":"STOCK"},
                        progress=lambda percent,description:stages.append((percent,description)))
        self.assertGreaterEqual(fetch.call_count,1)
        self.assertFalse(response["buffer_complete"])
        self.assertEqual(response["status"],"incomplete")
        self.assertGreater(response["missing_to_target"],0)
        self.assertIn("additional valid observations",response["message"])
        self.assertGreater(len(stages),2)

    def test_no_shared_dataset_yet_does_not_fail_before_first_vendor_capture(self):
        with patch.object(shared_market_data,"reuse_cached",
                          return_value={"rows_appended":0}):
            with patch.object(service,"dataset_path",side_effect=lambda dataset_id:
                (self.original,self.record) if dataset_id=="source" else
                (_ for _ in ()).throw(ValueError("Dataset unavailable"))):
                with patch("workstation_api.dhan_auth.check_profile",
                           return_value={"ok":True}):
                    with patch("workstation_api.dhan_workspace._fetch_history",
                               return_value={"rows_added":0}) as fetch:
                        result=single_series_completion.execute(
                            "heston_proxy","source",
                            {"target":"stock","ticker":"STOCK"})
                        self.assertGreater(fetch.call_count,0)
                        self.assertEqual(result["status"],"incomplete")
                        self.assertFalse(result["buffer_complete"])

    def test_shared_wide_panel_trim_edges_never_fills_internal_gaps(self):
        data=pd.read_csv(self.shared/"daily_prices.csv")
        data.loc[:20,"NSE_EQ_12345"]=np.nan
        data.loc[341:,"NSE_EQ_12345"]=np.nan
        data.to_csv(self.shared/"daily_prices.csv",index=False)
        _,returns,info=gbm_calibration._series(
            shared_market_data.SHARED_ID,"stock","NSE_EQ_12345")
        self.assertEqual(len(returns),319)
        self.assertEqual(info["observations"],319)
        selected=model_input_selector.inspect(
            shared_market_data.SHARED_ID,"heston_proxy")
        self.assertTrue(selected["candidates"][0]["runnable"])
        data.loc[75,"NSE_EQ_12345"]=np.nan
        data.to_csv(self.shared/"daily_prices.csv",index=False)
        with self.assertRaisesRegex(ValueError,"internal missing"):
            gbm_calibration._series(
                shared_market_data.SHARED_ID,"stock","NSE_EQ_12345")
        broken=model_input_selector.inspect(
            shared_market_data.SHARED_ID,"heston_proxy")
        self.assertFalse(broken["candidates"][0]["runnable"])
        self.assertFalse(broken["candidates"][0]["extendable"])

    def test_non_dhan_dataset_cannot_be_auto_extended(self):
        rec={**self.record,"kind":"upload"}
        with patch.object(service,"dataset_path",return_value=(self.original,rec)):
            plan=self.plan()
        self.assertFalse(plan["can_download"])
        self.assertIn("Dhan dataset",plan["download_explanation"])


if __name__=="__main__":
    unittest.main()
