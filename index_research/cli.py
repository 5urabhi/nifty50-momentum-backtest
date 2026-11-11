"""Local only command-line research interface: python -m index_research.cli ..."""
import argparse
import json
from pathlib import Path
from .experiment import ExperimentConfig, run_from_directory
from .reports import build_html_report


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
        return
    config=ExperimentConfig(**json.loads(Path(args.config).read_text())) if args.config else ExperimentConfig()
    _,meta=run_from_directory(args.input_dir,args.output_dir,config)
    path=build_html_report(args.output_dir)
    print(json.dumps(meta["metrics_by_split"],indent=2))
    print("Report:",path)
    print("WARNING: Results are research-only, dataset validity must be independently audited.")


if __name__=="__main__":
    main()
