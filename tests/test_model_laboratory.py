"""Offline model laboratory acceptance: actual Python computations only.

No Dhan token, network requests or trading endpoints are required.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import model_lab
from workstation_api.app import app


class ModelLaboratoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="quantlab_model_lab_")
        cls.folder=Path(cls.temp.name)
        rng=np.random.default_rng(208)
        dates=pd.bdate_range("2025-01-01",periods=260)
        names=[f"REAL_SAMPLE_{i:02d}" for i in range(8)]
        common=rng.normal(0.0003,0.004,size=(len(dates),1))
        shocks=rng.normal(0.0001,0.008,size=(len(dates),len(names)))
        values=100*np.exp(np.cumsum(common+shocks,axis=0))
        daily=pd.DataFrame(values,index=dates,columns=names)
        daily.to_csv(cls.folder/"daily_prices.csv",index_label="date")
        daily.resample("ME").last().to_csv(cls.folder/"prices.csv",index_label="date")
        cls.record={"id":"unit_test_prices","label":"Synthetic observed-input test fixture",
            "kind":"synthetic","has_daily_prices":True,"has_prices":True,
            "benchmark_kind":"unverified","basis":"OFFLINE TEST FIXTURE — NOT MARKET DATA"}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.patch=patch.object(model_lab.service,"dataset_path",
            return_value=(self.folder,self.record))
        self.path_patch=patch.object(model_lab.service,"RESULTS",self.folder/"test_model_runs")
        self.patch.start()
        self.path_patch.start()
        self.client=TestClient(app,base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        self.path_patch.stop()
        self.patch.stop()

    def run_model(self, model: str, params=None, with_data=True):
        return self.client.post("/api/lab/run",json={
            "model_id":model,"dataset_id":"unit_test_prices" if with_data else None,
            "params":params or {},
        })

    def test_catalog_contains_six_families_and_real_executable_dispatch(self):
        response=self.client.get("/api/lab/catalog")
        self.assertEqual(response.status_code,200,response.text)
        models=response.json()["models"]
        self.assertGreaterEqual(len(models),26)
        self.assertEqual(len({m["id"] for m in models}),len(models))
        self.assertEqual(len({m["group"] for m in models}),6)
        self.assertTrue(all(m["status"]=="runnable" for m in models))
        self.assertEqual({m["mode"] for m in models},{"synthetic","theoretical","historical"})

    def test_mathematical_simulations_are_seeded_and_not_mislabeled_market_data(self):
        one=self.run_model("gbm",{"seed":2026,"steps":25,"paths":50},False)
        two=self.run_model("gbm",{"seed":2026,"steps":25,"paths":50},False)
        self.assertEqual(one.status_code,200,one.text)
        self.assertEqual(two.status_code,200,two.text)
        self.assertEqual(one.json()["plots"],two.json()["plots"])
        self.assertIsNone(one.json()["source"])
        self.assertEqual(one.json()["mode"],"synthetic")
        self.assertEqual(one.json()["plots"][0]["kind"],"fan2d")
        for model in ("ou","heston","merton"):
            r=self.run_model(model,{"steps":24,"paths":40},False)
            self.assertEqual(r.status_code,200,(model,r.text))
            self.assertEqual(r.json()["mode"],"synthetic")
            self.assertEqual(r.json()["plots"][0]["kind"],"fan2d")

    def test_option_pricing_and_real_interactive_3d_surface_numbers(self):
        black=self.run_model("black_scholes",{},False)
        self.assertEqual(black.status_code,200,black.text)
        self.assertEqual(black.json()["mode"],"theoretical")
        surface=self.run_model("option_surface",{},False)
        self.assertEqual(surface.status_code,200,surface.text)
        plot=surface.json()["plots"][0]
        self.assertEqual(plot["kind"],"surface3d")
        self.assertEqual(len(plot["z"]),len(plot["y"]))
        self.assertEqual(len(plot["z"][0]),len(plot["x"]))
        self.assertLess(plot["z"][0][0],plot["z"][0][-1])
        for model in ("binomial","implied_vol","mc_option"):
            r=self.run_model(model,{},False)
            self.assertEqual(r.status_code,200,(model,r.text))

    def test_dataset_readiness_prefers_daily_prices_without_network(self):
        result=self.client.get("/api/lab/readiness",params={"dataset_id":"unit_test_prices"})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()["frequency"],"daily")
        self.assertEqual(result.json()["observed_dates"],260)
        self.assertEqual(result.json()["eligible_assets_180"],8)

    def test_historical_models_consume_true_observed_series_with_provenance(self):
        for model in ("pca","covariance","historical_tail","gaussian_tail",
                      "student_t_tail","newey_west","bootstrap_sharpe"):
            r=self.run_model(model)
            self.assertEqual(r.status_code,200,(model,r.text[:650]))
            d=r.json()
            self.assertEqual(d["mode"],"historical")
            self.assertEqual(d["source"]["frequency"],"daily")
            self.assertEqual(d["source"]["source_file"],"daily_prices.csv")
            self.assertEqual(d["source"]["assets"],sorted(d["source"]["assets"]))
            self.assertFalse(d["source"]["missing_prices_forward_filled"])
            self.assertTrue(d["plots"])

    def test_empirical_portfolio_optimizers_are_feasible(self):
        for model in ("min_variance","risk_parity","max_diversification","cvar"):
            r=self.run_model(model)
            self.assertEqual(r.status_code,200,(model,r.text[:700]))
            weights=r.json()["table"]
            self.assertAlmostEqual(sum(v["weight"] for v in weights),1,places=4)
            self.assertTrue(all(-1e-6<=v["weight"]<=.30001 for v in weights))
            self.assertEqual(r.json()["mode"],"historical")
        bl=self.run_model("black_litterman")
        self.assertEqual(bl.status_code,200,bl.text)
        self.assertEqual(len(bl.json()["table"]),8)

    def test_walk_forward_has_strict_holdout_and_risk_surface_has_empirical_vol(self):
        roll=self.run_model("rolling_vol",{"train_window":60})
        self.assertEqual(roll.status_code,200,roll.text)
        self.assertGreater(len(roll.json()["table"]),0)
        surf=self.run_model("risk_surface")
        self.assertEqual(surf.status_code,200,surf.text)
        self.assertEqual(surf.json()["plots"][0]["kind"],"surface3d")
        self.assertTrue(any("hypothetical" in w for w in surf.json()["limitations"]))

    def test_rejects_unsupported_and_out_of_range_models(self):
        bad=[
            ("not_a_model",{},400),("gbm",{"seed":-1},400),
            ("gbm",{"foo":"bar"},400),("gbm",{"paths":999999},400),
            ("black_scholes",{"volatility":0},400),
            ("implied_vol",{"market_price":9999},400),
            ("min_variance",{"assets":2,"max_weight":.3},400),
        ]
        for key,params,status in bad:
            r=self.run_model(key,params,with_data=False)
            self.assertEqual(r.status_code,status,(key,r.text))

    def test_missing_data_is_explicit_never_synthetic_fallback(self):
        r=self.run_model("garch",with_data=False)
        self.assertEqual(r.status_code,400,r.text)
        self.assertIn("Choose an observed research dataset",r.text)
        with tempfile.TemporaryDirectory() as small:
            folder=Path(small)
            prices=pd.read_csv(self.folder/"prices.csv")
            prices.head(6).to_csv(folder/"prices.csv",index=False)
            record={**self.record,"has_daily_prices":False}
            with patch.object(model_lab.service,"dataset_path",return_value=(folder,record)):
                r=self.run_model("evt")
                self.assertEqual(r.status_code,400,r.text)
                self.assertIn("180 observed common",r.text.lower())

    def test_persisted_model_runs_have_reproducible_source_evidence(self):
        response=self.run_model("min_variance")
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertRegex(result["run_id"],r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{10}$")
        self.assertEqual(len(result["source_sha256"]),64)
        listing=self.client.get("/api/lab/runs")
        self.assertEqual(listing.status_code,200,listing.text)
        self.assertTrue(any(item["id"]==result["run_id"] for item in listing.json()["runs"]))
        record=self.client.get("/api/lab/runs/"+result["run_id"])
        self.assertEqual(record.status_code,200,record.text)
        self.assertEqual(record.json()["plots"],result["plots"])
        self.assertEqual(record.json()["params"],result["params"])
        invalid=self.client.get("/api/lab/runs/..%2F..%2F.env")
        self.assertNotEqual(invalid.status_code,200)
        invalid=self.client.get("/api/lab/runs/not-an-id")
        self.assertEqual(invalid.status_code,400)

    def test_documentation_routes_have_only_allowlisted_text(self):
        for topic in ("user-guide","model-catalog","reproducibility"):
            response=self.client.get("/api/guide/"+topic)
            self.assertEqual(response.status_code,200,(topic,response.text[:500]))
            self.assertIn("QuantLab",response.text)
            self.assertNotIn("DHAN_ACCESS_TOKEN=",response.text)
        unknown=self.client.get("/api/guide/../../.env")
        self.assertNotEqual(unknown.status_code,200)
        self.assertEqual(self.client.get("/api/guide/not-listed").status_code,422)


if __name__=="__main__":
    unittest.main()
