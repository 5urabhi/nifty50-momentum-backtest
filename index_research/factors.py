"""Transparent cross-sectional factor research with as-of fundamentals."""
import numpy as np
import pandas as pd
from .data import asof_fundamentals
from .core import momentum_scores


def low_volatility_scores(prices: pd.DataFrame, lookback: int = 12,
                          skip: int = 1) -> pd.DataFrame:
    if lookback < 3 or skip < 0:
        raise ValueError("lookback >= 3 and skip >= 0 required")
    rets = prices.pct_change(fill_method=None)
    # Lag every observation by skip intervals; higher scores = lower volatility.
    return -rets.shift(skip).rolling(lookback, min_periods=lookback).std(ddof=1)


def zscore_cross_section(values: pd.Series, clip: float = 3.0) -> pd.Series:
    x = pd.to_numeric(values, errors="coerce")
    finite = x.replace([np.inf, -np.inf], np.nan).dropna()
    result = pd.Series(np.nan, index=x.index, dtype=float)
    if len(finite) < 2:
        return result
    mu, std = finite.mean(), finite.std(ddof=0)
    if std <= 1e-12:
        result.loc[finite.index] = 0.0
    else:
        result.loc[finite.index] = ((finite - mu) / std).clip(-clip, clip)
    return result


def composite_scores(prices: pd.DataFrame, membership: pd.DataFrame,
                     factor_weights: dict[str, float], fundamentals: pd.DataFrame | None = None,
                     momentum_formation: int = 12, momentum_skip: int = 1,
                     volatility_lookback: int = 12) -> pd.DataFrame:
    """Compute date-specific factor scores, requiring all requested factors.

    value/quality/yield require as-published, first-available source evidence;
    yield is cash dividends per share over contemporaneous market price;
    value/quality are external vendor-defined *higher-is-better* numeric scores;
    size uses -log(positive market capitalization), favoring smaller stocks.
    These are not asserted to be proprietary MSCI factor specifications.
    """
    allowed = {"momentum", "low_volatility", "value", "quality", "size", "yield"}
    if not factor_weights or not set(factor_weights).issubset(allowed):
        raise ValueError("factor weights must name supported factors")
    if any(not np.isfinite(w) or w < 0 for w in factor_weights.values()) or sum(factor_weights.values()) <= 0:
        raise ValueError("factor weights must be finite nonnegative with positive sum")
    if any(k in factor_weights for k in ("value", "quality", "size", "yield")) and fundamentals is None:
        raise ValueError("publication-dated fundamental data required for value/quality/size")
    if not prices.index.equals(membership.index) or not prices.columns.equals(membership.columns):
        raise ValueError("prices and membership must align")
    mom = momentum_scores(prices, momentum_formation, momentum_skip) if "momentum" in factor_weights else None
    low = low_volatility_scores(prices, volatility_lookback, momentum_skip) if "low_volatility" in factor_weights else None
    result = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    weights = {name: w / sum(factor_weights.values()) for name, w in factor_weights.items() if w > 0}
    for date in prices.index:
        active = membership.loc[date].astype(bool)
        fundamentals_asof = asof_fundamentals(fundamentals, date, prices.columns) if fundamentals is not None else None
        series = []
        for name, weight in weights.items():
            if name == "momentum":
                raw = mom.loc[date]
            elif name == "low_volatility":
                raw = low.loc[date]
            elif name == "size":
                caps = fundamentals_asof["size"].where(lambda v: v > 0)
                raw = -np.log(caps)
            else:
                raw = fundamentals_asof[name]
            norm = zscore_cross_section(raw.where(active))
            series.append(norm * weight)
        # min_count enforces complete case: no silently reweighted missing factors.
        values = pd.concat(series, axis=1).sum(axis=1, min_count=len(series))
        result.loc[date] = values.where(active)
    return result


def information_coefficient(scores: pd.DataFrame, prices: pd.DataFrame,
                            membership: pd.DataFrame, min_assets: int = 5) -> pd.Series:
    """Forward one-interval cross-sectional Spearman rank IC for descriptive evaluation."""
    future = prices.shift(-1).div(prices).sub(1)
    out = {}
    for date in scores.index[:-1]:
        x = scores.loc[date].where(membership.loc[date].astype(bool))
        y = future.loc[date]
        valid = x.notna() & y.notna()
        out[prices.index[prices.index.get_loc(date)+1]] = (
            float(x[valid].corr(y[valid], method="spearman"))
            if valid.sum() >= min_assets else np.nan
        )
    return pd.Series(out, name="rank_ic")
