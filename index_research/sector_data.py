"""Publication/effective-dated sector classification records.

Sector identities can change over time. Historical matrices are generated from
effective dates and unknown classifications remain missing, never inferred
from present-day company classifications.
"""
import numpy as np
import pandas as pd


def read_sector_history(path: str) -> pd.DataFrame:
    rows = pd.read_csv(path)
    required = {"date", "ticker", "sector"}
    if not required.issubset(rows.columns):
        raise ValueError("sectors.csv requires date,ticker,sector")
    out = rows[["date", "ticker", "sector"]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="raise")
    if out["date"].isna().any() or out["ticker"].isna().any() or out["sector"].isna().any():
        raise ValueError("sector records must be complete")
    if out[["date", "ticker"]].duplicated().any():
        raise ValueError("duplicate sector effective dates")
    out["sector"] = out["sector"].astype(str).str.strip()
    if (out["sector"] == "").any():
        raise ValueError("blank sector classifications forbidden")
    return out.sort_values(["date", "ticker"]).reset_index(drop=True)


def asof_sectors(records: pd.DataFrame, decision_dates: pd.DatetimeIndex,
                 tickers: pd.Index) -> pd.DataFrame:
    """Latest sector effective on or before each decision date.

    Returns date x ticker string matrix. Missing historical classifications
    remain NA and must block constrained portfolio construction.
    """
    if records.empty:
        raise ValueError("missing sector records")
    unknown = set(records["ticker"]) - set(tickers)
    if unknown:
        raise ValueError(f"unknown tickers in sectors: {sorted(unknown)}")
    dates = pd.DatetimeIndex(decision_dates)
    pivot = records.pivot(index="date", columns="ticker", values="sector")
    wide = pivot.reindex(index=pivot.index.union(dates)).sort_index().ffill()
    return wide.reindex(index=dates, columns=tickers)


def sector_exposure(weights: pd.DataFrame, sectors: pd.DataFrame) -> pd.DataFrame:
    """Time-specific portfolio sector exposure; fail if held stock unclassified."""
    if not weights.index.equals(sectors.index) or not weights.columns.equals(sectors.columns):
        raise ValueError("weight/sector matrices must align")
    if weights.isna().any().any() or not np.isfinite(weights.to_numpy()).all():
        raise ValueError("weights must be finite")
    result = []
    for date in weights.index:
        w = weights.loc[date]
        s = sectors.loc[date]
        if s[w > 1e-12].isna().any():
            raise ValueError(f"unclassified held security at {date}")
        values = w[w > 1e-12].groupby(s[w > 1e-12]).sum()
        result.append(values.rename(date))
    return pd.DataFrame(result).fillna(0.0).reindex(weights.index).fillna(0.0)


def concentration_metrics(weights: pd.DataFrame) -> pd.DataFrame:
    """HHI, effective names, largest position and top-five weight by period."""
    if weights.isna().any().any() or (weights < -1e-10).any().any():
        raise ValueError("weights must be nonnegative and complete")
    hhi = weights.pow(2).sum(axis=1)
    top = np.sort(weights.to_numpy(dtype=float), axis=1)[:, ::-1]
    return pd.DataFrame({
        "hhi": hhi.to_numpy(),
        "effective_names": np.divide(1.0, hhi.to_numpy(),
                                      out=np.full(len(hhi), np.nan),
                                      where=hhi.to_numpy() > 0),
        "largest_weight": top[:, 0],
        "top_five_weight": top[:, :5].sum(axis=1),
        "nonzero_holdings": (weights > 1e-12).sum(axis=1).to_numpy()
    }, index=weights.index)
