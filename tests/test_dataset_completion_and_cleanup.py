"""Source-safe TRI completion and recoverable dataset/download deletion.

No NSE scraping, Dhan token, actual trading, or synthetic performance claims.
"""
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from workstation_api import service, dhan_workspace as dw
from workstation_api.app import app


class DataCompletionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="quantlab_data_completion_")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.patcher=patch.object(service,"DATA",self.root/"data")
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.run_patcher=patch.object(service,"RESULTS",self.root/"results"/"workstation_runs")
        self.run_patcher.start()
        self.addCleanup(self.run_patcher.stop)
        self.client=TestClient(app,base_url="http://127.0.0.1:8765")
        self.addCleanup(self.client.close)
        self.dates=pd.date_range("2025-01-31",periods=8,freq="ME")
        self.folder=service.DATA/"dhan"/"monthly_research"/"batch_aaaaaaaaaaaaaaaa"
        self.folder.mkdir(parents=True)
        pd.DataFrame({
            "date":self.dates[1:],
            "AAA":[100+i for i in range(7)],
            "BBB":[200+i for i in range(7)],
        }).to_csv(self.folder/"prices.csv",index=False)
        pd.DataFrame({
            "date":["2025-01-31","2025-01-31"],
            "ticker":["AAA","BBB"],
            "eligible":[True,True],
        }).to_csv(self.folder/"membership.csv",index=False)
        self.dataset_id="dhan_batch_aaaaaaaaaaaaaaaa"
        self.tri=pd.DataFrame({
            "Date":self.dates,
            "Total Returns Index":[1000+i*10 for i in range(8)],
        }).to_csv(index=False).encode()

    def _attach(self,payload=None,confirm="true"):
        return self.client.post("/api/datasets/"+self.dataset_id+"/add-tri",
            data={
                "confirmed_tri":confirm,"date_column":"Date",
                "level_column":"Total Returns Index",
                "index_name":"NIFTY 50 TRI","convention":"gross_total_return",
            },
            files={"file":("exchange_TRI.csv",
                           payload if payload is not None else self.tri,"text/csv")})

    def test_original_dataset_is_untouched_and_new_tri_version_has_real_month_alignment(self):
        old_hash=hashlib.sha256((self.folder/"prices.csv").read_bytes()).hexdigest()
        result=self._attach()
        self.assertEqual(result.status_code,200,result.text)
        new=result.json()
        self.assertTrue(new["id"].startswith("upload_run_"))
        self.assertTrue(new["ready"],new)
        self.assertFalse(new["independently_verified"])
        self.assertTrue(new["benchmark_is_total_return"])
        self.assertEqual(new["benchmark_kind"],"user_supplied_total_return_index")
        self.assertFalse((self.folder/"benchmark.csv").exists())
        self.assertEqual(old_hash,hashlib.sha256((self.folder/"prices.csv").read_bytes()).hexdigest())
        out,record=service.dataset_path(new["id"])
        bench=pd.read_csv(out/"benchmark.csv")
        self.assertEqual(len(bench),7)
        self.assertEqual(bench["date"].tolist(),
                         self.dates[1:].strftime("%Y-%m-%d").tolist())
        self.assertAlmostEqual(bench["return"].iloc[0],1010/1000-1)
        self.assertFalse((out/"_tri_uploaded_source.csv").exists())
        receipt=(out/"BENCHMARK_PROVENANCE.json").read_text()
        self.assertIn('"is_independently_verified": false',receipt)
        self.assertIn(hashlib.sha256(self.tri).hexdigest(),
                      (out/"BENCHMARK_SOURCE.json").read_text())
        self.assertEqual(new["source_dataset_id"],self.dataset_id)

    def test_unobserved_preceding_month_and_incorrect_headers_rejected(self):
        trimmed=pd.read_csv(io.BytesIO(self.tri)).iloc[1:].to_csv(index=False).encode()
        result=self._attach(trimmed)
        self.assertEqual(result.status_code,400,result.text)
        self.assertIn("preceding month",result.text)
        self.assertFalse((self.folder/"benchmark.csv").exists())
        base=service.DATA/"workstation_imports"
        if base.exists():
            self.assertFalse(any(base.iterdir()),"Incomplete staging must be removed")
        wrong=self.client.post("/api/datasets/"+self.dataset_id+"/add-tri",
            data={"confirmed_tri":"true","date_column":"Date","level_column":"Wrong",
                  "index_name":"NIFTY 50 TRI","convention":"gross_total_return"},
            files={"file":("TRI.csv",self.tri,"text/csv")})
        self.assertEqual(wrong.status_code,400)
        self.assertIn("date/level",wrong.text)

    def test_price_index_or_unconfirmed_source_cannot_be_promoted(self):
        denied=self._attach(confirm="false")
        self.assertEqual(denied.status_code,400)
        not_tri=self.client.post("/api/datasets/"+self.dataset_id+"/add-tri",
            data={"confirmed_tri":"true","date_column":"Date",
                  "level_column":"Total Returns Index","index_name":"NIFTY 50",
                  "convention":"price_return"},
            files={"file":("index.csv",self.tri,"text/csv")})
        self.assertEqual(not_tri.status_code,400)
        (self.folder/"DO_NOT_CITE.txt").write_text("Synthetic data; do not treat as observed.")
        refused=self._attach()
        self.assertEqual(refused.status_code,400)
        self.assertIn("synthetic",refused.text.lower())

    def test_new_derived_dataset_has_explicit_recoverable_trash(self):
        ready=self._attach().json()
        item_id=ready["id"]
        deleted=self.client.post("/api/workspace/resources/action",json={
            "kind":"dataset","item_id":item_id,"action":"trash","confirm":True,
        })
        self.assertEqual(deleted.status_code,200,deleted.text)
        self.assertFalse(any(x["id"]==item_id for x in service.datasets()))
        resource=self.client.get("/api/workspace/resources?include_trashed=true").json()
        self.assertTrue(any(x["id"]==item_id and x["trashed"]
                            for x in resource["resources"]))
        restored=self.client.post("/api/workspace/resources/action",json={
            "kind":"dataset","item_id":item_id,"action":"restore",
        })
        self.assertEqual(restored.status_code,200,restored.text)
        self.assertTrue(any(x["id"]==item_id for x in service.datasets()))
        self.assertFalse((self.folder/"benchmark.csv").exists(),
                         "Restoring derived dataset must never modify original source")

    def test_queued_download_trash_restore_and_permanent_purge_preserve_shared_cache(self):
        master=service.DATA/"dhan"/"instrument_master.csv"
        master.parent.mkdir(parents=True,exist_ok=True)
        pd.DataFrame([{
            "SEM_EXM_EXCH_ID":"NSE","SEM_SEGMENT":"E",
            "SEM_SMST_SECURITY_ID":"1333","SEM_INSTRUMENT_NAME":"EQUITY",
            "SEM_TRADING_SYMBOL":"RELIANCE","SEM_CUSTOM_SYMBOL":"Reliance Industries",
            "SEM_SERIES":"EQ",
        }]).to_csv(master,index=False)
        dw._catalog_cached.cache_clear()
        self.addCleanup(dw._catalog_cached.cache_clear)
        stock=next(x for x in dw.catalog() if x["symbol"]=="RELIANCE")
        cache=dw._history_file(stock,None)
        cache.parent.mkdir(parents=True,exist_ok=True)
        cache.write_text("mock,original,source\n")
        original_hash=hashlib.sha256(cache.read_bytes()).hexdigest()
        batch=dw.create_batch("selected",[stock["id"]],[],
                              "2025-01-01","2025-02-01",None,False)
        batch_id=batch["id"]
        self.assertEqual(self.client.delete("/api/dhan/batches/"+batch_id).status_code,400)
        deleted=self.client.delete("/api/dhan/batches/"+batch_id+"?confirm=true")
        self.assertEqual(deleted.status_code,200,deleted.text)
        self.assertFalse(any(x["id"]==batch_id for x in dw.list_batches()))
        self.assertTrue(any(x["id"]==batch_id for x in dw.list_trashed_batches()))
        self.assertEqual(hashlib.sha256(cache.read_bytes()).hexdigest(),original_hash)
        undo=self.client.post("/api/dhan/batches/trash/"+batch_id+"/restore")
        self.assertEqual(undo.status_code,200,undo.text)
        self.assertTrue(any(x["id"]==batch_id for x in dw.list_batches()))
        self.client.delete("/api/dhan/batches/"+batch_id+"?confirm=true")
        purged=self.client.delete("/api/dhan/batches/trash/"+batch_id+"?confirm=true")
        self.assertEqual(purged.status_code,200,purged.text)
        self.assertEqual(dw.list_trashed_batches(),[])
        self.assertEqual(hashlib.sha256(cache.read_bytes()).hexdigest(),original_hash)

    def test_active_download_cannot_be_deleted(self):
        master=service.DATA/"dhan"/"instrument_master.csv"
        master.parent.mkdir(parents=True,exist_ok=True)
        pd.DataFrame([{
            "SEM_EXM_EXCH_ID":"NSE","SEM_SEGMENT":"E",
            "SEM_SMST_SECURITY_ID":"1333","SEM_INSTRUMENT_NAME":"EQUITY",
            "SEM_TRADING_SYMBOL":"RELIANCE","SEM_CUSTOM_SYMBOL":"Reliance Industries",
            "SEM_SERIES":"EQ",
        }]).to_csv(master,index=False)
        dw._catalog_cached.cache_clear()
        stock=next(x for x in dw.catalog() if x["symbol"]=="RELIANCE")
        batch=dw.create_batch("selected",[stock["id"]],[],
                              "2025-01-01","2025-02-01",None,False)
        dw.ACTIVE_BATCHES.add(batch["id"])
        try:
            resp=self.client.delete("/api/dhan/batches/"+batch["id"]+"?confirm=true")
            self.assertIn(resp.status_code,(400,409),resp.text)
            self.assertTrue((dw._batches()/batch["id"]).is_dir())
        finally:
            dw.ACTIVE_BATCHES.discard(batch["id"])
            dw._catalog_cached.cache_clear()
