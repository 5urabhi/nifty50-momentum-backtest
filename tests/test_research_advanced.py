"""QuantLab extended research regression: actual observations, no fabricated data."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import json
import math
import unittest

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import (model_lab, project_bundles, report_charts, research_advanced,
                             research_insights, research_library, service)
from workstation_api.app import app


class AdvancedResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix="quantlab_advanced_")
        path=Path(self.tmp.name)
        self.data=patch.object(service,"DATA",path/"data")
        self.results=patch.object(service,"RESULTS",path/"results"/"workstation_runs")
        self.data.start();self.results.start()
        self.client=TestClient(app,base_url="http://127.0.0.1:8765")
        rng=np.random.default_rng(155)
        n=280
        dates=pd.bdate_range("2023-01-02",periods=n)
        b=rng.normal(.00035,.009,n)
        c=rng.normal(.00025,.012,n)
        d=rng.normal(.00015,.010,n)
        e=rng.normal(.0005,.011,n)
        a=.0003+.45*b+.25*c+rng.normal(0,.005,n)
        returns=np.column_stack([a,b,c,d,e])
        prices=100*np.exp(np.cumsum(returns,axis=0))
        frame=pd.DataFrame(prices,index=dates,columns=["A","B","C","D","E"])
        folder=service.DATA/"workstation_imports"/"fixture_adv"
        folder.mkdir(parents=True)
        frame.to_csv(folder/"daily_prices.csv",index_label="date")
        monthly=frame.resample("ME").last()
        monthly.to_csv(folder/"prices.csv",index_label="date")
        pd.DataFrame({"date":monthly.index.date,"ticker":["A"]*len(monthly),
            "eligible":True}).to_csv(folder/"membership.csv",index=False)
        pd.DataFrame({"date":monthly.index.date,"benchmark":[.01]*len(monthly)}
            ).to_csv(folder/"benchmark.csv",index=False)
        self.id="upload_fixture_adv"
        self.folder=folder

    def tearDown(self):
        self.client.close();self.data.stop();self.results.stop();self.tmp.cleanup()

    def test_nine_plot_types_with_real_price_data(self):
        for kind,fields in [
            ("line",["A","B"]),("scatter",["A","B"]),("histogram",["A"]),
            ("kde",["A"]),("qq",["A"]),("drawdown",["A","B"]),
            ("cumulative",["A"]),("rolling_volatility",["A"]),
            ("correlation",["A","B","C"])]:
            with self.subTest(kind=kind):
                result=research_advanced.build_plot(self.id,fields,kind=kind)
                self.assertTrue(result["source"]["source_sha256"])
                self.assertGreater(result["sample_observations"],10)
                self.assertTrue(result["plot"]["kind"])
        cols=research_advanced.columns(self.id)
        self.assertEqual(cols["total_columns"],5)
        self.assertEqual(cols["total_dates"],280)

    def test_plot_transforms_and_invalid_semantics(self):
        result=research_advanced.build_plot(self.id,["A"],transform="base100")
        self.assertAlmostEqual(result["plot"]["traces"][0]["y"][0],100,places=6)
        result=research_advanced.build_plot(self.id,["A"],transform="log_return")
        self.assertEqual(result["source"]["frequency"],"daily")
        with self.assertRaisesRegex(ValueError,"exactly two"):
            research_advanced.build_plot(self.id,["A"],kind="scatter")
        with self.assertRaisesRegex(ValueError,"least two"):
            research_advanced.build_plot(self.id,["A"],kind="correlation")
        with self.assertRaisesRegex(ValueError,"not available"):
            research_advanced.build_plot(self.id,["UNLISTED"],kind="line")
        response=self.client.post("/api/workspace/plot-builder",
            json={"dataset_id":self.id,"fields":["A","B"],"kind":"correlation"})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["plot"]["kind"],"heatmap2d")

    def test_synthetic_data_is_not_labeled_observed(self):
        service.create_synthetic()
        with self.assertRaisesRegex(ValueError,"demonstration fixtures"):
            research_advanced.columns("synthetic")

    def test_diagnostics_and_ols_holdout_without_future_fit(self):
        result=research_advanced.diagnose(self.id,"A")
        self.assertEqual(result["observations"],279)
        self.assertTrue(0<=result["statistics"]["jarque_bera_p"]<=1)
        self.assertTrue(0<=result["statistics"]["ljung_box_p"]<=1)
        self.assertTrue(0<=result["statistics"]["arch_lm_p"]<=1)
        reg=research_advanced.factor_proxy_attribution(self.id,"A",["B","C"],
                                                         training_fraction=.70)
        self.assertEqual(len(reg["factor_proxies"]),2)
        self.assertGreater(reg["holdout_observations"],20)
        self.assertLess(reg["train_to"],reg["holdout_from"])
        self.assertEqual(reg["plot"]["kind"],"line2d")
        self.assertLess(reg["holdout_mse"],reg["holdout_baseline_mse"]*1.5)
        with self.assertRaisesRegex(ValueError,"excluding"):
            research_advanced.factor_proxy_attribution(self.id,"A",["A"])

    def test_significance_uses_saved_holdout_and_holm(self):
        study=research_insights.validate_out_of_sample(self.id,model="equal",
            assets=3,train_window=80,test_step=25,max_weight=.5,mode="single_holdout")
        result=research_advanced.significance([study["study_id"]])
        self.assertEqual(len(result["studies"]),1)
        row=result["studies"][0]
        self.assertEqual(row["observations"],study["test_observations"])
        self.assertEqual(len(row["bootstrap_mean_ci95"]),2)
        # Equal allocation against an equal-weight comparator can have
        # identically zero active returns. P-values are correctly unavailable.
        self.assertIsNone(row["nominal_p_value"])
        self.assertNotIn("holm_adjusted_p_value",row)
        other=research_insights.validate_out_of_sample(self.id,model="min_variance",
            assets=3,train_window=80,test_step=25,max_weight=.5,mode="single_holdout")
        corrected=research_advanced.significance([study["study_id"],other["study_id"]])
        self.assertEqual(len(corrected["studies"]),2)
        available=[x for x in corrected["studies"] if x["nominal_p_value"] is not None]
        self.assertTrue(available)
        self.assertTrue(all(x["holm_adjusted_p_value"]>=x["nominal_p_value"]
                            for x in available))
        request=self.client.post("/api/workspace/significance",
            json={"study_ids":[study["study_id"]]})
        self.assertEqual(request.status_code,200,request.text)

    def test_grid_preflight_and_real_parameter_runs(self):
        axes={"drift":[.03,.06],"volatility":[.11,.18,.24]}
        estimate=research_advanced.grid_estimate("gbm",axes,{"steps":16,"paths":24})
        self.assertEqual(estimate["run_count"],6)
        self.assertEqual(estimate["estimated_relative_work_units"],6*16*24)
        result=research_advanced.grid_sweep("gbm",None,axes,{"steps":16,"paths":24})
        self.assertEqual(result["run_count"],6)
        self.assertEqual(result["plot"]["scale"],"sequential")
        self.assertEqual(len(result["plot"]["row_labels"]),3)
        self.assertEqual(len(result["plot"]["labels"]),2)
        for row in result["runs"]:
            saved=model_lab.read_saved_model(row["run_id"])
            self.assertEqual(saved["model_id"],"gbm")
        with self.assertRaisesRegex(ValueError,"limit"):
            research_advanced.grid_estimate("gbm",{"drift":[.01*i for i in range(7)],
                                                  "volatility":[.03*i for i in range(1,8)]},
                                            {"steps":16,"paths":24})
        bad=self.client.post("/api/workspace/grid/run",json={
            "model_id":"gbm","axes":axes,"params":{"steps":16,"paths":24}})
        self.assertEqual(bad.status_code,400)

    def test_guided_goals_are_catalog_backed(self):
        for goal in research_advanced.GOALS:
            reply=research_advanced.guided(goal,self.id)
            self.assertEqual(reply["goal"],goal)
            self.assertTrue(reply["models"])
            for m in reply["models"]:
                self.assertIn(m["model_id"],research_advanced.model_registry.CATALOG)
        response=self.client.get("/api/workspace/guided/portfolio_allocation",
                                 params={"dataset_id":self.id})
        self.assertEqual(response.status_code,200,response.text)

    def test_resource_labels_copy_and_protected_raw_data(self):
        model=model_lab.save_result(model_lab.run_model("gbm",raw_parameters={
            "drift":.04,"paths":24,"steps":18,"seed":44}))
        original=model["run_id"]
        info=research_library.set_resource_info("model_run",original,
                     title="My GBM evidence",tags=["reviewed"],favorite=True)
        self.assertTrue(info["favorite"])
        self.assertIn("reviewed",info["tags"])
        library=research_library.resource_listing()
        self.assertTrue(any(x["id"]==original and x["title"]=="My GBM evidence"
                            for x in library))
        duplicated=research_library.duplicate_model_run(original)
        copy=model_lab.read_saved_model(duplicated["id"])
        self.assertEqual(copy["duplicated_from"],original)
        self.assertEqual(copy["metrics"],model["metrics"])
        self.assertNotEqual(copy["run_id"],original)
        research_library.set_resource_info("dataset",self.id,title="Observed daily stock sample")
        self.assertTrue(any(x["id"]==self.id and x["title"]=="Observed daily stock sample"
                            for x in research_library.resource_listing()))
        shared=service.DATA/"dhan"/"monthly_research"/"shared"
        shared.mkdir(parents=True,exist_ok=True)
        (shared/"daily_prices.csv").write_bytes((self.folder/"daily_prices.csv").read_bytes())
        (shared/"prices.csv").write_bytes((self.folder/"prices.csv").read_bytes())
        (shared/"membership.csv").write_bytes((self.folder/"membership.csv").read_bytes())
        (shared/"benchmark.csv").write_bytes((self.folder/"benchmark.csv").read_bytes())
        with self.assertRaisesRegex(ValueError,"Protected source"):
            research_library.resource_action("dataset","dhan_shared","trash",confirm=True)
        self.assertTrue((shared/"daily_prices.csv").exists())

    def test_click_to_add_chart_and_result_to_notebook(self):
        note=research_library.create("notebook","Indexed research report",{"cells":[]})
        chart=research_library.create("chart","Observed source chart",{
            "plot":{"kind":"line2d","title":"Source view","x":[0,1,2],
                    "traces":[{"name":"Series","y":[1.,2.,3.]}]}})
        run=model_lab.save_result(model_lab.run_model("gbm",raw_parameters={
            "paths":24,"steps":18,"seed":5}))
        chart_response=self.client.post("/api/workspace/notebooks/"+note["id"]+"/attach",
                                        json={"kind":"chart","source_id":chart["id"]})
        self.assertEqual(chart_response.status_code,200,chart_response.text)
        run_response=self.client.post("/api/workspace/notebooks/"+note["id"]+"/attach",
                                      json={"kind":"run","source_id":run["run_id"]})
        self.assertEqual(run_response.status_code,200,run_response.text)
        updated=research_library.get(note["id"])
        self.assertEqual([c["type"] for c in updated["payload"]["cells"]],["chart","run"])
        report=research_library.render_notebook_report(note["id"])
        self.assertEqual(report["figures"],1)
        html=research_library.report_path(report["id"],"html").read_text()
        self.assertIn("<svg",html)

    def test_scatter_and_heatmap_have_real_report_vectors(self):
        for kind,fields,tag in [
            ("scatter",["A","B"],"<circle"),
            ("correlation",["A","B","C"],"<rect")]:
            with self.subTest(kind=kind):
                result=research_advanced.build_plot(self.id,fields,kind=kind)
                chart=result["plot"]
                self.assertIn(tag,report_charts.svg(chart))
                self.assertIsNotNone(report_charts.pdf_drawing(chart))
                saved=research_library.create("chart","Vector "+kind,{"plot":chart})
                note=research_library.create("notebook","Figure "+kind,{
                    "cells":[{"type":"chart","chart_id":saved["id"]}]})
                report=research_library.render_notebook_report(note["id"])
                self.assertTrue(research_library.report_path(report["id"],"pdf").read_bytes().startswith(b"%PDF"))

    def test_code_version_provenance_and_real_recomputation(self):
        saved=model_lab.save_result(model_lab.run_model("gbm",raw_parameters={
            "paths":24,"steps":18,"seed":23}))
        self.assertIn("execution_environment",saved)
        self.assertIn("python",saved["execution_environment"])
        self.assertIn("numpy",saved["execution_environment"])
        self.assertIn("code_commit",saved["execution_environment"])
        first=research_insights.verify_reproducibility(saved["run_id"],recompute=False)
        self.assertFalse(first["reproducible"])
        self.assertEqual(first["verification_status"],"not_recomputed")
        second=research_insights.verify_reproducibility(saved["run_id"],recompute=True)
        self.assertTrue(second["reproducible"])
        self.assertEqual(second["verification_status"],"charts_recomputed")
        self.assertTrue(second["environment_unchanged"])

    def test_extended_quality_and_catalog_search(self):
        q=research_insights.inspect_quality(self.id)
        self.assertEqual(q["asset_count"],5)
        self.assertEqual(q["issues"]["duplicate_dates"],0)
        self.assertIsInstance(q["weekdays_since_latest"],int)
        self.assertIsInstance(q["recent_market_data"],bool)
        model_results=research_library.global_search("Heston")
        self.assertTrue(any(x["kind"]=="registered_model" and x["id"]=="heston"
                            for x in model_results))
        docs=research_library.global_search("formula reference")
        self.assertTrue(any(x["kind"]=="documentation" for x in docs))

    def test_portable_project_excludes_market_data_and_remaps_chart_ids(self):
        project=research_library.create("project","Factor thesis",{"goal":"style analysis"})
        chart=research_library.create("chart","Saved chart",{
            "project_id":project["id"],
            "plot":{"kind":"line2d","x":[1,2,3],
                    "traces":[{"name":"metric","y":[.1,.2,.3]}]}})
        notebook=research_library.create("notebook","Research notes",{
            "project_id":project["id"],
            "cells":[{"id":"c1","type":"chart","chart_id":chart["id"],"content":"Observed trend"}]})
        research_library.create("note","Private credentials must be filtered",{
            "project_id":project["id"],"dhan_access_token":"SECRET-SHOULD-NOT-LEAVE",
            "broker_password":"ANOTHER-SECRET",
            "body":"DHAN_ACCESS_TOKEN = FORBIDDEN-STRING",
        })
        file=project_bundles.bundle_path(project["id"])
        with ZipFile(file) as archive:
            self.assertEqual(set(archive.namelist()),{"manifest.json","records.json"})
            data=archive.read("records.json")
            self.assertNotIn(b"SECRET-SHOULD-NOT-LEAVE",data)
            self.assertNotIn(b"ANOTHER-SECRET",data)
            self.assertNotIn(b"FORBIDDEN-STRING",data)
            self.assertIn(b"REDACTED",data)
        imported=project_bundles.import_bundle(file.read_bytes())
        self.assertNotEqual(imported["project_id"],project["id"])
        self.assertTrue(research_library.get(imported["project_id"])["title"].endswith("(imported)"))
        notes=[x for x in research_library.list_items(kind="notebook")
               if x["payload"].get("project_id")==imported["project_id"]]
        self.assertEqual(len(notes),1)
        new_chart=notes[0]["payload"]["cells"][0]["chart_id"]
        self.assertEqual(research_library.get(new_chart)["kind"],"chart")
        bad=self.client.post("/api/workspace/projects/import-bundle",
            files={"file":("unsafe.zip",b"not a zip","application/zip")})
        self.assertEqual(bad.status_code,400)


if __name__=="__main__":
    unittest.main()
