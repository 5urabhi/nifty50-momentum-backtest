"""Reconcile observed market-session month marks with calendar-month TRI labels.

A date label is NOT a fabricated price. The last actually observed Dhan close
remains unchanged; only its monthly research key changes. Historical membership
is sampled at the ORIGINAL observed close, before relabeling, so an index
change after that close cannot enter the backtest early.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil

import pandas as pd

from .data import read_matrix, read_membership, read_returns


def _sha(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def align_research_calendar(source_dir: str | Path,
                            output_dir: str | Path,
                            benchmark_csv: str | Path | None = None,
                            *, max_staleness_days: int = 10,
                            membership_csv: str | Path | None = None,
                            observed_session_map: str | Path | None = None) -> dict:
    """Create an immutable, calendar-month-end research data view.

    Source must have (i) historical month-close observations from actual
    trading sessions and (ii) effective-dated membership events. A separately
    supplied NIFTY total-return benchmark must cover EXACTLY the modeled
    months, including the first row's genuine reference return.
    No benchmark is fabricated if not supplied, and no source files change.
    """
    root=Path(source_dir).expanduser().resolve()
    out=Path(output_dir).expanduser().resolve()
    if out.exists():
        raise FileExistsError("Choose a new output directory; historical data views are immutable")
    if not 0<=max_staleness_days<=15:
        raise ValueError("max_staleness_days must be between zero and fifteen")
    original=root/"prices.csv"
    eligibility_file=(Path(membership_csv).expanduser()
                      if membership_csv is not None else root/"membership.csv")
    if any(x.is_symlink() or not x.is_file() for x in (original,eligibility_file)):
        raise ValueError("Observed prices.csv and historical membership.csv are required")
    prices=read_matrix(original,positive=True)
    dated=prices.index
    session_path=(Path(observed_session_map).expanduser()
                  if observed_session_map is not None else root/"OBSERVED_MARKET_SESSIONS.csv")
    if not isinstance(dated,pd.DatetimeIndex):
        raise ValueError("Prices need source-observed date stamps")
    calendar=dated.to_period("M").to_timestamp("M")
    if calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError("Duplicate/reordered observed months; cannot infer a monthly close")
    expected=pd.period_range(calendar[0].to_period("M"),calendar[-1].to_period("M"),freq="M")
    if not expected.equals(calendar.to_period("M")):
        raise ValueError("An entire price month is missing; supply original data rather than filling it")
    observed_session=dated
    if session_path.exists():
        if session_path.is_symlink() or not session_path.is_file():
            raise ValueError("Invalid observed-session source map")
        frame=pd.read_csv(session_path)
        if not {"calendar_month_end","observed_market_session"}.issubset(frame.columns):
            raise ValueError("Session map needs calendar_month_end,observed_market_session")
        frame=frame[["calendar_month_end","observed_market_session"]].copy()
        frame["calendar_month_end"]=pd.to_datetime(
            frame["calendar_month_end"],errors="raise")
        frame["observed_market_session"]=pd.to_datetime(
            frame["observed_market_session"],errors="raise")
        if (frame.isna().any().any() or
            frame["calendar_month_end"].duplicated().any() or
            not pd.DatetimeIndex(frame["calendar_month_end"]).equals(calendar)):
            raise ValueError("Session map must cover the exact research price months")
        observed_session=pd.DatetimeIndex(frame["observed_market_session"])
        if not observed_session.is_monotonic_increasing or observed_session.has_duplicates:
            raise ValueError("Observed session dates must increase strictly")
        if not observed_session.to_period("M").equals(calendar.to_period("M")):
            raise ValueError("Observed sessions must fall in the corresponding price months")
    elif ((dated==calendar)&(dated.dayofweek>=5)).any():
        raise ValueError("Weekend month-end price labels require actual "
                         "OBSERVED_MARKET_SESSIONS.csv, not presumed trading dates")
    staleness=(calendar-observed_session).days
    if (staleness<0).any() or (staleness>max_staleness_days).any():
        raise ValueError("Observed month-end close is stale or after calendar end")
    membership=read_membership(eligibility_file,observed_session,prices.columns)
    labeled_prices=prices.copy()
    labeled_prices.index=calendar
    snapshots=membership.copy()
    snapshots.index=pd.DatetimeIndex(calendar,name="date")
    snapshots.columns=pd.Index(snapshots.columns,name="ticker")
    if benchmark_csv is None:
        benchmark_path=root/"benchmark.csv"
    else:
        benchmark_path=Path(benchmark_csv).expanduser().resolve()
    has_benchmark=benchmark_path.is_file() and not benchmark_path.is_symlink()
    if benchmark_csv is not None and not has_benchmark:
        raise ValueError("Provided benchmark file is unavailable or unsafe")
    benchmark=None
    if has_benchmark:
        benchmark=read_returns(benchmark_path)
        if not benchmark.index.equals(calendar):
            absent=sorted(set(calendar)-set(benchmark.index))
            unexpected=sorted(set(benchmark.index)-set(calendar))
            raise ValueError(
                "Actual TRI monthly returns do not align with observed stock months; "
                "source TRI levels must begin one month EARLIER than the first "
                "stock research month. Missing="+str([str(d.date()) for d in absent[:12]])+
                "; unexpected="+str([str(d.date()) for d in unexpected[:12]]))
    out.mkdir(parents=True)
    labeled_prices.to_csv(out/"prices.csv",index_label="date",float_format="%.12g")
    snapshots.stack(future_stack=True).rename("eligible").reset_index().to_csv(
        out/"membership.csv",index=False)
    if benchmark is not None:
        shutil.copyfile(benchmark_path,out/"benchmark.csv")
    for original_dir,receipt in (
        (root,"RETURN_METHODOLOGY.json"),
        (eligibility_file.parent,"PIT_MEMBERSHIP_PROVENANCE.json"),
        (benchmark_path.parent,"BENCHMARK_SOURCE.json"),
    ):
        candidate=original_dir/receipt
        if candidate.is_symlink():
            raise ValueError("Refusing source metadata symlink: "+str(candidate))
        if candidate.is_file():
            shutil.copyfile(candidate,out/receipt)
    observed=pd.DataFrame({
        "calendar_month_end":calendar,
        "observed_market_session":observed_session,
        "calendar_days_between":staleness,
    })
    observed.to_csv(out/"OBSERVED_MARKET_SESSIONS.csv",index=False)
    provenance={
        "kind":"source_preserving_calendar_month_alignment",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source_prices_sha256":_sha(original),
        "source_membership_sha256":_sha(eligibility_file),
        "source_observed_market_session_sha256":_sha(session_path)
             if session_path.is_file() else None,
        "source_benchmark_sha256":_sha(benchmark_path) if has_benchmark else None,
        "source_months":len(prices),
        "source_securities":len(prices.columns),
        "original_first_formation":str(observed_session[0].date()),
        "original_last_formation":str(observed_session[-1].date()),
        "canonical_first_month":str(calendar[0].date()),
        "canonical_last_month":str(calendar[-1].date()),
        "max_observed_calendar_lag_days":int(max(staleness)),
        "benchmark_available":bool(has_benchmark),
        "benchmark_has_original_previous_month_close":"requires separate source review",
        "label_policy":"Calendar month-end labels from LAST ACTUALLY OBSERVED market close; no price forward-fill",
        "eligibility_policy":"Eligibility sampled at original observed close, not after-close month-end events",
        "source_license_reviewed":False,
        "externally_certified":False,
        "warning":"Calendar alignment does NOT validate original TRI, adjusted security prices, "
                  "historical index membership, missing delisted securities or investment returns.",
    }
    (out/"CALENDAR_ALIGNMENT_PROVENANCE.json").write_text(
        json.dumps(provenance,indent=2,allow_nan=False)+"\n")
    return {"path":str(out),"months":len(calendar),
            "securities":len(prices.columns),
            "benchmark_available":bool(has_benchmark),
            "source_review_required":True,
            "observation_date_mapping":"OBSERVED_MARKET_SESSIONS.csv",
            "publication_certified":False}
