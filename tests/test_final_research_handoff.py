"""Final research handoff tests: immutable sources and no invented certification."""
import json
import io
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
import pandas as pd

from index_research.experiment import ExperimentConfig
from index_research.fixtures import make_fixture
from scripts.quantlab_finish import assemble, doctor, legacy_audit, file_sha256, main


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
        self.assertNotIn(chr(92)+chr(96), actions,
                         "Generated Markdown must not escape code-fence backticks")
        self.assertIn("```bash",actions)
        self.assertIn("Local dataset: `",actions)
        # Keep generated fenced CLI as four contiguous shell command lines.
        shell_block=actions.split("```bash\n",1)[1].split("\n```",1)[0]
        command_lines=shell_block.splitlines()
        self.assertEqual(len(command_lines),4)
        self.assertTrue(all(line.strip() for line in command_lines))
        self.assertTrue(all(line.endswith(chr(92)) for line in command_lines[:3]))
        self.assertNotIn(chr(92)+"\n\n",shell_block)
        self.assertIn("do not use --execute",actions.lower())
        self.assertTrue((dest/"RESEARCH_RELEASE.html").is_file())
        self.assertTrue((dest/"RESEARCH_PAPER_DRAFT.md").is_file())
        with self.assertRaises(FileExistsError):
            doctor(self.root/"missing_inputs",self.config,dest)

    def test_short_status_is_saved_and_terminal_defaults_to_one_screen(self):
        folder=self.root/"doctor_short"
        stdout=io.StringIO()
        with redirect_stdout(stdout):
            code=main([
                "doctor","--data-dir",str(self.root/"no_real_data"),
                "--config",str(self.config),"--output-dir",str(folder),
            ])
        brief=stdout.getvalue()
        self.assertEqual(code,2,"Missing market research input is not research-ready")
        self.assertIn("QUANTLAB DOCTOR: OK",brief)
        self.assertIn("HISTORICAL RESEARCH: NOT READY",brief)
        self.assertIn("prices.csv",brief)
        self.assertIn("membership.csv",brief)
        self.assertIn("benchmark.csv",brief)
        self.assertIn("DETAILS (optional)",brief)
        self.assertLess(len(brief.splitlines()),8)
        self.assertNotIn("Step 1",brief)
        self.assertEqual(brief,(folder/"STATUS.txt").read_text())
        self.assertTrue((folder/"NEXT_ACTIONS.md").exists())

    def test_json_is_opt_in_for_developers(self):
        folder=self.root/"doctor_json"
        output=io.StringIO()
        with redirect_stdout(output):
            code=main([
                "doctor","--data-dir",str(self.root/"missing_inputs"),
                "--config",str(self.config),"--output-dir",str(folder),"--json",
            ])
        self.assertEqual(code,2)
        data=json.loads(output.getvalue())
        self.assertFalse(data["software_ready"])
        self.assertEqual(data["output"],str(folder))
        self.assertIn("HISTORICAL RESEARCH: NOT READY",
                      (folder/"STATUS.txt").read_text())

    def test_missing_source_error_prints_simple_error_not_traceback(self):
        folder=self.root/"exists_already"
        folder.mkdir()
        stderr=io.StringIO()
        with redirect_stderr(stderr):
            code=main([
                "doctor","--data-dir",str(self.root/"missing_inputs"),
                "--config",str(self.config),"--output-dir",str(folder),
            ])
        self.assertEqual(code,2)
        self.assertIn("ERROR: Release report exists",stderr.getvalue())
        self.assertNotIn("Traceback",stderr.getvalue())

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

    def test_zero_weight_fundamental_does_not_require_missing_filings(self):
        from index_research.experiment import ExperimentConfig
        from scripts.complete_research_studies import research_preflight
        from dataclasses import replace
        from index_research.fixtures import make_fixture
        source=make_fixture(self.root/"zero_weight_fixture")
        (source/"fundamentals.csv").unlink()
        config=ExperimentConfig(
            name="SYNTH ZERO FACTOR INPUT",
            factor_weights={"momentum":1.,"value":0.,"quality":0.,"yield":0.},
            top_n=10,max_weight=.2,rebalance_every=3,execution_lag=1,
            validation_start="2020-01-31",final_test_start="2023-01-31")
        status=research_preflight(source,config)
        self.assertTrue(status["software_ready"],status)
        self.assertEqual(status["classification"],"SYNTHETIC_DEMONSTRATION")

    def test_external_review_cannot_be_auto_approved(self):
        result=assemble(self._inputs(),self.config,self.root/"still_unreviewed")
        self.assertTrue(result["external_evidence_blockers"])
        self.assertFalse(result["independent_research_certified"])
