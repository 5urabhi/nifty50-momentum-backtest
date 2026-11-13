"""Final research handoff tests: immutable sources and no invented certification."""
import json
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
import pandas as pd

from index_research.experiment import ExperimentConfig
from index_research.fixtures import make_fixture
from scripts.quantlab_finish import assemble, doctor, legacy_audit, file_sha256


class FinalResearchHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="quantlab_handoff_")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.original=make_fixture(self.root/"fixture")
        self.config=self.root/"config.json"
        self.config.write_text(json.dumps(asdict(ExperimentConfig(
            name="SYNTHETIC HANDOFF TEST",factor_weights={
                "momentum":.5,"low_volatility":.5},
            top_n=10,max_weight=.2,rebalance_every=3,execution_lag=1,
            validation_start="2020-01-31",final_test_start="2023-01-31",
        ))))

    def _inputs(self):
        return {"prices.csv":str(self.original),
                "membership.csv":str(self.original),
                "benchmark.csv":str(self.original),
                "fundamentals.csv":str(self.original)}

    def test_synthetic_source_stays_synthetic_after_immutable_assembly(self):
        target=self.root/"assembled"
        result=assemble(self._inputs(),self.config,target)
        self.assertTrue(result["software_ready"],result)
        self.assertEqual(result["dataset_kind"],"SYNTHETIC_DEMONSTRATION")
        self.assertFalse(result["independent_research_certified"])
        self.assertTrue((target/"DO_NOT_CITE.txt").exists())
        self.assertFalse((target/"EVIDENCE_REVIEW.json").exists())
        receipt=json.loads((target/"SOURCE_ASSEMBLY.json").read_text())
        self.assertFalse(receipt["independent_market_data_certification"])
        self.assertFalse(receipt["source_licenses_automatically_approved"])
        for name in ("prices.csv","membership.csv","benchmark.csv","FROZEN_CONFIG.json"):
            self.assertEqual(receipt["source_files"][name]["sha256"],
                             file_sha256(target/name))
        with self.assertRaises(FileExistsError):
            assemble(self._inputs(),self.config,target)

    def test_misaligned_source_is_rejected_without_publishing_any_folder(self):
        other=self.root/"bad_benchmark"
        other.mkdir()
        bench=pd.read_csv(self.original/"benchmark.csv")
        bench.loc[0,"date"]="2015-02-01"
        bench.to_csv(other/"benchmark.csv",index=False)
        values=self._inputs()
        values["benchmark.csv"]=str(other)
        dest=self.root/"no_published_folder"
        with self.assertRaisesRegex(ValueError,"NO dataset was committed"):
            assemble(values,self.config,dest)
        self.assertFalse(dest.exists())

    def test_month_start_archive_cannot_be_misrepresented_as_formation_closes(self):
        other=self.root/"legacy_month_start"
        other.mkdir()
        price=pd.read_csv(self.original/"prices.csv")
        price["date"]=pd.to_datetime(price["date"]).dt.to_period("M").dt.to_timestamp()
        price.to_csv(other/"prices.csv",index=False)
        values=self._inputs()
        values["prices.csv"]=str(other)
        dest=self.root/"blocked_legacy"
        with self.assertRaises(ValueError):
            assemble(values,self.config,dest)
        self.assertFalse(dest.exists())

    def test_doctor_on_missing_data_still_writes_actionable_report(self):
        dest=self.root/"report"
        result=doctor(self.root/"missing_inputs",self.config,dest)
        self.assertFalse(result["software_ready"])
        self.assertFalse(result["independently_certified"])
        actions=(dest/"NEXT_ACTIONS.md").read_text()
        self.assertIn("membership.csv",actions)
        self.assertIn("Data Seeking Request Form",actions)
        self.assertTrue((dest/"RESEARCH_RELEASE.html").is_file())
        self.assertTrue((dest/"RESEARCH_PAPER_DRAFT.md").is_file())
        with self.assertRaises(FileExistsError):
            doctor(self.root/"missing_inputs",self.config,dest)

    def test_real_tracked_legacy_archive_stays_non_pit_non_tri(self):
        archive=Path(__file__).resolve().parents[1]/"nifty50_prices_monthly.csv"
        self.assertTrue(archive.is_file())
        result=legacy_audit(archive,self.root/"legacy_report")
        self.assertEqual(result["months"],162)
        self.assertEqual(result["security_columns"],49)
        self.assertEqual(result["missing_price_cells"],193)
        self.assertEqual(result["first_of_month_date_labels"],162)
        self.assertFalse(result["historical_PIT_membership_source_in_archive"])
        self.assertFalse(result["nifty_tri_benchmark_verified"])
        self.assertFalse(result["independent_research_certified"])
        self.assertTrue((self.root/"legacy_report"/"LEGACY_SECURITY_COVERAGE.csv").is_file())

    def test_missing_core_source_is_explicitly_blocked(self):
        values=self._inputs()
        del values["membership.csv"]
        with self.assertRaisesRegex(ValueError,"requires original prices"):
            assemble(values,self.config,self.root/"bad_missing_membership")

    def test_external_review_cannot_be_auto_approved(self):
        result=assemble(self._inputs(),self.config,self.root/"still_unreviewed")
        self.assertTrue(result["external_evidence_blockers"])
        self.assertFalse(result["independent_research_certified"])
