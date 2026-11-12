"""Minimal point-in-time-aware monthly index research primitives.

Prices: monthly adjusted close, DatetimeIndex sorted ascending, columns=tickers.
Membership: boolean DataFrame, as-of *decision dates*; NOT a current constituent list.
Weights decided at month t close are first applied to return t -> t+1.
This research engine does not model intramonth trading, corporate actions or taxes.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    returns: pd.Series
    gross_returns: pd.Series
    benchmark_returns: pd.Series
    turnover: pd.Series
    weights: pd.DataFrame


def _check_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices must have a nonempty DatetimeIndex")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("dates must be unique and ascending")
    if prices.columns.has_duplicates:
        raise ValueError("duplicate security identifiers")
    x = prices.astype(float)
    if (x.dropna(how="all") <= 0).any().any():
        raise ValueError("nonpositive prices")
    return x


def momentum_scores(prices: pd.DataFrame, formation: int = 12, skip: int = 1) -> pd.DataFrame:
    """Return formation-window cumulative returns ending skip months before decision.

    With formation=12 and skip=1, signal at t is P[t-1]/P[t-13]-1.
    Future returns are never used to compute a signal.
    """
    x = _check_prices(prices)
    if formation < 1 or skip < 0:
        raise ValueError("formation must be >=1 and skip >=0")
    return x.shift(skip).div(x.shift(skip + formation)).sub(1)


def equal_weight_top_n(
    scores: pd.DataFrame,
    membership: pd.DataFrame,
    n: int = 10,
    min_names: int = 1,
) -> pd.DataFrame:
    """Select highest-scoring currently eligible names, with deterministic ties.

    Missing membership means NOT eligible. Never infer historic constituents from
    the present-day Nifty 50 list. Missing scores are never eligible.
    """
    if n < 1 or min_names < 1:
        raise ValueError("n and min_names must be positive")
    if not scores.index.equals(membership.index):
        raise ValueError("membership dates must exactly match score dates")
    if not scores.columns.equals(membership.columns):
        raise ValueError("membership identifiers must exactly match score identifiers")
    if membership.isna().any().any():
        raise ValueError("missing membership data: cannot claim point-in-time validity")
    if not membership.isin([True, False]).all().all():
        raise ValueError("membership must be boolean")
    output = pd.DataFrame(0.0, index=scores.index, columns=scores.columns)
    for date in scores.index:
        eligible = scores.loc[date].where(membership.loc[date].astype(bool)).dropna()
        eligible = eligible.sort_index().sort_values(ascending=False, kind="stable").head(n)
        if len(eligible) >= min_names:
            output.loc[date, eligible.index] = 1.0 / len(eligible)
    return output


def run_monthly_backtest(
    prices: pd.DataFrame,
    decision_weights: pd.DataFrame,
    benchmark_returns: pd.Series,
    cost_bps: float = 10.0,
) -> BacktestResult:
    """Monthly close-to-close simulation with next-month execution and turnover cost.

    Weight row t represents a decision at close t and is held during t -> t+1.
    This simple model charges one-way cost_bps * sum(abs(weight changes)) at the
    opening of each holding interval, including the first deployment from cash.
    Execution at the decision close is an idealization; add explicit execution
    lag and slippage before making investable-return claims.
    """
    x = _check_prices(prices)
    if cost_bps < 0:
        raise ValueError("cost_bps must be nonnegative")
    if not decision_weights.index.equals(x.index) or not decision_weights.columns.equals(x.columns):
        raise ValueError("weights must align exactly with prices")
    if decision_weights.isna().any().any() or not np.isfinite(decision_weights.to_numpy()).all():
        raise ValueError("weights must be finite")
    if (decision_weights < -1e-12).any().any():
        raise ValueError("long-only engine cannot use negative weights")
    if (decision_weights.sum(axis=1) > 1.0 + 1e-10).any():
        raise ValueError("weights must sum to <= 1")
    if not benchmark_returns.index.equals(x.index):
        raise ValueError("benchmark dates must align exactly with prices")
    if benchmark_returns.isna().any():
        raise ValueError("benchmark has missing returns")
    # A membership-restricted decision at t must never hold assets lacking
    # the entry/exit marks needed to observe the next interval.
    next_returns = x.shift(-1).div(x).sub(1)
    bad = decision_weights.gt(0) & next_returns.isna()
    if bad.iloc[:-1].any().any():
        raise ValueError("held security has unavailable next-period return")
    gross = decision_weights.mul(next_returns).sum(axis=1, min_count=1).iloc[:-1]
    prev = decision_weights.shift(1).fillna(0.0)
    turnover = (decision_weights - prev).abs().sum(axis=1).iloc[:-1]
    net = gross - turnover * (cost_bps / 10000.0)
    # Result dates label the END of each holding interval.
    dates = x.index[1:]
    gross.index = dates
    net.index = dates
    turnover.index = dates
    benchmark = benchmark_returns.loc[dates].astype(float)
    return BacktestResult(
        returns=net.rename("strategy_net"),
        gross_returns=gross.rename("strategy_gross"),
        benchmark_returns=benchmark.rename("benchmark"),
        turnover=turnover.rename("one_way_weight_change"),
        weights=decision_weights.iloc[:-1].set_axis(dates),
    )


def summary_metrics(result: BacktestResult, periods_per_year: int = 12) -> dict:
    """Annualized summary; no performance claim for insufficient observations."""
    r = result.returns.dropna()
    b = result.benchmark_returns.reindex(r.index)
    if len(r) < 12 or b.isna().any() or periods_per_year < 1:
        raise ValueError("at least 12 complete, benchmark-aligned observations required")
    if (r <= -1).any() or (b <= -1).any():
        raise ValueError("returns must exceed -100%")
    years = len(r) / periods_per_year
    ann = float(np.prod(1 + r) ** (1 / years) - 1)
    vol = float(r.std(ddof=1) * np.sqrt(periods_per_year))
    excess = r - b
    te = float(excess.std(ddof=1) * np.sqrt(periods_per_year))
    active = float(excess.mean() * periods_per_year)
    wealth = (1 + r).cumprod()
    drawdown = wealth.div(wealth.cummax()).sub(1)
    return {
        "observations": len(r),
        "annualized_return": ann,
        "annualized_volatility": vol,
        "max_drawdown": float(drawdown.min()),
        "tracking_error": te,
        "information_ratio": active / te if te > 0 else float("nan"),
        "annualized_turnover_proxy": float(result.turnover.loc[r.index].mean() * periods_per_year),
    }
