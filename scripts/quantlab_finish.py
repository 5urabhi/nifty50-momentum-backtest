#!/usr/bin/env python3
"""QuantLab final research handoff: assemble, diagnose, execute, never certify.

No remote requests, broker orders, data fabrication, credentials, or source
licensing assumptions. All inputs are explicitly provided local files and
all outputs are immutable. Genuine market-source validation remains a
separate human and licensing process.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from shlex import quote as shell_quote
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import numpy as np

from index_research.data import load_research_inputs
from index_research.experiment import ExperimentConfig
from scripts.complete_research_studies import research_preflight
from scripts.research_release import generate

STANDARD = (
    "prices.csv", "membership.csv", "benchmark.csv", "fundamentals.csv",
    "sectors.csv", "corporate_actions.csv", "benchmark_weights.csv",
    "factor_returns.csv", "liquidity.csv",
)
METADATA = {
    "prices.csv": ("RETURN_METHODOLOGY.json",),
    "membership.csv": ("PIT_MEMBERSHIP_PROVENANCE.json",),
    "benchmark.csv": ("BENCHMARK_SOURCE.json",),
    "fundamentals.csv": ("FUNDAMENTAL_METHODS.json", "fundamental_sources.csv"),
    "benchmark_weights.csv": ("NSE_WEIGHTAGE_SOURCE_MANIFEST.json",),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_input(source: str | Path, target_name: str) -> Path:
    declared=Path(source).expanduser()
    if declared.is_symlink():
        raise ValueError("Symlink inputs are not accepted: " + str(declared))
    file=declared/target_name if declared.is_dir() else declared
    if (not file.is_file() or file.is_symlink() or
        file.name != target_name):
        raise ValueError(
            "Expected a source folder containing "+target_name+
            " or the file itself; got "+str(declared))
    if file.stat().st_size > 2*1024*1024*1024:
        raise ValueError("Original file exceeds 2 GiB local limit: "+target_name)
    return file


def _copy(stage: Path, target_name: str, file: Path,
          receipts: dict[str, dict]) -> None:
    if target_name in receipts:
        raise ValueError("Duplicate research source target: "+target_name)
    shutil.copyfile(file, stage/target_name)
    digest=file_sha256(file)
    if file_sha256(stage/target_name) != digest:
        raise RuntimeError("Source integrity failed while copying "+target_name)
    receipts[target_name] = {
        "original_local_path":str(file.absolute()),
        "sha256":digest,
        "size_bytes":file.stat().st_size,
        "locally_copied_verbatim":True,
        "independently_reviewed":False,
    }


def assemble(source_options: dict[str, str | None],
             config_path: str | Path,
             output_dir: str | Path) -> dict:
    """Assemble exact source files without overwrite, synthesis or imputation.

    Metadata next to a specific source is copied if it exists; source review
    declarations are copied only if explicitly supplied. No reviewer status
    is granted by these operations.
    """
    destination=Path(output_dir).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Research dataset output exists; choose a new versioned path")
    config=ExperimentConfig(**json.loads(Path(config_path).read_text()))
    cfg_path=Path(config_path).expanduser()
    if not cfg_path.is_file() or cfg_path.is_symlink():
        raise ValueError("An existing regular frozen study configuration is required")
    requested={
        name:value for name,value in source_options.items()
        if name in STANDARD and value is not None
    }
    if not set(("prices.csv","membership.csv","benchmark.csv")).issubset(requested):
        raise ValueError("Assembly requires original prices, membership, and benchmark sources")
    # Resolve and validate all required paths before creating any artifact.
    sources={name:read_input(path,name) for name,path in requested.items()}
    extras={}
    for name,src in sources.items():
        for receipt_name in METADATA.get(name,()):
            candidate=src.parent/receipt_name
            if candidate.is_symlink():
                raise ValueError("Refusing unsafe source provenance symlink: "+str(candidate))
            if candidate.is_file():
                if receipt_name in extras:
                    raise ValueError("Conflicting source receipt: "+receipt_name)
                extras[receipt_name]=candidate
    review=source_options.get("EVIDENCE_REVIEW.json")
    if review:
        extras["EVIDENCE_REVIEW.json"]=read_input(review,"EVIDENCE_REVIEW.json")
    pit=source_options.get("PIT_MEMBERSHIP_PROVENANCE.json")
    if pit:
        extras["PIT_MEMBERSHIP_PROVENANCE.json"]=read_input(
            pit,"PIT_MEMBERSHIP_PROVENANCE.json")
    # Preserve all source fixture markers. It is unsafe to make a synthetic
    # dataset look like a legitimate observed index by copying only its CSVs.
    synthetic_markers=[
        src.parent/"DO_NOT_CITE.txt" for src in sources.values()
        if (src.parent/"DO_NOT_CITE.txt").is_file()
    ]
    if synthetic_markers and any(p.is_symlink() for p in synthetic_markers):
        raise ValueError("Refusing symlinked synthetic marker")
    destination.parent.mkdir(parents=True,exist_ok=True)
    receipts={}
    with tempfile.TemporaryDirectory(prefix=".quantlab_source_",dir=destination.parent) as root:
        stage=Path(root)/"dataset"
        stage.mkdir()
        for name,source in sorted({**sources,**extras}.items()):
            _copy(stage,name,source,receipts)
        if synthetic_markers:
            _copy(stage,"DO_NOT_CITE.txt",synthetic_markers[0],receipts)
        _copy(stage,"FROZEN_CONFIG.json",cfg_path,receipts)
        try:
            prices,members,benchmark,fundamentals=load_research_inputs(stage)
        except (ValueError,OSError,KeyError) as exc:
            raise ValueError("Core research source mismatch; NO dataset was committed: "+str(exc)) from exc
        if prices.index.min().day==1 and prices.index.to_period("M").nunique()>1:
            raise ValueError(
                "Research prices are first-day-labeled monthly data. "
                "Do not guess observation or rebalance times; use original "
                "dated session closes before calendar-align. NO dataset committed.")
        preflight=research_preflight(stage,config)
        status={
            "kind":"verbatim_immutable_research_input_assembly",
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "source_files":receipts,
            "rows":len(prices),
            "securities":len(prices.columns),
            "membership_observed_states":int(members.to_numpy(dtype=bool).sum()),
            "benchmark_months":len(benchmark),
            "first_observation":prices.index[0].date().isoformat(),
            "last_observation":prices.index[-1].date().isoformat(),
            "software_preflight":preflight,
            "source_licenses_automatically_approved":False,
            "independent_market_data_certification":False,
            "frozen_config_sha256":file_sha256(stage/"FROZEN_CONFIG.json"),
            "warning":"Source file presence and reproducibility do not prove "
                      "NIFTY point-in-time membership, total returns, filing "
                      "vintages, corporate actions, or licensing.",
        }
        (stage/"SOURCE_ASSEMBLY.json").write_text(
            json.dumps(status,indent=2,allow_nan=False)+"\n")
        # Atomic publish of a validated private data folder.
        os.replace(stage,destination)
    return {
        "dataset":str(destination),
        "software_ready":preflight["software_ready"],
        "dataset_kind":preflight["classification"],
        "missing_software_inputs":preflight["configuration_blockers"]+
                                  preflight["missing_core_files"],
        "external_evidence_blockers":preflight["external_evidence_blockers"],
        "frozen_config":str(destination/"FROZEN_CONFIG.json"),
        "independent_research_certified":False,
    }


def _next_steps(data: Path, config: Path, status: dict) -> str:
    missing=set(status["missing_sources"])
    blocked=status["preflight"]["software_blockers"]
    review=status["preflight"]["external_evidence_blockers"]
    steps=[
        "# QuantLab — Exact Remaining Actions",
        "**Nothing here is independently verified solely because a file exists.**",
        "## Data currently inspected",
        "Local dataset: `"+str(data)+"`",
        "Frozen config: `"+str(config)+"`",
        "Current classification: **"+status["classification"]+"**.",
        "## Step 1 — Collect only the missing original sources",
    ]
    if "prices.csv" in missing:
        steps.append(
            "- Obtain Dhan historical DAILY prices for every historically "
            "eligible security, including removed/delisted identities. "
            "A monthly price-only archive is not dividend-adjusted research wealth.")
    if "membership.csv" in missing:
        steps.append(
            "- Import and independently reconcile effective-dated original "
            "NIFTY membership notices; a present-day 50-member list is NOT valid.")
    if "benchmark.csv" in missing or "BENCHMARK_SOURCE.json" in missing:
        steps.append(
            "- Export authentic NIFTY 50 TRI index LEVELS from "
            "https://www.niftyindices.com/reports/historical-data, "
            "including a preceding monthly close. Then run the documented "
            "`benchmark` preparation command (specify its ACTUAL source headers).")
    for file in ("corporate_actions.csv","RETURN_METHODOLOGY.json",
                 "PIT_MEMBERSHIP_PROVENANCE.json"):
        if file in missing:
            steps.append("- Resolve `"+file+"` from original records; "
                         "do not fill unknown payout or ticker events with zero.")
    if "fundamentals.csv" in missing:
        steps.append(
            "- Supply first-published filing vintages, true period "
            "capitalizations and a documented factor definition; normalize "
            "them with `prepare_research_data.py fundamentals`.")
    for file in ("sectors.csv","benchmark_weights.csv","factor_returns.csv",
                 "liquidity.csv"):
        if file in missing:
            steps.append(
                "- `"+file+"`: obtain verified effective-dated source "
                "records only if the selected model requires this input.")
    if not missing:
        steps.append("- All required filenames exist, but content still "
                     "requires independent source verification.")
    if blocked:
        steps.extend(["## Step 2 — Repair software/preflight blockers",*("- "+v for v in blocked)])
    else:
        steps.append("## Step 2 — Software preflight currently passes")
    steps.extend([
        "## Step 3 — Original-source, license, hypothesis and holdout review",
        "NSE's current academic-only data access application is at "
        "https://www.nseindia.com/static/research/initiatives-data-for-research.",
        "The application requires the Data Seeking Request Form sent to "
        "nseri@nse.co.in and does not itself grant permission.",
        *("- "+v for v in review),
        "Obtain original rights to use derived index results and complete "
        "the original-source review with a named independent reviewer.",
        "## Step 4 — Rebuild a NEW immutable dataset folder (no overwrite)",
        "Run `python scripts/quantlab_finish.py assemble --help` to "
        "combine observed stock wealth, PIT events, TRI, filings, sectors, "
        "and optional factor/capacity sources into a source-hashed package.",
        "## Step 5 — Run the three studies only on complete sourced data",
        "Run only after the source data and methodology preflight pass. "
        "Do not use --execute while the report is BLOCKED.",
        "\n".join([
            "```bash",
            "python scripts/quantlab_finish.py doctor \\",
            "  --data-dir "+shell_quote(str(data))+" \\",
            "  --config "+shell_quote(str(config))+" \\",
            "  --output-dir results/research_release_new --execute",
            "```",
        ]),
        "The three-study runner produces descriptive calculations only. "
        "It never auto-certifies source truth, profitability or publication rights.",
        "## Step 6 — Independent reproduction and research paper",
        "Have another researcher run the frozen source and config hashes; "
        "check period and factor attribution against the original NSE exports. "
        "After review, use RESEARCH_PAPER_DRAFT.md for a truthful final paper.",
    ])
    return "\n\n".join(steps)+"\n"


def doctor(data_dir: str | Path, config_path: str | Path,
           output_dir: str | Path, *, execute: bool=False) -> dict:
    """Report exact missing evidence, optional three studies, and next commands."""
    data=Path(data_dir).expanduser()
    config=Path(config_path).expanduser()
    out=Path(output_dir).expanduser()
    if out.exists():
        raise FileExistsError("Release report exists; choose a new immutable output directory")
    result=generate(data,config,out,execute=execute)
    status=json.loads((out/"RESEARCH_RELEASE_STATUS.json").read_text())
    (out/"NEXT_ACTIONS.md").write_text(_next_steps(data,config,status))
    return {
        **result,
        "actions_file":str(out/"NEXT_ACTIONS.md"),
        "research_complete":False,
        "independently_certified":False,
        "warning":"A software-ready run is not an externally reviewed empirical study.",
    }


def legacy_audit(source: str | Path, output_dir: str | Path) -> dict:
    """Audit tracked legacy static-universe prices without inventing PIT/TRI."""
    src=Path(source).expanduser()
    if src.is_symlink() or not src.is_file():
        raise ValueError("An actual legacy CSV file (not symlink) is required")
    out=Path(output_dir).expanduser()
    if out.exists():
        raise FileExistsError("Choose a new immutable archive audit folder")
    raw=pd.read_csv(src)
    if len(raw.columns)<2 or raw.columns[0].lower() not in {"date","datetime"}:
        raise ValueError("Historical price archive must have first date column")
    dates=pd.to_datetime(raw.iloc[:,0],errors="raise")
    values=raw.iloc[:,1:].apply(pd.to_numeric,errors="coerce")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Price labels must be valid unique increasing dates")
    if values.columns.has_duplicates:
        raise ValueError("Historical securities must be unique")
    missing=int(values.isna().to_numpy().sum())
    invalid=int((values.le(0)&values.notna()).to_numpy().sum())
    dates_unique=int(dates.dt.to_period("M").nunique())
    first_day=int((dates.dt.day==1).sum())
    per_stock=[
        {"ticker":str(name),"observed_months":int(column.notna().sum()),
         "missing_months":int(column.isna().sum())}
        for name,column in values.items()
    ]
    result={
        "archive_file_name":src.name,"archive_sha256":file_sha256(src),
        "date_min":dates.min().date().isoformat(),
        "date_max":dates.max().date().isoformat(),
        "months":len(raw),"distinct_calendar_months":dates_unique,
        "security_columns":len(values.columns),
        "missing_price_cells":missing,
        "non_positive_observed_cells":invalid,
        "first_of_month_date_labels":first_day,
        "historical_PIT_membership_source_in_archive":False,
        "trading_session_timestamp_verified":False,
        "dividend_reinvestment_verified":False,
        "delistings_and_recovery_verified":False,
        "source_vintage_financials_verified":False,
        "nifty_tri_benchmark_verified":False,
        "independent_research_certified":False,
        "limitations":[
            "Static ticker columns include securities that were not necessarily "
            "historical NIFTY members or even publicly traded at the time.",
            "Month-start date labels may reflect start-of-month group keys, "
            "not the true observed market session or formation timestamp.",
            "Missing cells cannot be filled with zeros or backfilled "
            "without original exchange evidence.",
            "Historical raw CSV should not be used as a total-return PIT "
            "investment study or recruiter alpha claim.",
        ],
    }
    out.mkdir(parents=True)
    (out/"LEGACY_ARCHIVE_STATUS.json").write_text(
        json.dumps(result,indent=2,allow_nan=False)+"\n")
    pd.DataFrame(per_stock).sort_values(
        ["missing_months","ticker"],ascending=[False,True]).to_csv(
            out/"LEGACY_SECURITY_COVERAGE.csv",index=False)
    (out/"LEGACY_RESEARCH_WARNING.md").write_text(
        "# Legacy historical price archive — UNVERIFIED\n\n"
        f"Observed {len(raw)} monthly rows, {len(values.columns)} static stock "
        f"columns, {missing} missing price cells. "
        f"{first_day} monthly labels are first-of-month.\n\n"
        "This is **not** a point-in-time total-return NIFTY 50 study. "
        "Do not relabel as an independently verified backtest; obtain "
        "original trading-session, membership, corporate-action, filing "
        "and benchmark records before publishing empirical findings.\n"
    )
    return result


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    assembly=sub.add_parser("assemble",help="Build immutable research dataset from supplied primary-source stages")
    for flag in ("prices","membership","benchmark"):
        assembly.add_argument("--"+flag,required=True,
            help="Folder containing "+flag+".csv or the exact file path")
    for flag in ("fundamentals","sectors","corporate-actions",
                 "benchmark-weights","factor-returns","liquidity",
                 "evidence-review","pit-provenance"):
        assembly.add_argument("--"+flag)
    assembly.add_argument("--config",required=True)
    assembly.add_argument("--output-dir",required=True)
    diagnostics=sub.add_parser("doctor",help="Write all missing sources, commands and optionally run studies")
    diagnostics.add_argument("--data-dir",default="data/research_v1")
    diagnostics.add_argument("--config",default="config/research_multifactor.json")
    diagnostics.add_argument("--output-dir",required=True)
    diagnostics.add_argument("--execute",action="store_true",
                             help="Run source-gated three-study calculations, not independent validation")
    legacy=sub.add_parser("legacy-audit",help="Inventory old static-universe prices without certifying them")
    legacy.add_argument("--source",default="nifty50_prices_monthly.csv")
    legacy.add_argument("--output-dir",required=True)
    args=p.parse_args(argv)
    try:
        if args.command=="assemble":
            fields={
                "prices.csv":args.prices,
                "membership.csv":args.membership,
                "benchmark.csv":args.benchmark,
                "fundamentals.csv":args.fundamentals,
                "sectors.csv":args.sectors,
                "corporate_actions.csv":args.corporate_actions,
                "benchmark_weights.csv":args.benchmark_weights,
                "factor_returns.csv":args.factor_returns,
                "liquidity.csv":args.liquidity,
                "EVIDENCE_REVIEW.json":args.evidence_review,
                "PIT_MEMBERSHIP_PROVENANCE.json":args.pit_provenance,
            }
            outcome=assemble(fields,args.config,args.output_dir)
        elif args.command=="doctor":
            outcome=doctor(args.data_dir,args.config,args.output_dir,
                           execute=args.execute)
        else:
            outcome=legacy_audit(args.source,args.output_dir)
        print(json.dumps(outcome,indent=2,allow_nan=False))
        if args.command=="doctor" and not outcome["software_ready"]:
            return 2
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print("QuantLab research handoff blocked: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
