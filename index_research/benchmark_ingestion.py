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
