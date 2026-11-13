"""Index selection, constraints, and drift-aware investable-return approximation."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from .math_models import minimum_variance
from .portfolio_theory import risk_parity
from .institutional_index import benchmark_asof, optimize_active_index


@dataclass(frozen=True)
class IndexBacktest:
    returns: pd.Series
    gross_returns: pd.Series
    benchmark_returns: pd.Series
    turnover: pd.Series
    weights: pd.DataFrame
    pre_trade_weights: pd.DataFrame
    costs: pd.Series


def construct_weights(scores: pd.DataFrame, membership: pd.DataFrame,
                      top_n: int = 20, weighting: str = "equal",
                      cap: float = 0.15, rebalance_every: int = 3,
                      prices: pd.DataFrame | None = None, vol_lookback: int = 12,
                      sectors: dict[str, str] | pd.DataFrame | None = None,
                      sector_cap: float | None = None,
                      benchmark_history: pd.DataFrame | None = None,
                      optimizer_risk_aversion: float = 3.,
                      optimizer_turnover_penalty: float = .02,
                      optimizer_tracking_error_limit: float | None = None,
                      optimizer_max_trade_weight: float | None = None) -> pd.DataFrame:
    """Rank scores at decision close; reconstitution at every k-th observation.

    The 'score' method uses shifted positive z-score values, not predictive alpha.
    Sector classifications MUST be effective-dated before calling them PIT.
    """
    if not scores.index.equals(membership.index) or not scores.columns.equals(membership.columns):
        raise ValueError("scores/membership alignment required")
    if top_n < 1 or rebalance_every < 1 or cap <= 0 or cap > 1:
        raise ValueError("invalid index construction parameters")
    if weighting not in {"equal", "score", "inverse_volatility", "minimum_variance", "risk_parity", "benchmark_relative"}:
        raise ValueError("unsupported weighting")
    if sector_cap is not None and (sectors is None or not 0 < sector_cap <= 1):
        raise ValueError("sector cap requires valid sector mapping")
    if weighting == "benchmark_relative" and benchmark_history is None:
        raise ValueError("Benchmark-relative weighting requires real, dated benchmark_weights.csv")
    if weighting in {"inverse_volatility", "minimum_variance", "risk_parity", "benchmark_relative"} and prices is None:
        raise ValueError("historical prices required for inverse volatility")
    vol = None
    lagged_returns = None
    if prices is not None and weighting in {"inverse_volatility", "minimum_variance", "risk_parity", "benchmark_relative"}:
        if not prices.index.equals(scores.index) or not prices.columns.equals(scores.columns):
            raise ValueError("historical price panel must align")
        lagged_returns=prices.pct_change(fill_method=None).shift(1)
        if weighting == "inverse_volatility":
            vol = lagged_returns.rolling(vol_lookback, min_periods=vol_lookback).std()
    output = pd.DataFrame(np.nan, index=scores.index, columns=scores.columns)
    for i, date in enumerate(scores.index):
        if i % rebalance_every:
            continue
        eligible = scores.loc[date].where(membership.loc[date].astype(bool)).dropna()
        selected = eligible.sort_index().sort_values(ascending=False, kind="stable").head(top_n)
        weights = pd.Series(0.0, index=scores.columns)
        if selected.empty:
            output.loc[date] = weights
            continue
        if selected.size * cap < 1 - 1e-10:
            raise ValueError(f"infeasible cap: {len(selected)} eligible names * {cap} < 1")
        if weighting == "benchmark_relative":
            benchmark=benchmark_asof(benchmark_history,date,scores.columns)
            old_targets=output.iloc[:i].dropna(how="all")
            previous_full=(old_targets.iloc[-1].reindex(scores.columns).fillna(0)
                           if not old_targets.empty else pd.Series(0.,index=scores.columns))
            # Include prior positions even if they have fallen out of both
            # today's benchmark and today's selected top-N. This preserves
            # the full cost of mandatory liquidations in the turnover term.
            active_names=(set(selected.index)|set(benchmark[benchmark>0].index)|
                          set(previous_full[previous_full>1e-10].index))
            risk_names=pd.Index([t for t in scores.columns if t in active_names])
            # Source evidence must cover all benchmark exposures, including
            # securities excluded from the active index. Never set missing
            # variance observations to zero.
            history=lagged_returns.loc[:date,risk_names].tail(max(12,vol_lookback))
            if len(history)<12 or history.isna().any().any():
                raise ValueError("Benchmark-relative risk requires >=12 complete PRIOR monthly returns "
                                 "for all selected and benchmark-held securities")
            risk_cov=history.cov()*12
            forecast=pd.Series(np.nan,index=risk_names)
            forecast.loc[selected.index]=selected
            previous=previous_full.reindex(risk_names)
            identities=None
            if sector_cap is not None:
                if isinstance(sectors,pd.DataFrame):
                    identities=sectors.loc[date].reindex(risk_names)
                else:
                    identities=pd.Series(sectors).reindex(risk_names)
            optimized=optimize_active_index(
                forecast,benchmark.reindex(risk_names),risk_cov,previous,
                max_weight=cap,risk_aversion=optimizer_risk_aversion,
                turnover_penalty=optimizer_turnover_penalty,
                tracking_error_limit=optimizer_tracking_error_limit,
                sector_labels=identities,sector_cap=sector_cap,
                max_trade_weight=optimizer_max_trade_weight)
            weights.loc[risk_names]=optimized.weights
            output.loc[date]=weights
            continue
        if weighting == "equal":
            raw = pd.Series(1.0, index=selected.index)
        elif weighting == "score":
            raw = (selected - selected.min() + 0.1).clip(lower=0.1)
        elif weighting == "inverse_volatility":
            asset_vol = vol.loc[date, selected.index]
            if asset_vol.isna().any() or (asset_vol <= 0).any():
                raise ValueError("not enough prior volatility data for selected names")
            raw = 1 / asset_vol
        else:
            history=lagged_returns.loc[:date,selected.index].tail(vol_lookback)
            if len(history)<3 or history.isna().any().any():
                raise ValueError("insufficient lagged complete covariance history")
            covariance=history.cov()*12
            if weighting == "minimum_variance":
                raw = minimum_variance(covariance,max_weight=cap).weights
            else:
                raw = risk_parity(covariance,max_weight=cap).weights
        target = (raw / raw.sum()).to_numpy(dtype=float)
        keys = list(selected.index)
        constraints = [{"type":"eq","fun":lambda w: np.sum(w) - 1}]
        if sector_cap is not None:
            if isinstance(sectors, pd.DataFrame):
                if not sectors.index.equals(scores.index) or not sectors.columns.equals(scores.columns):
                    raise ValueError("effective-dated sector matrix must match scores")
                current_sectors = sectors.loc[date].reindex(keys)
                if current_sectors.isna().any():
                    raise ValueError(f"missing effective-dated sector at {date}")
                mapping = current_sectors.to_dict()
            else:
                mapping = sectors
                if any(k not in mapping for k in keys):
                    raise ValueError("missing sector classification")
            for sector in sorted(set(mapping[k] for k in keys)):
                mask = np.array([mapping[k] == sector for k in keys])
                constraints.append({"type":"ineq", "fun": lambda w,mask=mask: sector_cap - w[mask].sum()})
        opt = minimize(lambda w: float(((w-target)**2).sum()), np.full(len(keys), 1.0/len(keys)),
                       method="SLSQP",bounds=[(0,cap)]*len(keys),constraints=constraints,
                       options={"ftol":1e-12,"maxiter":1000})
        if not opt.success or abs(opt.x.sum()-1) > 1e-6 or opt.x.max() > cap+1e-6:
            raise ValueError("index constraints infeasible or optimization failed")
        weights.loc[keys] = np.clip(opt.x,0,cap)
        weights /= weights.sum()
        output.loc[date] = weights
    # Target weights are only specified at rebalance dates. Between those,
    # a NaN row means 'hold drifted existing positions', NOT reset to target.
    return output


def backtest_index(prices: pd.DataFrame, targets: pd.DataFrame,
                   benchmark_returns: pd.Series, cost_bps: float = 10.0,
                   execution_lag: int = 0) -> IndexBacktest:
    """Long-only, self-financing monthly simulation with drift-aware turnover.

    At decision date t, target applies to t->t+1 when lag=0 (idealized
    same-close execution). lag=1 applies the most recent target one month
    later. NaN target rows mean no rebalance. Rebalance prices are assumed
    to be observed at the beginning of the relevant month-end interval.
    No delisting-recovery estimates are invented: missing held returns fail.
    """
    if not prices.index.equals(targets.index) or not prices.columns.equals(targets.columns):
        raise ValueError("prices and targets must align exactly")
    if not benchmark_returns.index.equals(prices.index):
        raise ValueError("benchmark dates must match prices")
    if cost_bps < 0 or execution_lag not in (0,1):
        raise ValueError("nonnegative cost and execution lag in {0,1} required")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("prices dates must be unique increasing")
    if (prices <= 0).where(prices.notna(),False).any().any():
        raise ValueError("nonpositive prices")
    if benchmark_returns.isna().any() or not np.isfinite(benchmark_returns.to_numpy()).all():
        raise ValueError("benchmark returns must be complete and finite")
    if len(prices) < 3:
        raise ValueError("at least three observations required")
    if np.isinf(prices.to_numpy()).any() or np.isinf(targets.to_numpy()).any():
        raise ValueError("infinite inputs")
    observed = targets.dropna(how="all")
    if observed.isna().any().any() or (observed < -1e-10).any().any():
        raise ValueError("target rows must have complete nonnegative weights")
    if (observed.sum(axis=1) > 1+1e-8).any():
        raise ValueError("target weights sum above one")
    current = np.zeros(prices.shape[1], dtype=float)
    cash = 1.0
    output, gross_out, turnover_out, cost_out, weight_out, pre_out = [], [], [], [], [], []
    ix = prices.index
    for i in range(len(ix)-1):
        w_pre = current.copy()
        target_i = i - execution_lag
        if target_i >= 0 and targets.iloc[target_i].notna().all():
            target = targets.iloc[target_i].to_numpy(dtype=float)
            turn = float(np.abs(target-current).sum())
            trading_cost = turn * cost_bps / 10000.0
            if trading_cost >= 1:
                raise ValueError("cost consumes entire portfolio")
            current = target.copy()
            cash = max(0,1-float(target.sum()))
        else:
            turn, trading_cost = 0.0, 0.0
        p0, p1 = prices.iloc[i].to_numpy(dtype=float),prices.iloc[i+1].to_numpy(dtype=float)
        holding = current > 1e-12
        if not np.isfinite(p0[holding]).all() or not np.isfinite(p1[holding]).all():
            raise ValueError(f"missing price on held security during {ix[i]} -> {ix[i+1]}")
        rtn = np.zeros_like(current)
        rtn[holding] = p1[holding]/p0[holding]-1.0
        gross = float(current @ rtn)
        net = (1-trading_cost)*(1+gross)-1
        if 1+gross <= 0:
            raise ValueError("portfolio wiped out: cannot drift weights")
        current = current * (1+rtn)/(1+gross)
        cash /= 1+gross
        output.append(net)
        gross_out.append(gross)
        turnover_out.append(turn)
        cost_out.append(trading_cost)
        weight_out.append(target if target_i >= 0 and targets.iloc[target_i].notna().all() else w_pre)
        pre_out.append(w_pre)
    dates=ix[1:]
    return IndexBacktest(
        pd.Series(output,index=dates,name="net_return"),
        pd.Series(gross_out,index=dates,name="gross_return"),
        benchmark_returns.loc[dates].rename("benchmark_return"),
        pd.Series(turnover_out,index=dates,name="turnover"),
        pd.DataFrame(weight_out,index=dates,columns=prices.columns),
        pd.DataFrame(pre_out,index=dates,columns=prices.columns),
        pd.Series(cost_out,index=dates,name="transaction_cost_fraction"),
    )
