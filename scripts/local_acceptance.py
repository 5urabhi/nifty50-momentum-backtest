"""Run the complete research project's local acceptance checks in ONE command.

This script runs locally; GitHub Actions separately tests the React browser.\nIt executes only when a user
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


def run_complete_acceptance(include_streamlit: bool=False,include_legacy: bool=False):
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
                "dashboard/pages/11_Run_History.py",
                "dashboard/pages/12_Dhan_Data_Setup.py",
                "dashboard/pages/13_Empirical_Readiness.py",
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


def _build_react() -> None:
    """Build the CURRENT React/Vite interface, not the archived Streamlit UI."""
    completed = subprocess.run(
        ["npm", "run", "build"], cwd=ROOT, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if completed.returncode:
        raise RuntimeError("React/TypeScript build FAILED:\\n" + completed.stdout[-8000:])
    print("PASS: current React/Vite TypeScript build")


def _doctor(data_dir: str, config: str) -> str:
    """Read local market-evidence readiness without pretending it is certified.

    Exit 2 plus the explicit NOT READY marker is a legitimate data shortfall.
    Other exit-2 errors (existing output path, invalid config, etc.) are failures.
    """
    args = [
        sys.executable, "scripts/quantlab_finish.py", "doctor",
        "--data-dir", data_dir, "--config", config,
    ]
    completed = subprocess.run(
        args, cwd=ROOT, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = completed.stdout.rstrip()
    if completed.returncode == 2 and "HISTORICAL RESEARCH: NOT READY" in output:
        print(output)
        print("RESEARCH EVIDENCE: NOT READY (this does not invalidate the software tests)")
        return "not_ready"
    if completed.returncode != 0 or "QUANTLAB DOCTOR: OK" not in output:
        raise RuntimeError("Historical data doctor FAILED:\\n" + output[-8000:])
    print(output)
    print("RESEARCH EVIDENCE: source review and real-market certification are still separate")
    return "numerically_ready_not_certified"


def main(argv=None):
    parser=argparse.ArgumentParser(
        description="QuantLab current React/FastAPI software acceptance plus source-aware doctor")
    parser.add_argument("--legacy-streamlit", action="store_true",
                        help="Also run archived Streamlit checks (not the current UI)")
    parser.add_argument("--skip-ui", action="store_true",
                        help="Deprecated compatibility switch: legacy UI is skipped by default")
    parser.add_argument("--include-legacy", action="store_true",
                        help="Run static-universe demonstration with survivorship warning")
    parser.add_argument("--skip-build", action="store_true",
                        help="Use only after the current React build has already passed")
    parser.add_argument("--skip-doctor", action="store_true",
                        help="Skip the read-only historical evidence readiness report")
    parser.add_argument("--data-dir", default="data/research_v1",
                        help="Local original-source research inputs, never uploaded")
    parser.add_argument("--config", default="config/research_multifactor.json",
                        help="Research configuration for the source doctor")
    args=parser.parse_args(argv)
    if args.legacy_streamlit and args.skip_ui:
        parser.error("--legacy-streamlit and --skip-ui cannot be used together")
    run_complete_acceptance(include_streamlit=args.legacy_streamlit,
                            include_legacy=args.include_legacy)
    if not args.skip_build:
        _build_react()
    if not args.skip_doctor:
        _doctor(args.data_dir, args.config)
    print("QUANTLAB SOFTWARE: PASS. Synthetic tests are NOT an empirical certificate.")


if __name__=="__main__":
    main()
