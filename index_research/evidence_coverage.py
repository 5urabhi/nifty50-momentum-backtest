"""Exact per-security empirical data coverage and actionable research blockers.

This module does not download licensed exchange files, reconstruct nonexistent
delisting proceeds or treat missing rows as zero. It quantifies precisely
which observed security-months prevent a defensible historical study.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from math import ceil

import numpy as np
import pandas as pd

from .data import (asof_fundamentals, read_fundamentals, read_matrix,
                   read_membership, read_returns)


def _digest(file: Path) -> str:
    hash=hashlib.sha256()
    with file.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            hash.update(chunk)
    return hash.hexdigest()


def inspect_empirical_coverage(data_dir: str | Path,
                               config: dict | None = None) -> dict:
    """Audit stock coverage against available PIT states and dated benchmark.

    The original data directory is never altered. Missing or stale source
    evidence remains a blocker even if all numeric cells appear complete.
    """
    root=Path(data_dir).expanduser().resolve()
    src=root/"prices.csv"
    if src.is_symlink() or not src.is_file():
        raise ValueError("A source prices.csv file is needed for security-month coverage")
    price=read_matrix(src,positive=True)
    dates=price.index
    labels=dates.to_period("M").to_timestamp("M")
    months=labels.to_period("M")
    expected=pd.period_range(months[0],months[-1],freq="M")
    absent_months=expected.difference(months)
    active=None
    member_file=root/"membership.csv"
    member_error=None
    if member_file.is_file() and not member_file.is_symlink():
        try:
            active=read_membership(member_file,dates,price.columns)
        except (ValueError, KeyError, OSError) as e:
            member_error=str(e)
    else:
        member_error="Original historical membership.csv is missing"
    if active is not None:
        observed=price.notna()&(price>0)&np.isfinite(price)
        missing=active&(~observed)
        returns=price.shift(-1).div(price).sub(1)
        forward_missing=(active&(~np.isfinite(returns))).iloc[:-1]
        opportunities=int(active.to_numpy().sum())
        missing_count=int(missing.to_numpy().sum())
        forward_count=int(forward_missing.to_numpy().sum())
        missing_rows=[
            {"date":str(d.date()),"ticker":t,"problem":"eligible_price_unavailable"}
            for d,t in zip(*np.where(missing.to_numpy()))
        ]
        # The vectorized positions returned above are integer row/column
        # indices, not date or ticker strings.
        missing_rows=[
            {"date":str(dates[int(i)].date()),"ticker":str(price.columns[int(j)]),
             "problem":"eligible_price_unavailable"}
            for i,j in zip(*np.where(missing.to_numpy()))
        ]
        missing_rows.extend({
            "date":str(dates[int(i)].date()),"ticker":str(price.columns[int(j)]),
            "problem":"eligible_next_month_total_return_unavailable"
        } for i,j in zip(*np.where(forward_missing.to_numpy())))
    else:
        opportunities=missing_count=forward_count=None
        missing_rows=[]
    benchmark=root/"benchmark.csv"
    benchmark_status="missing"
    benchmark_months_missing=[]
    if benchmark.is_file() and not benchmark.is_symlink():
        try:
            series=read_returns(benchmark)
            if series.index.equals(labels):
                benchmark_status="calendar_matched"
            elif series.index.to_period("M").equals(labels.to_period("M")):
                benchmark_status="same_month_different_label_use_calendar_align"
            else:
                benchmark_status="missing_or_extra_months"
                benchmark_months_missing=[
                    str(x.date()) for x in labels.difference(series.index)[:24]]
        except (ValueError,OSError) as e:
            benchmark_status="invalid: "+str(e)
    models=config or {}
    validation=models.get("validation_start")
    final=models.get("final_test_start")
    train_months=(int((labels<pd.Timestamp(validation)).sum())
                  if validation else None)
    final_months=(int((labels>=pd.Timestamp(final)).sum())-1
                  if final else None)
    minimum_training=36
    preferred_training=ceil(minimum_training*1.2)
    factor_source=root/"fundamentals.csv"
    factor_status={}
    factor_error=None
    selected=[key for key,weight in (models.get("factor_weights") or {}).items()
              if float(weight)>0 and key in {"value","quality","size","yield"}]
    if selected:
        if not factor_source.is_file() or factor_source.is_symlink():
            factor_error="Missing publication-dated fundamentals.csv"
        elif active is None:
            factor_error="Cannot audit as-of factor coverage without historical member states"
        else:
            try:
                fundamentals=read_fundamentals(factor_source)
                for factor in selected:
                    sufficient=0
                    eligible=0
                    for i,date in enumerate(dates[:-1]):
                        names=price.columns[active.iloc[i]]
                        if len(names)==0:
                            continue
                        observed=asof_fundamentals(fundamentals,date,names)
                        eligible+=len(names)
                        sufficient+=int(observed[factor].notna().sum())
                    factor_status[factor]={
                        "eligible_decision_security_months":eligible,
                        "as_published_values_available":sufficient,
                        "as_published_coverage_ratio":sufficient/eligible if eligible else None,
                    }
            except (ValueError,KeyError,OSError) as exc:
                factor_error=str(exc)
    warnings=[]
    if member_error:
        warnings.append("PIT eligibility cannot be audited: "+member_error)
    if absent_months.size:
        warnings.append("Entire research months are missing; no imputation is permitted")
    if missing_count:
        warnings.append("Eligible securities lack observed prices in historical months")
    if forward_count:
        warnings.append("Eligible securities lack next-period observed total returns, "
                        "possibly including historical exits/delistings")
    if benchmark_status!="calendar_matched":
        warnings.append("Benchmark is unavailable, invalid, or not on the same calendar; "
                        "source official NIFTY 50 TRI with one prior monthly level")
    if factor_error:
        warnings.append("Publication-time factor coverage: "+factor_error)
    if train_months is not None and train_months<preferred_training:
        warnings.append("Pre-validation minimum 36 months, preferred >=44 "
                        "for a 20% estimation/diagnostic buffer")
    if final_months is not None and final_months<12:
        warnings.append("At least 12 complete untouched final-test returns are required")
    if (root/"DO_NOT_CITE.txt").exists():
        warnings.append("Fixture contains SYNTHETIC observations, not historical NSE evidence")
    if not (root/"BENCHMARK_SOURCE.json").is_file():
        warnings.append("Official TRI source checksum/convention is not documented")
    pit_file=root/"PIT_MEMBERSHIP_PROVENANCE.json"
    pit_missing=[]
    if pit_file.is_file() and not pit_file.is_symlink():
        try:
            pit=json.loads(pit_file.read_text())
            pit_missing=pit.get("missing_historical_symbols",[]) or []
            if not isinstance(pit_missing,list):
                pit_missing=[]
        except (ValueError,OSError):
            warnings.append("PIT provenance is malformed")
    if pit_missing:
        warnings.append("Historical source contains unresolved delisted/renamed tickers")
    return {
        "kind":"empirical_source_coverage_not_financial_certification",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source_prices_sha256":_digest(src),
        "source_membership_sha256":_digest(member_file) if active is not None else None,
        "price_observations":len(dates),
        "securities_in_observed_panel":len(price.columns),
        "first_observed_date":str(dates[0].date()),
        "last_observed_date":str(dates[-1].date()),
        "first_calendar_month":str(labels[0].date()),
        "last_calendar_month":str(labels[-1].date()),
        "missing_entire_months":[str(p) for p in absent_months],
        "eligible_security_months":opportunities,
        "missing_eligible_prices":missing_count,
        "missing_eligible_forward_returns":forward_count,
        "missing_security_observation_rows":missing_rows,
        "PIT_status":"available_internal_only" if active is not None else member_error,
        "unresolved_historical_symbols":pit_missing,
        "benchmark_alignment":benchmark_status,
        "missing_benchmark_calendar_months":benchmark_months_missing,
        "factor_coverage":factor_status,
        "factor_error":factor_error,
        "minimum_prevalidation_months":minimum_training,
        "preferred_prevalidation_months_with_20_percent_buffer":preferred_training,
        "observed_prevalidation_months":train_months,
        "observed_final_test_months":final_months,
        "warnings":warnings,
        "historical_investability_certified":False,
        "independent_source_audit":False,
        "scope":"Structural data coverage; not original source, index weight, "
                "corporate event, license or execution certification",
    }


def export_empirical_coverage(data_dir: str | Path, output_dir: str | Path,
                              config: dict | None = None) -> dict:
    """Write a new, immutable per-security missing-data remediation pack."""
    out=Path(output_dir).expanduser()
    if out.exists():
        raise FileExistsError("Coverage reports are immutable; choose a new folder")
    report=inspect_empirical_coverage(data_dir,config)
    out.mkdir(parents=True)
    missing=report.pop("missing_security_observation_rows")
    rows=pd.DataFrame(missing,columns=["date","ticker","problem"])
    rows.to_csv(out/"MISSING_SECURITY_MONTHS.csv",index=False)
    (out/"SOURCE_COVERAGE.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    md=[
        "# QuantLab — Original Evidence and Coverage Remediation",
        "Source-dependent coverage assessment. No original NSE records were "
        "invented or independently certified.",
        "## Observed source extent",
        "Price security panel: "+str(report["securities_in_observed_panel"]),
        "Observed months: "+str(report["price_observations"]),
        "Missing eligible security price months: "+str(report["missing_eligible_prices"]),
        "Missing eligible forward-return observations: "+str(report["missing_eligible_forward_returns"]),
        "PIT status: "+str(report["PIT_status"]),
        "Benchmark calendar: "+report["benchmark_alignment"],
        "Pre-validation observed months: "+str(report["observed_prevalidation_months"]),
        "Preferred minimum (+20% estimation/diagnostic buffer): "+
            str(report["preferred_prevalidation_months_with_20_percent_buffer"]),
        "## Required source actions",
        *("- "+warning for warning in report["warnings"]),
        "The detailed MISSING_SECURITY_MONTHS.csv lists missing original "
        "security-period observations only, not invented prices.",
        "## Reviewer requirements",
        "Source notice review, original listing and rename identities, dividend "
        "payoff, delisting recovery, first-publication financial statements, "
        "official total-return benchmark and execution cost evidence.",
        "No source file is redistributed by this report, and an apparently "
        "complete matrix does not imply independent correctness.",
    ]
    (out/"SOURCE_REMEDIATION.md").write_text("\n\n".join(md)+"\n")
    return {"folder":str(out),"missing_observations":len(missing),
            "publication_certified":False}
