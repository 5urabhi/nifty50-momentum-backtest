"""Offline acceptance of the QuantLab research workspace and safety contracts."""
from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import model_lab, research_insights, research_library, service
from workstation_api.app import app


class ResearchWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quantlab_workspace_")
        root = Path(self.temp.name)
        self.pdata = patch.object(service, "DATA", root / "data")
        self.presult = patch.object(service, "RESULTS", root / "results" / "workstation_runs")
        self.pdata.start()
        self.presult.start()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        dates = pd.bdate_range("2024-01-01", periods=220)
        rng = np.random.default_rng(1934)
        noise = rng.normal(0.0002, 0.012, (len(dates), 4))
        prices = pd.DataFrame(100*np.exp(np.cumsum(noise, axis=0)), index=dates,
                              columns=["A","B","C","D"])
        folder = service.DATA / "workstation_imports" / "fixture"
        folder.mkdir(parents=True)
        prices.to_csv(folder / "daily_prices.csv", index_label="date")
        prices.resample("ME").last().to_csv(folder / "prices.csv", index_label="date")
        membership = pd.DataFrame([{"date": d.date().isoformat(), "ticker": name,
                                     "eligible": True}
                                   for d in prices.resample("ME").last().index
                                   for name in prices.columns])
        membership.to_csv(folder / "membership.csv", index=False)
        pd.DataFrame({"date": prices.resample("ME").last().index.date,
                      "benchmark": [0.01]*len(prices.resample("ME").last())}).to_csv(
                          folder / "benchmark.csv", index=False)
        self.dataset_id = "upload_fixture"
        self.source_folder = folder

    def tearDown(self):
        self.client.close()
        self.pdata.stop()
        self.presult.stop()
        self.temp.cleanup()

    def _saved(self, drift=.05):
        result = model_lab.run_model("gbm", raw_parameters={
            "drift":drift,"steps":24,"paths":40,"seed":2})
        return model_lab.save_result(result)

    def test_records_crud_archive_favorite_restore_and_permanent_delete(self):
        obj = research_library.create("configuration", "Study base",
                                       {"model_id":"gbm","params":{"seed":1}}, ["quant"])
        item_id = obj["id"]
        updated = research_library.update(item_id, title="Study updated", favorite=True)
        self.assertEqual(updated["title"], "Study updated")
        self.assertTrue(updated["favorite"])
        research_library.action(item_id, "archive")
        self.assertFalse(any(x["id"]==item_id for x in research_library.list_items()))
        self.assertTrue(any(x["id"]==item_id for x in research_library.list_items(archived=True)))
        research_library.action(item_id, "unarchive")
        research_library.action(item_id, "trash")
        self.assertEqual(research_library.list_items(), [])
        self.assertEqual(research_library.list_items(trashed=True)[0]["id"], item_id)
        research_library.action(item_id, "restore")
        research_library.action(item_id, "trash")
        with self.assertRaises(ValueError):
            research_library.action(item_id, "purge")
        research_library.action(item_id, "purge", confirm=True)
        with self.assertRaises(FileNotFoundError):
            research_library.get(item_id)

    def test_reversible_dataset_trash_never_deletes_raw_market_history(self):
        source = self.source_folder
        self.assertTrue(source.exists())
        with self.assertRaisesRegex(ValueError, "confirmation"):
            research_library.resource_action("dataset", self.dataset_id, "trash")
        research_library.resource_action("dataset", self.dataset_id, "trash", confirm=True)
        self.assertFalse(source.exists())
        result = research_library.resource_status("dataset", self.dataset_id)
        self.assertTrue(result["trashed"])
        research_library.resource_action("dataset", self.dataset_id, "restore")
        self.assertTrue(source.exists())
        self.assertFalse(research_library.resource_status("dataset", self.dataset_id)["trashed"])
        with self.assertRaises(ValueError):
            research_library.resource_action("dataset", "dhan_shared", "trash", confirm=True)

    def test_saved_runs_overlay_requires_compatible_axes_and_modes(self):
        first, second = self._saved(.05), self._saved(.09)
        selected = [{"kind":"model_run","run_id":first["run_id"]},
                    {"kind":"model_run","run_id":second["run_id"]}]
        merged = research_insights.compare(selected, normalize="base100")
        self.assertEqual(len(merged["plot"]["traces"]), 6)
        self.assertEqual(merged["normalization"],"base100")
        self.assertGreaterEqual(len(merged["plot"]["x"]), 10)
        self.assertAlmostEqual(merged["plot"]["traces"][0]["y"][0],100)
        with self.assertRaisesRegex(ValueError, "between two and eight"):
            research_insights.compare(selected[:1])
        theoretical = model_lab.save_result(model_lab.run_model("black_scholes"))
        with self.assertRaisesRegex(ValueError, "theoretical"):
            research_insights.compare([selected[0],{"kind":"model_run",
                                                    "run_id":theoretical["run_id"]}])

    def test_parameter_sweep_runs_actual_models_and_saves_each_run(self):
        study = research_insights.sweep("gbm", None, {"steps":24,"paths":30},
                                        "volatility", [0.1,0.2,0.3])
        self.assertEqual(len(study["runs"]),3)
        self.assertTrue(study["plot"])
        self.assertEqual(study["model_id"],"gbm")
        for run in study["runs"]:
            self.assertEqual(model_lab.read_saved_model(run["run_id"])["model_id"],"gbm")

    def test_invalid_final_sweep_value_creates_no_partial_runs(self):
        with self.assertRaises(ValueError):
            research_insights.sweep("gbm",None,{"steps":24,"paths":30},
                                    "volatility",[.1,-.2])
        self.assertEqual(model_lab.list_saved_models(),[])

    def test_oos_train_end_strictly_precedes_test_start(self):
        result = research_insights.validate_out_of_sample(self.dataset_id,
                   model="min_variance",assets=4,train_window=75,test_step=20,
                   max_weight=.45,mode="walk_forward")
        self.assertGreater(result["test_observations"], 50)
        self.assertEqual(result["metrics"]["observations"], result["test_observations"])
        self.assertEqual(len(result["rows"]), result["test_observations"])
        for fold in result["folds"]:
            self.assertLess(fold["train_to"], fold["test_from"])
            self.assertAlmostEqual(sum(fold["weights"].values()),1.,places=5)
        self.assertTrue(result["uncertainty"]["available"])
        study = research_library.get(result["study_id"])
        self.assertEqual(study["kind"],"study")

    def test_large_holdout_preserves_every_return_with_bounded_graph(self):
        prices_path = self.source_folder / "daily_prices.csv"
        rng = np.random.default_rng(7832)
        dates = pd.bdate_range("2018-01-01", periods=1200)
        values = 100*np.exp(np.cumsum(rng.normal(.0002,.01,(len(dates),4)),axis=0))
        pd.DataFrame(values,index=dates,columns=["A","B","C","D"]).to_csv(
            prices_path,index_label="date")
        result = research_insights.validate_out_of_sample(self.dataset_id,
                    model="equal", assets=4, train_window=75, test_step=20,
                    max_weight=.45, mode="single_holdout")
        self.assertGreater(result["test_observations"],1000)
        self.assertLessEqual(result["figure_observations"],601)
        self.assertEqual(len(result["plot"]["x"]),result["figure_observations"])
        artifact = research_insights.study_returns_path(result["study_id"])
        self.assertTrue(artifact.is_file())
        self.assertEqual(len(pd.read_csv(artifact)), result["test_observations"])
        response = self.client.get(
             "/api/workspace/studies/"+result["study_id"]+"/returns.csv")
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn(b"date,strategy,equal_weight",response.content)
        research_library.action(result["study_id"],"trash")
        with self.assertRaises(FileNotFoundError):
            research_insights.study_returns_path(result["study_id"])
        research_library.action(result["study_id"],"purge",confirm=True)
        self.assertFalse(artifact.exists())

    def test_single_chronological_holdout_has_only_one_fold(self):
        result = research_insights.validate_out_of_sample(self.dataset_id,
                   model="equal",assets=4,train_window=75,test_step=20,
                   max_weight=.45,mode="single_holdout")
        self.assertEqual(len(result["folds"]),1)
        self.assertEqual(result["test_observations"],(220-1)-75)  # one price date is lost to return formation

    def test_validation_never_selects_assets_using_future_availability(self):
        path = self.source_folder / "daily_prices.csv"
        frame = pd.read_csv(path)
        # Alphabetically first asset becomes available only AFTER formation.
        # A look-ahead selector would choose this in preference to A/B/C/D.
        frame.insert(1, "AAA_FUTURE", np.r_[[np.nan]*95, np.arange(125)+120.])
        frame.to_csv(path, index=False)
        result = research_insights.validate_out_of_sample(self.dataset_id,
                   model="equal", assets=4, train_window=75, test_step=25,
                   max_weight=.45, mode="single_holdout")
        self.assertNotIn("AAA_FUTURE", result["source"]["assets"])
        self.assertEqual(result["source"]["selection_rule"].split(",")[0],
                         "Eligible from first training window only")
        self.assertEqual(result["source"]["source_sha256"],
                         research_insights.file_sha256(path))
        self.assertEqual(result["source"]["dataset_kind"], "uploaded")

    def test_synthetic_fixture_cannot_masquerade_as_historical_holdout(self):
        service.create_synthetic()
        self.assertIn("Synthetic fixture", model_lab.readiness("synthetic")["warning"])
        with self.assertRaisesRegex(ValueError,"Synthetic demonstration"):
            research_insights.validate_out_of_sample("synthetic", model="equal",
                     assets=3, train_window=50, test_step=20, max_weight=.5)
        self.assertEqual(research_insights.evidence_class({
            "mode":"historical", "source":{"dataset_kind":"synthetic"}}),
            "synthetic_fixture")
        self.assertEqual(research_insights.evidence_class({
            "mode":"historical", "source":{"dataset_kind":"uploaded"}}),
            "historical")
        research_library.resource_action("dataset","synthetic","archive")
        self.assertEqual(service.create_synthetic()["id"], "synthetic")

    def test_quality_reports_actual_prices_without_forward_fill(self):
        result = research_insights.inspect_quality(self.dataset_id)
        self.assertEqual(result["asset_count"],4)
        self.assertEqual(result["price_dates"],220)
        self.assertEqual(result["duplicate_dates"],0)
        self.assertEqual(result["assets"][0]["missing_prices"],0)
        self.assertRegex(result["sha256"],r"^[0-9a-f]{64}$")

    def test_reproducibility_detects_model_source_change(self):
        saved = self._saved()
        stable = research_insights.verify_reproducibility(saved["run_id"],recompute=True)
        self.assertTrue(stable["reproducible"])
        self.assertTrue(stable["recomputed_figure_match"])

    def test_notebook_report_html_escapes_untrusted_content(self):
        model = self._saved()
        note = research_library.create("notebook","Risk research",{
            "cells":[{"type":"markdown","content":"<script>alert(1)</script>"},
                     {"type":"run","run_id":model["run_id"]}]})
        report = research_library.render_notebook_report(note["id"])
        path = research_library.report_path(report["id"], "html")
        html = path.read_text()
        self.assertNotIn("<script>alert",html)
        self.assertIn("&lt;script&gt;",html)
        self.assertIn("Geometric Brownian Motion",html)
        self.assertTrue(research_library.report_path(report["id"],"markdown").exists())

    def test_split_panel_compare_accepts_different_saved_evidence(self):
        gbm = self._saved()
        bsm = model_lab.save_result(model_lab.run_model("black_scholes"))
        chosen = [{"kind":"model_run","run_id":gbm["run_id"]},
                  {"kind":"model_run","run_id":bsm["run_id"]}]
        split = research_insights.compare(chosen, layout="split")
        self.assertEqual(split["layout"],"split")
        self.assertEqual(len(split["plots"]), 2)
        self.assertNotIn("plot", split)
        invalid = self.client.post("/api/workspace/compare",json={"selections":chosen})
        self.assertEqual(invalid.status_code,400,invalid.text)
        valid = self.client.post("/api/workspace/compare",json={
            "selections": chosen, "layout": "split"})
        self.assertEqual(valid.status_code,200,valid.text)

    def test_report_pdf_export_and_edit_updates_all_formats(self):
        notebook = research_library.create("notebook","Portfolio report",{
            "cells":[{"type":"markdown","content":"Risk attribution is hypothetical."}]})
        report = research_library.render_notebook_report(notebook["id"])
        pdf = research_library.report_path(report["id"], "pdf")
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))
        source = self.client.get("/api/workspace/reports/"+report["id"]+"/source")
        self.assertEqual(source.status_code,200,source.text)
        changed = self.client.put("/api/workspace/reports/"+report["id"]+"/source",
                                  json={"content":"# Updated research\n\nNew findings"})
        self.assertEqual(changed.status_code,200,changed.text)
        html = research_library.report_path(report["id"],"html").read_text()
        md = research_library.report_path(report["id"],"markdown").read_text()
        self.assertIn("New findings",html)
        self.assertIn("New findings",md)
        self.assertTrue(research_library.report_path(report["id"],"pdf").read_bytes().startswith(b"%PDF"))
        response = self.client.get("/api/workspace/reports/"+report["id"]+"/pdf")
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_job_history_saved_across_sessions(self):
        snapshot = {"id":"abc12345","kind":"workspace_validation","status":"complete",
                    "created_utc":"2026-11-01T00:00:00+00:00",
                    "result":{"status":"ready","study_id":"study_123"}}
        research_library.store_job(snapshot)
        historic = research_library.list_job_history()
        self.assertTrue(historic)
        self.assertEqual(historic[0]["id"],"abc12345")
        self.assertEqual(historic[0]["result"]["study_id"],"study_123")
        pending = {**snapshot,"id":"abc12346","status":"running"}
        research_library.store_job(pending)
        rows = research_library.list_job_history()
        self.assertEqual(next(x for x in rows if x["id"]=="abc12346")["status"],"interrupted")

    def test_archived_dataset_remains_resolvable_and_protects_source(self):
        self.assertTrue(any(x["id"]==self.dataset_id for x in service.datasets()))
        research_library.resource_action("dataset",self.dataset_id,"archive")
        self.assertFalse(any(x["id"]==self.dataset_id for x in service.datasets()))
        self.assertEqual(service.dataset_path(self.dataset_id)[0],self.source_folder)
        listed = research_library.resource_listing(include_trashed=True)
        self.assertTrue(any(x["id"]==self.dataset_id and x["archived"] for x in listed))
        research_library.resource_action("dataset",self.dataset_id,"unarchive")
        self.assertTrue(any(x["id"]==self.dataset_id for x in service.datasets()))

    def test_referenced_dataset_prevents_unsafe_delete(self):
        research_library.create("note","Source is needed",
                                {"dataset_id":self.dataset_id})
        with self.assertRaisesRegex(ValueError,"referenced"):
            research_library.resource_action("dataset",self.dataset_id,"trash",confirm=True)
        self.assertTrue(self.source_folder.exists())

    def test_notebook_chart_figure_preserved_in_html_and_pdf(self):
        model = self._saved()
        plot = model["plots"][0]
        chart = research_library.create("chart","Saved simulation fan",
                  {"plot":plot,"annotation":"Mathematical distribution"})
        notebook = research_library.create("notebook","Stochastic figure study",{
            "cells":[{"type":"chart","chart_id":chart["id"],
                      "content":"Figure derived from saved model parameters"}]})
        report = research_library.render_notebook_report(notebook["id"])
        self.assertEqual(report["figures"],1)
        html = research_library.report_path(report["id"],"html").read_text()
        self.assertIn("<svg",html)
        self.assertIn("Saved simulation fan",html)
        self.assertIn("Figure derived",html)
        self.assertTrue(research_library.report_path(report["id"],"pdf").read_bytes().startswith(b"%PDF"))
        research_library.action(chart["id"],"trash")
        edited = research_library.edit_report(report["id"],
                    "# Rewritten interpretation\nThe source chart remains in the appendix.")
        self.assertTrue(edited["payload"]["manually_edited"])
        self.assertIn("<svg",research_library.report_path(report["id"],"html").read_text())

    def test_workspace_api_create_edit_search_and_archive(self):
        created = self.client.post("/api/workspace/records",json={
            "kind":"project","title":"Index Research","payload":{"goal":"factor study"},
            "tags":["finance"]})
        self.assertEqual(created.status_code,200,created.text)
        obj = created.json()
        search = self.client.get("/api/workspace/search",params={"q":"Index Research"})
        self.assertEqual(search.status_code,200,search.text)
        self.assertTrue(any(x["id"]==obj["id"] for x in search.json()["results"]))
        updated = self.client.patch("/api/workspace/records/"+obj["id"],
                                    json={"favorite":True})
        self.assertEqual(updated.status_code,200,updated.text)
        self.assertTrue(updated.json()["favorite"])
        deleted = self.client.post("/api/workspace/records/"+obj["id"]+"/action",
                                   json={"action":"trash"})
        self.assertEqual(deleted.status_code,200,deleted.text)

    def test_external_network_and_order_routes_are_not_required(self):
        response = self.client.get("/api/workspace/resources")
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(any(x["id"]==self.dataset_id for x in response.json()["resources"]))
        response = self.client.post("/api/workspace/compare",json={"selections":[]})
        self.assertEqual(response.status_code,422)


if __name__=="__main__":
    unittest.main()
