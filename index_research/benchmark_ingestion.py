"""Official index level CSV import, with explicit total-return convention.

Use a lawfully downloaded NSE Indices historical Total Returns Index file.
This module does not automatically scrape NSE or imply redistribution rights.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd


def normalize_benchmark(source: str | Path, output_dir: str | Path,
                        *, date_column: str, level_column: str,
                        index_name: str, return_convention: str,
                        date_format: str | None=None) -> tuple[Path,Path]:
    if return_convention not in {"gross_total_return","net_total_return","price_return"}:
        raise ValueError("return_convention must be declared explicitly")
    if not index_name.strip():
        raise ValueError("index_name required")
    frame=pd.read_csv(source)
    if date_column not in frame or level_column not in frame:
        raise ValueError("source CSV lacks requested date/level columns")
    dates=pd.to_datetime(frame[date_column],format=date_format,errors="raise")
    level=pd.to_numeric(frame[level_column],errors="coerce")
    if dates.isna().any() or dates.duplicated().any() or level.isna().any():
        raise ValueError("invalid dates or levels")
    data=pd.DataFrame({"date":dates,"level":level})
    data=data.sort_values("date")
    if (data.level<=0).any() or not np.isfinite(data.level).all():
        raise ValueError("index levels must be finite positive")
    # Last observable trading mark in each month, no forward-filling.
    monthly=data.set_index("date")["level"].resample("ME").last().dropna()
    if len(monthly)<3:
        raise ValueError("at least three monthly index levels required")
    # The first observed index level has no preceding close. Do not invent a
    # zero return: downstream price calendars must supply the prior month.
    returns=monthly.pct_change(fill_method=None).iloc[1:]
    if returns.isna().any() or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("monthly benchmark has an unobservable return")
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    destination=out/"benchmark.csv"
    if destination.exists():
        raise FileExistsError("benchmark exists; select new output directory")
    pd.DataFrame({"date":returns.index,"return":returns.to_numpy()}).to_csv(destination,index=False)
    manifest=out/"BENCHMARK_SOURCE.json"
    manifest.write_text(json.dumps({
        "index_name":index_name,"return_convention":return_convention,
        "source_file":str(source),"date_column":date_column,"level_column":level_column,
        "first_observation":str(monthly.index.min().date()),
        "last_observation":str(monthly.index.max().date()),
        "first_return_observation":str(returns.index.min().date()),
        "return_observations":int(len(returns)),
        "source_sha256":__import__("hashlib").sha256(Path(source).read_bytes()).hexdigest(),
        "initial_level_policy":"No fabricated zero return; first CSV row requires a prior observed monthly level.",
        "warning":"Data provenance, licensed use, full coverage, trading calendar and benchmark compatibility require external validation."
    },indent=2))
    return destination,manifest


def align_benchmark_to_prices(prices_csv: str | Path,
                              benchmark_csv: str | Path) -> pd.DataFrame:
    """Strictly verify benchmark monthly calendar and return series."""
    prices=pd.read_csv(prices_csv)
    bench=pd.read_csv(benchmark_csv)
    dates=pd.to_datetime(prices.iloc[:,0],errors="raise")
    bdates=pd.to_datetime(bench["date"],errors="raise")
    if not pd.DatetimeIndex(dates).equals(pd.DatetimeIndex(bdates)):
        raise ValueError("benchmark and research prices must have exactly matching monthly dates")
    if bench["return"].isna().any() or not np.isfinite(bench["return"]).all():
        raise ValueError("benchmark incomplete")
    return bench


def align_daily_tri_to_stock_dates(
    source: str | Path,
    prices_csv: str | Path,
    output_dir: str | Path,
    *,
    date_column: str = "Date",
    level_column: str = "Total Returns Index",
    index_name: str = "NIFTY 50 TRI",
    return_convention: str = "gross_total_return",
) -> tuple[Path, Path, Path]:
    """Make monthly TRI returns at the **actual stock observation marks**.

    NSE daily TRI CSVs contain trading-session dates. Stock data can use the
    observed final trading day OR a calendar month-end *label*. Joining those
    timestamps directly to a month-end-resampled TRI incorrectly reports
    months missing (for example, 2026-01-30 != 2026-01-31).

    Rules: use an exact trading date when one is present. For an explicitly
    calendar-month-end label only, select the last *observed* TRI session in
    that month, no more than five calendar days prior. Never use an observation
    after the stock mark, interpolate, carry across missing months or invent a
    first benchmark return. Preserve every alignment choice in an audit file.
    """
    import hashlib
    import re

    if return_convention not in {"gross_total_return", "net_total_return"}:
        raise ValueError("Only original total-return index levels may be imported")
    if level_column.strip().casefold() in {"close", "open", "high", "low", "closing value"}:
        raise ValueError("A price-index OHLC column is not a verified TRI level. "
                         "Choose Total Returns Index or Net Total Return Index.")
    original = Path(source)
    prices_path = Path(prices_csv)
    frame = pd.read_csv(original)
    if date_column not in frame.columns or level_column not in frame.columns:
        raise ValueError("TRI CSV lacks the selected date/level column: "
                         + date_column + ", " + level_column)
    if frame.empty:
        raise ValueError("The TRI file contains no historical levels")
    source_dates = pd.DatetimeIndex(pd.to_datetime(frame[date_column], errors="raise"))
    source_levels = pd.to_numeric(frame[level_column], errors="coerce")
    if (source_dates.hasnans or source_dates.has_duplicates
            or source_levels.isna().any()
            or not np.isfinite(source_levels.to_numpy(dtype=float)).all()
            or (source_levels <= 0).any()):
        raise ValueError("TRI source contains duplicate dates, missing/nonpositive levels or invalid values")
    source_index_name = None
    for name_field in ("IndexName", "Index Name"):
        if name_field in frame.columns:
            unique = sorted(set(str(x).strip() for x in frame[name_field].dropna()))
            if len(unique) != 1:
                raise ValueError("TRI source mixes multiple index names; import one index at a time")
            source_index_name = unique[0]
            def canonical(x: str) -> str:
                return re.sub(r"[^a-z0-9]", "", re.sub(
                    r"\b(tri|total returns index|total return index)\b", "",
                    x.lower()))
            if canonical(source_index_name) != canonical(index_name):
                raise ValueError(
                    f"TRI file contains {source_index_name}, but dataset expects {index_name}. "
                    "Select the matching NIFTY index.")
            break

    observed = pd.Series(
        source_levels.to_numpy(dtype=float), index=source_dates, name="level"
    ).sort_index()
    rows = pd.read_csv(prices_path, usecols=["date"])
    stock_dates = pd.DatetimeIndex(pd.to_datetime(rows["date"], errors="raise"))
    if (len(stock_dates) < 2 or stock_dates.hasnans or stock_dates.has_duplicates
            or not stock_dates.is_monotonic_increasing):
        raise ValueError("Stock monthly marks must be unique, chronological and contain at least two rows")
    stock_periods = stock_dates.to_period("M")
    if stock_periods.has_duplicates:
        raise ValueError("Stock dataset contains more than one observation in a calendar month")
    complete_periods = pd.period_range(stock_periods[0], stock_periods[-1], freq="M")
    if len(complete_periods) != len(stock_periods):
        missing = complete_periods.difference(stock_periods)
        raise ValueError("Stock dataset is missing entire months: "
                         + ", ".join(str(x) for x in list(missing)[:12]))

    prior_period = stock_periods[0] - 1
    prior_observed = observed[observed.index.to_period("M") == prior_period]
    if prior_observed.empty:
        raise ValueError(
            "TRI source needs the preceding month (" + str(prior_period)
            + ") to calculate the first stock-month return. "
            "Download the original TRI levels for that month too.")
    prior_date = prior_observed.index[-1]
    if (prior_period.to_timestamp("M") - prior_date).days > 5:
        raise ValueError("Prior-month TRI source has no observed close near the end of "
                         + str(prior_period) + "; do not manufacture a baseline")
    previous_level = float(prior_observed.iloc[-1])
    previous_date = prior_date
    aligned = []
    mappings = []
    source_periods = observed.index.to_period("M")

    for label, period in zip(stock_dates, stock_periods):
        if label in observed.index:
            trading_date = label
            rule = "exact_observed_trading_date"
        elif label.is_month_end:
            in_month = observed[(source_periods == period) & (observed.index <= label)]
            if in_month.empty:
                raise ValueError("TRI source has no observed trading level for " + str(period))
            trading_date = in_month.index[-1]
            if (label - trading_date).days > 5:
                raise ValueError("The last TRI observation for " + str(period)
                                 + " is too old for its calendar-month-end label ("
                                 + str(trading_date.date()) + "). "
                                 "Obtain missing original index sessions.")
            rule = "calendar_month_end_label_to_last_observed_session"
        else:
            raise ValueError(
                "TRI source is missing the exact stock observation date "
                + str(label.date()) + " (" + str(period) + "). "
                "Do not substitute a different trading day; obtain source data for this session.")
        if trading_date <= previous_date:
            raise ValueError("TRI trading observations are not strictly increasing across the study")
        current = float(observed.loc[trading_date])
        monthly_return = current / previous_level - 1.0
        if not np.isfinite(monthly_return) or monthly_return <= -1:
            raise ValueError("Non-finite or economically impossible TRI return for " + str(period))
        aligned.append({"date": label.date().isoformat(), "return": monthly_return})
        mappings.append({
            "study_month": str(period),
            "stock_observation_label": label.date().isoformat(),
            "tri_observed_trading_date": trading_date.date().isoformat(),
            "tri_prior_observed_date": previous_date.date().isoformat(),
            "selection_rule": rule,
            "date_lag_calendar_days": int((label - trading_date).days),
        })
        previous_level = current
        previous_date = trading_date

    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    benchmark = dest / "benchmark.csv"
    receipt = dest / "BENCHMARK_SOURCE.json"
    audit = dest / "BENCHMARK_ALIGNMENT_PROVENANCE.json"
    if any(x.exists() for x in (benchmark, receipt, audit)):
        raise FileExistsError("TRI research version already contains benchmark evidence")
    pd.DataFrame(aligned).to_csv(benchmark, index=False)
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    receipt.write_text(json.dumps({
        "index_name": index_name,
        "source_index_name": source_index_name,
        "return_convention": return_convention,
        "date_column": date_column,
        "level_column": level_column,
        "source_sha256": original_hash,
        "first_observation": observed.index[0].date().isoformat(),
        "last_observation": observed.index[-1].date().isoformat(),
        "first_return_observation": stock_dates[0].date().isoformat(),
        "return_observations": len(aligned),
        "first_prior_observed_session": prior_date.date().isoformat(),
        "initial_level_policy": "Observed preceding-month TRI close only; no invented zero return.",
        "selection_policy": "Exact trading mark, or last observed in month for calendar-month-end labels only.",
        "warning": "Source provenance and licensing are NOT independently certified. "
                   "This benchmark does not validate stock dividends or constituent history.",
    }, indent=2))
    audit.write_text(json.dumps({
        "source_sha256": original_hash,
        "stock_calendar_months": len(stock_dates),
        "exact_trading_date_matches": sum(
            x["selection_rule"] == "exact_observed_trading_date" for x in mappings),
        "calendar_end_label_matches": sum(
            x["selection_rule"] == "calendar_month_end_label_to_last_observed_session"
            for x in mappings),
        "source_has_future_observations_used": False,
        "missing_months_imputed": 0,
        "alignment_rows": mappings,
        "warning": "Use of an earlier session is allowed ONLY when a stock observation is "
                   "explicitly labeled with the calendar month-end. No missing price is filled.",
    }, indent=2))
    return benchmark, receipt, audit
