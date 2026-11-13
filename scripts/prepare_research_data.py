"""Local research-input preparation: no implicit web scraping, no secret storage.

Corporate actions, fundamental filings and benchmark files must be supplied
from authorized independent primary data sources.
"""
import argparse
from pathlib import Path
# Make project imports work when invoked directly as python scripts/<name>.py.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from index_research.dhan_data import read_instruments
from index_research.total_returns import build_research_total_returns
from index_research.fundamental_ingestion import export_factor_inputs
from index_research.benchmark_ingestion import normalize_benchmark
from index_research.empirical_validation import export_holdout_review
from index_research.research_calendar import align_research_calendar
from index_research.nse_weights import import_nifty_weight_snapshots


def main(argv=None):
    p=argparse.ArgumentParser(description="Construct and audit evidence-based Indian equity research inputs")
    sub=p.add_subparsers(dest="command",required=True)
    price=sub.add_parser("total-returns",help="Reinvest sourced dividend events in Dhan daily close series")
    price.add_argument("--raw-dir",required=True)
    price.add_argument("--instruments",required=True)
    price.add_argument("--actions",required=True)
    price.add_argument("--output-dir",required=True)
    price.add_argument("--price-basis",choices=["raw_unadjusted","split_bonus_adjusted"],
                       default="split_bonus_adjusted")
    finance=sub.add_parser("fundamentals",help="Validate dated filing records and derive transparent factors")
    finance.add_argument("--filings",required=True)
    finance.add_argument("--output-dir",required=True)
    benchmark=sub.add_parser("benchmark",help="Normalize legitimate exchange index-level CSV")
    benchmark.add_argument("--source",required=True)
    benchmark.add_argument("--date-column",required=True)
    benchmark.add_argument("--level-column",required=True)
    benchmark.add_argument("--index-name",required=True)
    benchmark.add_argument("--return-convention",choices=[
        "gross_total_return","net_total_return","price_return"],required=True)
    benchmark.add_argument("--date-format")
    benchmark.add_argument("--output-dir",required=True)
    calendar=sub.add_parser("calendar-align",
        help="Align actually observed trading-session prices and PIT membership to TRI month ends")
    calendar.add_argument("--source-dir",required=True)
    calendar.add_argument("--benchmark",default=None,
                          help="Official-normalized benchmark.csv with real prior-month level")
    calendar.add_argument("--output-dir",required=True)
    calendar.add_argument("--max-staleness-days",type=int,default=10)
    weights=sub.add_parser("nse-weight-snapshots",
        help="Import lawfully obtained monthly NIFTY50 weight CSVs with a delayed publication-date gate")
    weights.add_argument("--manifest",required=True)
    weights.add_argument("--prices",required=True,
                         help="Full historical security prices.csv, including removed/delisted names")
    weights.add_argument("--output-dir",required=True)
    weights.add_argument("--symbol-column",default="Symbol")
    weights.add_argument("--weight-column",default="Weightage (%)")
    weights.add_argument("--weight-unit",choices=["percent","fraction"],required=True)
    weights.add_argument("--index-column",default=None)
    weights.add_argument("--index-label",default="NIFTY 50")
    weights.add_argument("--pit-intervals",default=None)
    review=sub.add_parser("review",help="Report research evidence readiness without auto-approving it")
    review.add_argument("--data-dir",required=True)
    review.add_argument("--results-dir",required=True)
    review.add_argument("--declarations",required=True)
    args=p.parse_args(argv)
    if args.command=="total-returns":
        names=read_instruments(args.instruments)
        out=build_research_total_returns(
            args.raw_dir,names,args.actions,args.output_dir,
            price_basis=args.price_basis)
        print("Produced dividend-reinvested historical wealth indices:",out)
        print("MUST verify all dividends, delistings, vendor split basis, security IDs, and missing corporate actions.")
    elif args.command=="fundamentals":
        files=export_factor_inputs(args.filings,args.output_dir)
        print("Dated factor inputs:",*files)
        print("MUST independently validate first-public financial results and historical market capitalization.")
    elif args.command=="benchmark":
        files=normalize_benchmark(
            args.source,args.output_dir,date_column=args.date_column,
            level_column=args.level_column,index_name=args.index_name,
            return_convention=args.return_convention,date_format=args.date_format)
        print("Benchmark:",*files)
        print("MUST verify license, total-return convention, sample dates and benchmark methodology.")
    elif args.command=="calendar-align":
        result=align_research_calendar(
            args.source_dir,args.output_dir,args.benchmark,
            max_staleness_days=args.max_staleness_days)
        print("Monthly calendar alignment:",result)
        print("Historical source correctness and true TRI provenance still need independent review.")
    elif args.command=="nse-weight-snapshots":
        result=import_nifty_weight_snapshots(
            args.manifest,args.prices,args.output_dir,
            symbol_column=args.symbol_column,weight_column=args.weight_column,
            weight_unit=args.weight_unit,index_column=args.index_column,
            index_label=args.index_label,pit_intervals_csv=args.pit_intervals)
        print("Official-claimed monthly source snapshots (unverified):",result)
        print("Original publication dates, historical ticker coverage and source licensing remain unverified.")
    else:
        print(export_holdout_review(args.results_dir,args.data_dir,args.declarations))
        print("A review-ready status is NOT an independent market-data audit.")


if __name__=="__main__":
    main()
