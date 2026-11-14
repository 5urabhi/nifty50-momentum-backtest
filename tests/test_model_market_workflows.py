"""Source-bound optional market paths and observed stochastic fits.

All numerical fixtures in this suite are artificial, explicitly NOT Dhan or
NSE prices. Assert no automatic market quote fabrication or future fitting.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import (model_lab, model_registry, model_readiness,
                              option_quotes, dhan_option_chain, service)
from workstation_api.app import app


class CompleteModelWorkflowsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="quantlab_market_models_")
        self.folder=Path(self.tmp.name)
        rng=np.random.default_rng(123456)
        dates=pd.bdate_range("2024-01-02",periods=500)
        stochastic_vol=np.empty(len(dates));stochastic_vol[0]=.011
        for i in range(1,len(dates)):
            stochastic_vol[i]=float(np.clip(
                .93*stochastic_vol[i-1]+.07*.013+rng.normal(0,.00035),
                .004,.04))
        shocks=rng.normal(0,1,len(dates))*stochastic_vol
        shocks[105]+=.09;shocks[176]-=.095;shocks[297]+=.11;shocks[327]-=.085
        levels=120*np.exp(np.cumsum(shocks))
        other=90*np.exp(np.cumsum(rng.normal(0,.012,len(dates))))
        pd.DataFrame({"date":dates,"STOCK":levels,"OTHER":other}).to_csv(
            self.folder/"daily_prices.csv",index=False)
        monthly_dates=pd.date_range("2022-01-31",periods=48,freq="ME")
        monthly=rng.normal(.011,.031,len(monthly_dates))
        pd.DataFrame({"date":monthly_dates,"return":monthly}).to_csv(
            self.folder/"benchmark.csv",index=False)
        (self.folder/"BENCHMARK_SOURCE.json").write_text(json.dumps({
            "index_name":"NIFTY 50","return_convention":"gross_total_return",
            "source_sha256":"b"*64}))
        self.record={"id":"market_fixture","kind":"synthetic",
            "label":"SYNTHETIC MARKET RESEARCH FIXTURE",
            "has_prices":True,"has_daily_prices":True,"basis":"No real market evidence"}
        self.data_patch=patch.object(service,"dataset_path",return_value=(self.folder,self.record))
        self.raw_patch=patch.object(service,"DATA",self.folder/"data")
        self.runs_patch=patch.object(service,"RESULTS",self.folder/"results"/"workstation_runs")
        for p in (self.data_patch,self.raw_patch,self.runs_patch):p.start()
        self.client=TestClient(app,base_url="http://127.0.0.1:8765")
        stamp=datetime.now(timezone.utc).replace(microsecond=0)-timedelta(days=1)
        expiration=stamp+timedelta(days=41)
        self.quote_csv=("captured_at,provider,underlying,underlying_spot,expiry_at,strike,option_type,bid,ask\n"
            +f"{stamp.isoformat()},TEST_PROVIDER,STOCK,120,{expiration.isoformat()},120,call,3.4,3.8\n").encode()

    def tearDown(self):
        self.client.close()
        for p in (self.runs_patch,self.raw_patch,self.data_patch):p.stop()
        self.tmp.cleanup()

    def _run(self,name,params=None):
        return self.client.post("/api/lab/run",json={
            "model_id":name,"dataset_id":"market_fixture","params":params or {}})

    def test_existing_simulations_and_theory_still_work_without_market_files(self):
        for name in ("gbm","ou","merton","heston","black_scholes",
                     "implied_vol","binomial","mc_option","option_surface"):
            params={"paths":40,"steps":24} if name in {"gbm","ou","merton","heston"} else {}
            response=self.client.post("/api/lab/run",json={
                "model_id":name,"dataset_id":None,"params":params})
            self.assertEqual(response.status_code,200,(name,response.text[:400]))
            self.assertIn(response.json()["mode"],{"synthetic","theoretical"})

    def test_observed_merton_fit_and_strict_holdout(self):
        p={"target":"stock","ticker":"STOCK","paths":40,"steps":48}
        first=self._run("merton_fit",p)
        self.assertEqual(first.status_code,200,first.text)
        a=first.json()
        self.assertEqual(a["mode"],"historical")
        self.assertEqual(a["source"]["source_file"],"daily_prices.csv")
        self.assertEqual(a["calibration"]["train_count"],399)
        self.assertEqual(a["calibration"]["test_count"],100)
        self.assertFalse(a["calibration"]["test_used_in_fit"])
        self.assertIn("SYNTHETIC FIXTURE"," ".join(a["limitations"]))
        self.assertEqual(len(a["plots"]),2)
        original=pd.read_csv(self.folder/"daily_prices.csv")
        changed=original.copy()
        changed.loc[470:,"STOCK"]=changed.loc[470:,"STOCK"]*1.2
        changed.to_csv(self.folder/"daily_prices.csv",index=False)
        new=self._run("merton_fit",p)
        self.assertEqual(new.status_code,200,new.text)
        b=new.json()
        self.assertEqual(a["calibration"]["mu"],b["calibration"]["mu"])
        self.assertEqual(a["calibration"]["lambda"],b["calibration"]["lambda"])

    def test_ou_uses_log_realized_volatility_not_stock_price_fit(self):
        params={"target":"stock","ticker":"STOCK","paths":40,"steps":50}
        response=self._run("ou_fit",params)
        self.assertEqual(response.status_code,200,response.text)
        d=response.json()
        self.assertIn("log(20_session_realized_volatility)",d["source"]["source_transform"])
        self.assertGreater(d["calibration"]["kappa"],0)
        self.assertFalse(d["calibration"]["test_used_in_fit"])
        self.assertTrue(any("NOT" in x for x in d["notes"]))

    def test_heston_is_honestly_a_proxy_not_options_calibrated(self):
        response=self._run("heston_proxy",{
            "target":"stock","ticker":"STOCK","paths":25,"steps":30})
        self.assertEqual(response.status_code,200,response.text)
        d=response.json()
        self.assertEqual(d["mode"],"historical")
        self.assertFalse(d["calibration"]["risk_neutral_option_calibration"])
        self.assertEqual(d["evidence_type"],
                         "historical_realized_variance_proxy_not_heston_option_calibration")
        self.assertTrue(any("CANNOT" in x for x in d["limitations"]))
        self.assertFalse(d["calibration"]["test_used_in_fit"])

    def test_source_specific_stochastic_readiness(self):
        for name,min_count in (("merton_fit",120),("ou_fit",90),("heston_proxy",252)):
            result=self.client.get("/api/lab/data-requirements",params={
                "model_id":name,"dataset_id":"market_fixture",
                "target":"stock","ticker":"STOCK"})
            self.assertEqual(result.status_code,200,result.text)
            d=result.json()
            self.assertTrue(d["runnable"],name+" "+d["message"])
            self.assertEqual(d["min_returns"],min_count)
            self.assertEqual(d["assets_requested"],1)
        missing=self.client.get("/api/lab/data-requirements",params={
            "model_id":"ou_fit","dataset_id":"market_fixture",
            "target":"stock","ticker":"MISSING"})
        self.assertEqual(missing.status_code,200)
        self.assertFalse(missing.json()["runnable"])

    def test_option_quote_import_and_five_real_quote_calculations(self):
        response=self.client.post("/api/lab/option-quotes/import",
            data={"dataset_id":"market_fixture","confirm_original_quote":"true"},
            files={"file":("option_export.csv",self.quote_csv,"text/csv")})
        self.assertEqual(response.status_code,200,response.text)
        quote_id=response.json()["id"]
        snapshot=self.client.get("/api/lab/option-quotes",params={"dataset_id":"market_fixture"})
        self.assertEqual(snapshot.status_code,200,snapshot.text)
        self.assertEqual(len(snapshot.json()["snapshots"]),1)
        quote_ref=quote_id+":0"
        for name in ("black_scholes_quote","binomial_quote","implied_vol_quote",
                     "mc_option_quote","option_surface_quote"):
            response=self._run(name,{"quote":quote_ref})
            self.assertEqual(response.status_code,200,(name,response.text[:450]))
            d=response.json()
            self.assertEqual(d["mode"],"market")
            self.assertEqual(d["source"]["option_quote_id"],quote_id)
            self.assertEqual(d["source_sha256"],response.json()["calibration"]["market_source_sha256"])
            self.assertTrue(d["source"]["market_quote_observed"])
            self.assertFalse(d["calibration"]["historical_oos_validation"])
            self.assertTrue(any("ASSUMPTIONS" in x for x in d["limitations"]))
            self.assertGreater(len(d["plots"]),0)
            self.assertTrue((self.folder/"results"/"model_laboratory"/(d["run_id"]+".json")).is_file())

    def test_model_matrix_separates_math_historical_sources_and_quotes(self):
        before=model_readiness.overview("market_fixture")
        self.assertGreaterEqual(before["math_ready"],9)
        self.assertGreaterEqual(before["historical_source_ready"],3)
        self.assertEqual(before["option_source_ready"],0)
        self.assertEqual(before["total_models"],len(model_registry.MODELS))
        self.assertTrue(before["not_a_market_performance_certification"])
        imported=option_quotes.import_quotes("market_fixture",self.quote_csv)
        after=self.client.get("/api/lab/model-readiness",params={
            "dataset_id":"market_fixture"})
        self.assertEqual(after.status_code,200,after.text)
        data=after.json()
        self.assertEqual(data["option_source_ready"],5)
        self.assertEqual(data["available_original_option_contracts"],1)
        self.assertEqual(data["total_models"],len(model_registry.MODELS))
        models={m["id"]:m for m in data["models"]}
        self.assertEqual(models["heston"]["status"],"math_ready")
        self.assertEqual(models["heston_proxy"]["status"],"source_available")
        self.assertTrue(models["implied_vol_quote"]["source_ready"])
        self.assertFalse(models["implied_vol"]["source_ready"])

    def test_market_readiness_requires_exact_saved_quote(self):
        empty=self.client.get("/api/lab/data-requirements",params={
            "model_id":"implied_vol_quote","dataset_id":"market_fixture"})
        self.assertEqual(empty.status_code,200,empty.text)
        self.assertFalse(empty.json()["runnable"])
        self.assertIn("option quote",empty.json()["message"])
        imported=option_quotes.import_quotes("market_fixture",self.quote_csv)
        available=self.client.get("/api/lab/data-requirements",params={
            "model_id":"implied_vol_quote","dataset_id":"market_fixture",
            "quote":imported["id"]+":0"})
        self.assertEqual(available.status_code,200,available.text)
        self.assertTrue(available.json()["runnable"])
        refused=self._run("implied_vol_quote",{"quote":""})
        self.assertEqual(refused.status_code,400)

    def test_live_dhan_chain_mock_is_readonly_and_preserves_provider_json(self):
        expiry=(datetime.now(timezone.utc)+timedelta(days=35)).date().isoformat()
        chain={"status":"success","data":{"last_price":25000.0,"oc":{
            "25000.000000":{
                "ce":{"top_bid_price":198.0,"top_ask_price":200.0},
                "pe":{"top_bid_price":195.0,"top_ask_price":202.0}},
            "25050.000000":{
                "ce":{"top_bid_price":182.0,"top_ask_price":186.0},
                "pe":{"top_bid_price":213.0,"top_ask_price":220.0}},
        }}}
        provider=json.dumps(chain).encode()
        calls=[]
        def fake(path,**kwargs):
            calls.append((path,kwargs.get("body")))
            if path==dhan_option_chain.EXPIRY_ENDPOINT:
                return {"status":"success","data":[expiry]},b"original expiry list"
            if path==dhan_option_chain.CHAIN_ENDPOINT:
                return chain,provider
            raise AssertionError("No other Dhan endpoint must be called")
        with patch.dict("os.environ",{"DHAN_ACCESS_TOKEN":"synthetic-token",
                                      "DHAN_CLIENT_ID":"123456789"}):
            with patch.object(dhan_option_chain,"_json_http",side_effect=fake):
                receipt=dhan_option_chain.capture(
                    "market_fixture","NIFTY50",sleep=lambda _:None)
        self.assertEqual(receipt["contracts"],4)
        self.assertTrue(receipt["market_data_not_orders"])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][0],dhan_option_chain.EXPIRY_ENDPOINT)
        self.assertEqual(calls[1][0],dhan_option_chain.CHAIN_ENDPOINT)
        self.assertEqual(calls[1][1]["UnderlyingScrip"],13)
        self.assertEqual(calls[1][1]["UnderlyingSeg"],"IDX_I")
        self.assertEqual(calls[1][1]["Expiry"],expiry)
        quotes=option_quotes.get(receipt["id"],"market_fixture")
        self.assertEqual(quotes["source_type"],"dhan_readonly_optionchain_api_v2")
        self.assertFalse(quotes["provider_metadata"]["source_expiry_time_is_exact"])
        original=self.folder/"data"/"model_option_quotes"/(receipt["id"]+".vendor.json")
        self.assertEqual(original.read_bytes(),provider)
        self.assertEqual(len(quotes["contracts"]),4)
        self.assertEqual(quotes["contracts"][0]["underlying"],"NIFTY50")
        self.assertTrue(quotes["contracts"][0]["expiry_at"].endswith("+00:00"))

    def test_dhan_live_quote_requires_explicit_confirmation_and_local_token(self):
        payload={"dataset_id":"market_fixture","underlying":"NIFTY50",
                 "confirm_readonly":False}
        bad=self.client.post("/api/lab/option-quotes/dhan",json=payload)
        self.assertEqual(bad.status_code,400)
        self.assertIn("read-only",bad.text)
        with patch.dict("os.environ",{"DHAN_ACCESS_TOKEN":""}):
            denied=self.client.post("/api/lab/option-quotes/dhan",
                                    json={**payload,"confirm_readonly":True})
        self.assertEqual(denied.status_code,400)
        self.assertIn("DHAN_ACCESS_TOKEN",denied.text)
        with patch.dict("os.environ",{"DHAN_ACCESS_TOKEN":"synthetic-test"}):
            with patch("workstation_api.app._spawn",return_value={
                    "job_id":"test_queued","status":"queued"}) as spawn:
                authorized=self.client.post("/api/lab/option-quotes/dhan",
                                            json={**payload,"confirm_readonly":True})
        self.assertEqual(authorized.status_code,200,authorized.text)
        self.assertEqual(authorized.json()["status"],"queued")
        self.assertEqual(spawn.call_args.args[0],"lab_dhan_optionchain")

    def test_rejects_crossed_nonfinite_and_unauthorized_source(self):
        imported=option_quotes.import_quotes("market_fixture",self.quote_csv)
        quote_ref=imported["id"]+":0"
        raw,_=option_quotes._entry_path(imported["id"])
        raw.write_bytes(self.quote_csv.replace(b"3.4,3.8",b"9.0,3.8"))
        response=self._run("implied_vol_quote",{"quote":quote_ref})
        self.assertEqual(response.status_code,400)
        self.assertIn("integrity",response.text.lower())
        response=self.client.post("/api/lab/option-quotes/import",
            data={"dataset_id":"market_fixture","confirm_original_quote":"false"},
            files={"file":("invalid.csv",self.quote_csv,"text/csv")})
        self.assertEqual(response.status_code,400)
        for bad in (self.quote_csv.replace(b"3.4,3.8",b"9.0,3.8"),
                    self.quote_csv.replace(b"TEST_PROVIDER",b""),
                    self.quote_csv.replace(b"STOCK,120",b"INVALID,0")):
            with self.assertRaises(ValueError):
                option_quotes.import_quotes("market_fixture",bad)

    def test_extreme_premium_no_arbitrage_rejected_and_preserves_source(self):
        # Make a valid CSV but economically impossible European option quote;
        # importer may retain raw source, model must fail instead of inventing IV.
        bad=self.quote_csv.replace(b"3.4,3.8",b"140.0,145.0")
        imported=option_quotes.import_quotes("market_fixture",bad)
        response=self._run("implied_vol_quote",{"quote":imported["id"]+":0"})
        self.assertEqual(response.status_code,400)
        self.assertIn("no-arbitrage",response.text)

if __name__=="__main__":
    unittest.main()
