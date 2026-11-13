"""Local only command-line research interface: python -m index_research.cli ..."""
import argparse
import json
from pathlib import Path
from .experiment import ExperimentConfig, run_from_directory
from .reports import build_html_report
from .pdf_report import generate_pdf_report
from .data_audit import save_dataset_audit
from .data import load_research_inputs
from .sector_data import read_sector_history, asof_sectors
from .comparison import compare_index_methods
from .robustness import sensitivity_grid


def main(argv=None):
    parser=argparse.ArgumentParser(description="Research-grade equity factor index laboratory")
    sub=parser.add_subparsers(dest="command",required=True)
    run=sub.add_parser("run",help="Run data-driven experiment from local CSV folder")
    run.add_argument("--input-dir",required=True)
    run.add_argument("--output-dir",default="results/research_run")
    run.add_argument("--config",help="JSON configuration file")
    create=sub.add_parser("make-fixture",help="Generate deterministic labeled SYNTHETIC local fixture")
    create.add_argument("--output-dir",default="data/synthetic_example")
    report=sub.add_parser("report",help="Render offline HTML report from saved outputs")
    report.add_argument("--output-dir",required=True)
    args=parser.parse_args(argv)
    if args.command=="make-fixture":
        from .fixtures import make_fixture
        print("SYNTHETIC DATA ONLY:",make_fixture(args.output_dir))
        return
    if args.command=="report":
        print(build_html_report(args.output_dir))
        print(generate_pdf_report(args.output_dir))
        return
    config=ExperimentConfig(**json.loads(Path(args.config).read_text())) if args.config else ExperimentConfig()
    _,meta=run_from_directory(args.input_dir,args.output_dir,config)
    root=Path(args.output_dir)
    save_dataset_audit(args.input_dir,root/"data_audit.json")
    try:
        prices,membership,benchmark,fundamentals=load_research_inputs(args.input_dir)
        sector_path=Path(args.input_dir)/"sectors.csv"
        sectors=asof_sectors(read_sector_history(str(sector_path)),prices.index,prices.columns) if sector_path.exists() else None
        benchmark_history=None
        liquidity_records=None
        if config.weighting=="benchmark_relative":
            from .institutional_index import read_benchmark_history
            benchmark_history=read_benchmark_history(Path(args.input_dir)/"benchmark_weights.csv")
        if config.liquidity_aum is not None:
            from .liquidity import read_liquidity
            liquidity_records=read_liquidity(Path(args.input_dir)/"liquidity.csv")
        comparison,summary=compare_index_methods(
            prices,membership,benchmark,fundamentals,config,sectors=sectors,
            benchmark_history=benchmark_history,liquidity_records=liquidity_records)
        comparison.to_csv(root/"methodology_returns.csv",index_label="date")
        summary.to_csv(root/"methodology_summary.csv",index_label="methodology")
        sensitivity=sensitivity_grid(prices,membership,benchmark,fundamentals,config,sectors=sectors,
            benchmark_history=benchmark_history,liquidity_records=liquidity_records,
            costs_bps=(0.,20.),rebalance_months=(1,3),execution_lags=(0,1),
            segment="validation" if config.validation_start else "full_history")
        sensitivity.to_csv(root/"sensitivity_grid.csv",index=False)
    except (ValueError,RuntimeError) as exc:
        print("Optional comparison or sensitivity unavailable:",exc)
    path=build_html_report(args.output_dir)
    pdf_path=generate_pdf_report(args.output_dir)
    print(json.dumps(meta["metrics_by_split"],indent=2))
    print("HTML report:",path)
    print("PDF research draft:",pdf_path)
    print("WARNING: Results are research-only, dataset validity must be independently audited.")


if __name__=="__main__":
    main()
