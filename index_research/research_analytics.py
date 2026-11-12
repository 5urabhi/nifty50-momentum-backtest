"""Index comparison, rolling attribution, transaction-cost sensitivity and robust diagnostics.

These methods consume *existing calculated results*. They do not create or
endorse historical market performance data. The benchmark must use the same
return conventions as the research index.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd


def benchmark_comparison(strategy: pd.Series, benchmark: pd.Series,
                         turnover: pd.Series | None = None,
                         periods_per_year: int = 12) -> dict:
    """Consistently aligned realized and relative performance statistics."""
    if not strategy.index.equals(benchmark.index):
        raise ValueError("strategy and benchmark dates must match exactly")
    if len(strategy) < 12 or periods_per_year <= 0:
        raise ValueError("at least twelve complete observations required")
    a = strategy.astype(float)
    b = benchmark.astype(float)
    if a.isna().any() or b.isna().any() or (a <= -1).any() or (b <= -1).any():
        raise ValueError("returns must be complete and greater than -100%")
    if not np.isfinite(a.to_numpy()).all() or not np.isfinite(b.to_numpy()).all():
        raise ValueError("finite returns required")
    years = len(a) / periods_per_year
    active = a - b
    vol = a.std(ddof=1) * np.sqrt(periods_per_year)
    te = active.std(ddof=1) * np.sqrt(periods_per_year)
    nav = (1+a).cumprod()
    bnav = (1+b).cumprod()
    excess_wealth = nav / bnav
    downside = a.clip(upper=0).pow(2).mean() ** .5 * np.sqrt(periods_per_year)
    info = active.mean()*periods_per_year/te if te>1e-12 else np.nan
    values = {
        "observations": int(len(a)),
        "strategy_cagr": float(nav.iloc[-1]**(1/years)-1),
        "benchmark_cagr": float(bnav.iloc[-1]**(1/years)-1),
        "volatility": float(vol),
        "tracking_error": float(te),
        "information_ratio": float(info) if np.isfinite(info) else None,
        "max_drawdown": float((nav/nav.cummax()-1).min()),
        "sortino_zero_target": float(a.mean()*periods_per_year/downside) if downside>0 else None,
        "geometric_relative_cagr": float(excess_wealth.iloc[-1]**(1/years)-1),
        "win_rate": float((active>0).mean()),
    }
    if turnover is not None:
        if not turnover.index.equals(a.index) or turnover.isna().any():
            raise ValueError("turnover dates must match and be complete")
        values["annualized_turnover"] = float(turnover.sum()/years)
    return values


def rolling_relative_metrics(strategy: pd.Series, benchmark: pd.Series,
                             window: int=12, periods_per_year: int=12) -> pd.DataFrame:
    """Trailing annualized risk and active return using only observed past data."""
    if not strategy.index.equals(benchmark.index) or window<6:
        raise ValueError("return alignment or rolling window invalid")
    active = strategy - benchmark
    te = active.rolling(window,min_periods=window).std(ddof=1)*np.sqrt(periods_per_year)
    info = active.rolling(window,min_periods=window).mean()*periods_per_year/te.replace(0,np.nan)
    nav = (1+strategy).cumprod()
    relative_nav = ((1+strategy)/(1+benchmark)).cumprod()
    return pd.DataFrame({
        "rolling_volatility": strategy.rolling(window,min_periods=window).std(ddof=1)*np.sqrt(periods_per_year),
        "rolling_tracking_error": te,
        "rolling_information_ratio": info,
        "rolling_active_return": active.rolling(window,min_periods=window).mean()*periods_per_year,
        "cumulative_relative_wealth": relative_nav,
        "drawdown": nav/nav.cummax()-1,
    })


def factor_exposures(weights: pd.DataFrame, exposures: dict[str,pd.DataFrame]) -> pd.DataFrame:
    """Weight-averaged date-specific stock factor exposures, no future fill."""
    if weights.isna().any().any():
        raise ValueError("weights must be complete")
    out = pd.DataFrame(index=weights.index)
    for name, matrix in exposures.items():
        if not weights.index.equals(matrix.index) or not weights.columns.equals(matrix.columns):
            raise ValueError(f"factor exposure {name} not aligned")
        invalid = weights.gt(0) & matrix.isna()
        if invalid.any().any():
            raise ValueError(f"missing factor {name} for held constituents")
        out[name] = weights.mul(matrix).sum(axis=1)
    return out


def cost_sensitivity(gross: pd.Series, turnover: pd.Series,
                     cost_levels_bps=(0, 5, 10, 20, 40),
                     periods_per_year: int=12) -> pd.DataFrame:
    """Reprice a *fixed trade path* at costs; approximation, no reoptimization.

    Preserves proportional cost compounding; gross and turnover are fixed,
    so varying cost does not alter future holdings or decision rules.
    """
    if not gross.index.equals(turnover.index):
        raise ValueError("gross/turnover dates must match")
    if len(gross)<12 or gross.isna().any() or turnover.isna().any() or (turnover<0).any():
        raise ValueError("invalid gross returns or turnover")
    out=[]
    years=len(gross)/periods_per_year
    for bps in cost_levels_bps:
        if bps<0:
            raise ValueError("cost must be nonnegative")
        fractions=turnover*bps/10000
        if (fractions >= 1).any():
            raise ValueError("cost would exhaust wealth")
        net=(1-fractions)*(1+gross)-1
        if (net<=-1).any():
            raise ValueError("invalid portfolio return")
        out.append({"cost_bps":float(bps),
                    "annualized_return":float((1+net).prod()**(1/years)-1),
                    "total_turnover":float(turnover.sum())})
    return pd.DataFrame(out)


def compare_methodologies(results: dict[str,pd.Series], benchmark: pd.Series) -> pd.DataFrame:
    """Same-date descriptive comparison. Fail rather than silently intersect dates."""
    if not results:
        raise ValueError("need at least one portfolio")
    rows=[]
    for name, returns in results.items():
        stats=benchmark_comparison(returns,benchmark)
        rows.append({"methodology":name,**stats})
    return pd.DataFrame(rows).set_index("methodology")


def sector_active_exposure(index_sector: pd.DataFrame,
                           benchmark_sector: pd.DataFrame) -> pd.DataFrame:
    if not index_sector.index.equals(benchmark_sector.index):
        raise ValueError("sector dates must align")
    names=index_sector.columns.union(benchmark_sector.columns)
    return index_sector.reindex(columns=names,fill_value=0)-benchmark_sector.reindex(columns=names,fill_value=0)


def annualized_sharpe(returns: pd.Series, risk_free_per_period: float=0.0,
                      periods_per_year: int=12) -> float:
    if len(returns)<12 or returns.isna().any():
        raise ValueError("twelve complete observations required")
    excess=returns-risk_free_per_period
    sd=float(excess.std(ddof=1))
    return float(excess.mean()/sd*np.sqrt(periods_per_year)) if sd>0 else float("nan")
