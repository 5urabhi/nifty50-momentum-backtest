"""Strict, provenance-aware local CSV ingestion for index research."""
from pathlib import Path
import pandas as pd
import numpy as np

def read_matrix(path: str | Path, *, positive: bool = False) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if len(frame.columns) < 2:
        raise ValueError(f"{path}: expected date and at least one security column")
    dates = pd.to_datetime(frame.iloc[:, 0], errors="raise")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError(f"{path}: dates must be unique, valid and increasing")
    values = frame.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    if values.columns.has_duplicates or len(values) < 2:
        raise ValueError(f"{path}: at least two rows and unique columns required")
    values.index = pd.DatetimeIndex(dates)
    if positive and (values.le(0) & values.notna()).any().any():
        raise ValueError(f"{path}: prices must be positive")
    if np.isinf(values.to_numpy()).any():
        raise ValueError(f"{path}: infinite values forbidden")
    return values.astype(float)


def read_returns(path: str | Path) -> pd.Series:
    frame = pd.read_csv(path)
    if len(frame.columns) != 2:
        raise ValueError("benchmark CSV must contain exactly date,return columns")
    dates = pd.to_datetime(frame.iloc[:, 0], errors="raise")
    values = pd.to_numeric(frame.iloc[:, 1], errors="raise")
    if dates.duplicated().any() or not dates.is_monotonic_increasing or dates.isna().any():
        raise ValueError("benchmark dates must be increasing, unique and valid")
    if values.isna().any() or (~np.isfinite(values)).any() or (values <= -1).any():
        raise ValueError("benchmark returns must be finite decimals above -100%")
    return pd.Series(values.to_numpy(dtype=float), index=pd.DatetimeIndex(dates), name="benchmark")


def read_membership(path: str | Path, dates: pd.DatetimeIndex,
                    tickers: pd.Index) -> pd.DataFrame:
    """Date-effective membership events: date,ticker,eligible.

    Every ticker must have an observation ON OR BEFORE the first decision date.
    Snapshots represent verified as-of membership evidence, not historical
    reconstruction from today's index. Forward-fill is for persistent *state*
    transitions only, never missing prices or financial data.
    """
    frame = pd.read_csv(path)
    required = {"date", "ticker", "eligible"}
    if not required.issubset(frame.columns):
        raise ValueError("membership CSV requires date,ticker,eligible")
    frame = frame[["date", "ticker", "eligible"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame["date"].isna().any() or frame[["date", "ticker"]].duplicated().any():
        raise ValueError("invalid or duplicate membership events")
    if not frame["eligible"].astype(str).str.lower().isin(["true", "false", "1", "0"]).all():
        raise ValueError("eligibility must be true/false or 1/0")
    frame["eligible"] = frame["eligible"].astype(str).str.lower().isin(["true", "1"])
    unknown = set(frame["ticker"]) - set(tickers)
    if unknown:
        raise ValueError(f"membership has unknown tickers: {sorted(unknown)}")
    wide = frame.pivot(index="date", columns="ticker", values="eligible")
    wide = wide.reindex(index=wide.index.union(dates)).sort_index().ffill().reindex(index=dates, columns=tickers)
    if wide.isna().any().any():
        raise ValueError("missing historical eligibility for one or more dates/tickers")
    return wide.astype(bool)


def read_fundamentals(path: str | Path) -> pd.DataFrame:
    """Long-form data: ticker,period_end,available_at,value,quality,size.

    available_at is first public availability, not accounting period end;
    accounting period end must not be after publication date. Factor columns
    are nullable; data are never backfilled into earlier decision dates.
    """
    f = pd.read_csv(path)
    required = {"ticker", "period_end", "available_at", "value", "quality", "size"}
    if not required.issubset(f.columns):
        raise ValueError(f"fundamentals missing columns: {sorted(required - set(f.columns))}")
    # Preserve optional, first-public-date dividend-yield evidence. Do not
    # invent a zero yield when the original source never supplied the field.
    columns=list(required)+(["yield"] if "yield" in f.columns else [])
    f = f[columns].copy()
    for col in ("period_end", "available_at"):
        f[col] = pd.to_datetime(f[col], errors="raise")
    if f[["ticker", "period_end", "available_at"]].isna().any().any():
        raise ValueError("missing fundamental identity or dates")
    if (f["period_end"] > f["available_at"]).any():
        raise ValueError("fundamentals cannot be available before period end")
    if f[["ticker", "available_at"]].duplicated().any():
        raise ValueError("duplicate as-of records")
    for col in ("value", "quality", "size", "yield"):
        if col not in f.columns:
            continue
        f[col] = pd.to_numeric(f[col], errors="coerce")
        if np.isinf(f[col].to_numpy()).any():
            raise ValueError("infinite fundamental scores")
    return f.sort_values(["available_at", "ticker"]).reset_index(drop=True)


def asof_fundamentals(records: pd.DataFrame, date: pd.Timestamp,
                      tickers: pd.Index) -> pd.DataFrame:
    """Strictly earlier availability prevents same-close publication ambiguity."""
    visible = records.loc[records["available_at"] < date].copy()
    visible = visible.sort_values(["available_at", "period_end"]).drop_duplicates("ticker", keep="last")
    return visible.set_index("ticker").reindex(tickers).reindex(
        columns=["value","quality","size","yield"])


def load_research_inputs(directory: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame | None]:
    root = Path(directory)
    prices = read_matrix(root / "prices.csv", positive=True)
    eligibility = read_membership(root / "membership.csv", prices.index, prices.columns)
    benchmark = read_returns(root / "benchmark.csv")
    if not benchmark.index.equals(prices.index):
        raise ValueError("benchmark dates must exactly match the price observations")
    file = root / "fundamentals.csv"
    fundamentals = read_fundamentals(file) if file.exists() else None
    return prices, eligibility, benchmark, fundamentals
