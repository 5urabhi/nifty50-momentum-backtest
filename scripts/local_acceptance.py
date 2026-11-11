"""Run the complete research project's local acceptance checks in ONE command.

This script is never invoked by GitHub Actions. It executes only when a user
runs python scripts/local_acceptance.py on a local machine.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def _run(args):
    completed=subprocess.run(
        [sys.executable,*args],cwd=ROOT,check=False,text=True,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if completed.returncode:
        raise RuntimeError(f"FAILED: {' '.join(args)}\n{completed.stdout[-8000:]}")
    print(f"PASS: {' '.join(args)}")
    return completed.stdout


def check_files(folder: Path, expected: set[str]):
    for filename in expected:
        path=folder/filename
        if not path.is_file() or path.stat().st_size<=0:
            raise RuntimeError(f"Missing/empty research artifact: {path}")


def run_complete_acceptance(include_streamlit: bool=True,include_legacy: bool=False):
    with tempfile.TemporaryDirectory(prefix="equity_quant_acceptance_") as tmp:
        root=Path(tmp)
        inputs=root/"inputs"
        outputs=root/"outputs"
        _run(["-m","unittest","discover","-s","tests","-v"])
        _run(["-m","index_research.cli","make-fixture","--output-dir",str(inputs)])
        _run(["-m","index_research.cli","run","--input-dir",str(inputs),
              "--output-dir",str(outputs),
              "--config","config/research_multifactor.json"])
        expected={
            "monthly_results.csv","post_rebalance_weights.csv",
            "pre_trade_weights.csv","factor_scores.csv","concentration.csv",
            "rolling_metrics.csv","cost_sensitivity.csv",
            "sector_exposure.csv","research_manifest.json",
            "dataset_audit.json","robustness_grid.csv",
            "factor_rank_ic.csv","portfolio_factor_exposures.csv",
            "data_quality.json","methodology_returns.csv","methodology_summary.csv",
            "research_report.html","research_paper_draft.pdf",
        }
        check_files(outputs,expected)
        manifest=json.loads((outputs/"research_manifest.json").read_text())
        assert manifest["config"]["dataset_status"]=="unverified", "Config status was changed unexpectedly"
        assert manifest["coverage"]["historical_sector_classification"],"Synthetic sectors were not wired"
        assert "final_test" in manifest["metrics_by_split"],"Chronological final test missing"
        import pandas as pd
        result=pd.read_csv(outputs/"monthly_results.csv")
        if result.empty or not result["strategy_net"].notna().all():
            raise RuntimeError("Nonfinite/missing net strategy returns")
        pdf=(outputs/"research_paper_draft.pdf").read_bytes()
        if not pdf.startswith(b"%PDF-"):
            raise RuntimeError("Generated report is not a PDF")
        with zipfile.ZipFile(root/"artifacts.zip","w") as archive:
            for path in outputs.iterdir():
                archive.write(path,path.name)
        with zipfile.ZipFile(root/"artifacts.zip") as archive:
            if not expected.issubset(set(archive.namelist())):
                raise RuntimeError("Research bundle missing outputs")
        print("PASS: synthetic factor experiment, as-of sectors, holdout, artifacts, PDF and ZIP")

        if include_streamlit:
            from streamlit.testing.v1 import AppTest
            pages=[
                "dashboard/app.py",
                "dashboard/pages/1_Index_Research.py",
                "dashboard/pages/2_Model_Comparison.py",
                "dashboard/pages/3_Advanced_Mathematics.py",
                "dashboard/pages/4_Rolling_Validation.py",
                "dashboard/pages/5_Quantitative_Models.py",
                "dashboard/pages/6_Factor_Laboratory.py",
                "dashboard/pages/7_Index_Comparisons.py",
                "dashboard/pages/8_Research_Report.py",
                "dashboard/pages/9_Risk_Attribution.py",
                "dashboard/pages/9_Robustness.py",
                "dashboard/pages/10_Visual_Validation.py",
            ]
            for name in pages:
                app=AppTest.from_file(str(ROOT/name),default_timeout=60).run()
                if app.exception:
                    raise RuntimeError(f"Streamlit startup failure in {name}: {list(app.exception)}")
                print("PASS: Streamlit page can render initially:",name)
            # End-to-end UI interaction: switch on synthetic data and run the index page.
            app=AppTest.from_file(str(ROOT/"dashboard/pages/1_Index_Research.py"),
                                  default_timeout=120)
            app.run()
            if not app.toggle:
                raise RuntimeError("Missing synthetic toggle on Index Research page")
            app.toggle[0].set_value(True)
            app.run()
            if not app.button:
                raise RuntimeError("Missing research run button")
            app.button[0].click()
            app.run()
            if app.exception or app.error:
                raise RuntimeError(f"End-to-end Streamlit run failed: {list(app.exception)} / {list(app.error)}")
            print("PASS: Streamlit synthetic index experiment UI interaction")

        if include_legacy:
            inputs_legacy=root/"legacy"
            outputs_legacy=root/"legacy_result"
            _run(["scripts/prepare_legacy_demo.py","--output-dir",str(inputs_legacy)])
            _run(["-m","index_research.cli","run",
                  "--input-dir",str(inputs_legacy),"--output-dir",str(outputs_legacy),
                  "--config","config/research_legacy_demo.json"])
            if not (inputs_legacy/"DEMONSTRATION_LIMITATIONS.json").exists():
                raise RuntimeError("Historical legacy caveat record missing")
            print("PASS: legacy survivorship-bias demonstration (NOT historical index evidence)")
    print("\nALL REQUESTED LOCAL SOFTWARE ACCEPTANCE CHECKS PASSED")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--skip-ui",action="store_true",help="Skip Streamlit AppTest checks")
    parser.add_argument("--include-legacy",action="store_true",
                        help="Run original static universe with explicit survivorship warning")
    args=parser.parse_args()
    run_complete_acceptance(include_streamlit=not args.skip_ui,
                            include_legacy=args.include_legacy)


if __name__=="__main__":
    main()
