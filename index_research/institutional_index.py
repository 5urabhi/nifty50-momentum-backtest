"""Explainable benchmark-relative index optimization; research-grade constraints.

This independent optimizer is NOT an MSCI/Barra replica and does not claim its
factor-score inputs are predictive alpha. Missing benchmark and covariance
evidence are hard blockers, never silently replaced by equal weights.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize


class IndexInfeasible(ValueError):
    """Human-readable diagnostics for mathematically impossible portfolios."""
    def __init__(self, reason: str, diagnostics: dict | None = None):
        self.diagnostics = diagnostics or {}
        super().__init__(reason)


@dataclass(frozen=True)
class OptimizedIndex:
    weights: pd.Series
    active_variance_annual: float
    tracking_error_annual: float
    target_turnover: float
    binding_constraints: list[str]
    objective_value: float
    solver_message: str


def read_benchmark_history(path: str | Path) -> pd.DataFrame:
    """Read complete dated benchmark snapshots with explicit zero-weight names."""
    source=Path(path)
    if not source.is_file() or source.is_symlink():
        raise ValueError("benchmark_weights.csv is required, including explicit zero weights")
    frame=pd.read_csv(source)
    if not {"date","ticker","weight"}.issubset(frame.columns) or frame.empty:
        raise ValueError("Benchmark weights require date,ticker,weight and rows")
    out=frame.loc[:,["date","ticker","weight"]].copy()
    out["date"]=pd.to_datetime(out["date"],errors="raise")
    out["weight"]=pd.to_numeric(out["weight"],errors="raise")
    if (out["date"].isna().any() or out["ticker"].isna().any() or
        out["ticker"].astype(str).str.strip().eq("").any() or
        out[["date","ticker"]].duplicated().any() or
        not np.isfinite(out["weight"].to_numpy(dtype=float)).all() or
        (out["weight"]<0).any()):
        raise ValueError("Invalid/duplicate benchmark members, dates or weights")
    sums=out.groupby("date")["weight"].sum()
    if not np.allclose(sums.to_numpy(),1.,rtol=0.,atol=1e-6):
        raise ValueError("Every benchmark-weight snapshot must sum to one")
    return out.sort_values(["date","ticker"]).reset_index(drop=True)


def benchmark_asof(history: pd.DataFrame, decision: pd.Timestamp,
                   universe: pd.Index, max_age_days: int = 95) -> pd.Series:
    """No future benchmark weights; no missing constituents or stale snapshots."""
    previous=history.loc[history["date"]<=decision]
    if previous.empty:
        raise IndexInfeasible("No benchmark snapshot available on/before decision date")
    observed=previous["date"].max()
    if (decision-observed).days > max_age_days:
        raise IndexInfeasible("Benchmark weight snapshot is stale at " + str(decision.date()),
                              {"snapshot":observed.date().isoformat(),"max_age_days":max_age_days})
    frame=previous.loc[previous["date"]==observed]
    if set(frame["ticker"]) != set(universe):
        missing=sorted(set(universe)-set(frame["ticker"]))
        unknown=sorted(set(frame["ticker"])-set(universe))
        raise IndexInfeasible("Benchmark weights must cover the exact modeled universe",
                              {"missing":missing[:20],"unexpected":unknown[:20]})
    return frame.set_index("ticker")["weight"].reindex(universe).astype(float)


def optimize_active_index(scores: pd.Series, benchmark: pd.Series,
                          covariance_annual: pd.DataFrame,
                          previous: pd.Series | None = None,
                          *, max_weight: float = .1, risk_aversion: float = 3.,
                          turnover_penalty: float = .02,
                          tracking_error_limit: float | None = None,
                          sector_labels: pd.Series | None = None,
                          sector_cap: float | None = None,
                          max_trade_weight: float | None = None) -> OptimizedIndex:
    """Maximize score minus active variance/turnover with hard, auditable constraints.

    Alpha term uses *research factor z-scores*, not calibrated expected returns.
    Covariance is ANNUALIZED and estimated outside this routine using strictly
    prior returns. Turnover uses previous TARGET weights as a declared proxy
    until the trading simulator computes drifted actual turnover. The smooth
    L1 penalty is a numerical approximation with epsilon=1e-7.

    NaN score => ineligible and fixed to zero. Non-NaN score => eligible to hold.
    """
    universe=scores.index
    if (universe.has_duplicates or not universe.equals(benchmark.index) or
        not universe.equals(covariance_annual.index) or
        not universe.equals(covariance_annual.columns)):
        raise ValueError("Scores, benchmark and covariance must share exact security axes")
    if not 0<max_weight<=1 or risk_aversion<0 or turnover_penalty<0:
        raise ValueError("Invalid max weight or optimization risk/turnover penalties")
    if (tracking_error_limit is not None and not 0<tracking_error_limit<=5) or (
        max_trade_weight is not None and not 0<max_trade_weight<=1):
        raise ValueError("Tracking-error/trade caps must be strictly positive")
    b=benchmark.to_numpy(dtype=float)
    cov=covariance_annual.to_numpy(dtype=float)
    if (not np.isfinite(b).all() or (b<0).any() or abs(b.sum()-1)>1e-6 or
        not np.isfinite(cov).all() or not np.allclose(cov,cov.T,atol=1e-8) or
        np.linalg.eigvalsh(cov).min()<-1e-7):
        raise ValueError("Benchmark or annualized covariance is incomplete, non-PSD or unnormalized")
    cov=(cov+cov.T)*.5
    usable=(scores.notna() & np.isfinite(scores.astype(float)))
    members=np.flatnonzero(usable.to_numpy())
    if not len(members):
        raise IndexInfeasible("All selected factor scores are unavailable")
    if len(members)*max_weight < 1-1e-8:
        raise IndexInfeasible("Constituent limit infeasible: selected names × security cap < 100%",
                              {"eligible_count":len(members),"max_weight":max_weight})
    if previous is None:
        old=np.zeros(len(universe),dtype=float)
    else:
        if not previous.index.equals(universe):
            raise ValueError("Previous target universe must match the modeled securities")
        old=previous.to_numpy(dtype=float)
        if not np.isfinite(old).all() or (old<-1e-10).any() or old.sum()>1+1e-6:
            raise ValueError("Previous targets must be complete, long-only and <=100%")
    low=np.zeros(len(members))
    high=np.full(len(members),float(max_weight))
    if max_trade_weight is not None:
        low=np.maximum(low,old[members]-max_trade_weight)
        high=np.minimum(high,old[members]+max_trade_weight)
        excluded=np.ones(len(universe),dtype=bool)
        excluded[members]=False
        if (old[excluded] > max_trade_weight+1e-9).any():
            raise IndexInfeasible("Trade cap prevents liquidating a security excluded at rebalance")
        if (low>high+1e-9).any():
            raise IndexInfeasible("Trade cap conflicts with security position cap")
    if float(low.sum())>1+1e-9 or float(high.sum())<1-1e-9:
        raise IndexInfeasible("Security/trade caps make full investment impossible",
                              {"minimum_total_weight":float(low.sum()),
                               "maximum_total_weight":float(high.sum())})
    constraints=[{"type":"eq","fun":lambda w: float(w.sum()-1),
                  "jac":lambda w: np.ones(len(members))}]
    groups={}
    if sector_cap is not None:
        if not 0<sector_cap<=1 or sector_labels is None or not sector_labels.index.equals(universe):
            raise ValueError("Sector cap needs aligned, as-of sector identities")
        selected=sector_labels.iloc[members]
        if selected.isna().any():
            raise IndexInfeasible("Missing historical sector identity for a selected security")
        for label in sorted(selected.astype(str).unique()):
            local=np.flatnonzero(selected.astype(str).to_numpy()==label)
            groups[label]=local
            if float(low[local].sum())>sector_cap+1e-9:
                raise IndexInfeasible("Lower trade bounds violate sector cap: "+label)
            constraints.append({"type":"ineq","fun":lambda w,loc=local:float(sector_cap-w[loc].sum()),
                                "jac":lambda w,loc=local:-np.isin(np.arange(len(members)),loc).astype(float)})
        # A necessary feasibility condition, also checked by the solver.
        if sum(min(float(high[v].sum()),sector_cap) for v in groups.values())<1-1e-8:
            raise IndexInfeasible("Combined sector/security caps cannot reach full investment",
                                  {"sector_cap":sector_cap,"sectors":len(groups)})
    alpha=scores.iloc[members].to_numpy(dtype=float)
    def full(w):
        value=np.zeros(len(universe),dtype=float)
        value[members]=w
        return value
    def active_var(w):
        diff=full(w)-b
        return float(diff@cov@diff)
    if tracking_error_limit is not None:
        constraints.append({
            "type":"ineq","fun":lambda w:tracking_error_limit**2-active_var(w),
            "jac":lambda w:-2*(cov@(full(w)-b))[members],
        })
    epsilon=1e-7
    def objective(w):
        diff=full(w)-old
        # Smooth L1 turnover penalty for stable SLSQP gradients.
        smooth=np.sqrt(diff*diff+epsilon*epsilon)-epsilon
        return float(-alpha@w+risk_aversion*active_var(w)+turnover_penalty*smooth.sum())
    def gradient(w):
        diff=full(w)-old
        d_turn=diff/np.sqrt(diff*diff+epsilon*epsilon)
        return -alpha+2*risk_aversion*(cov@(full(w)-b))[members]+turnover_penalty*d_turn[members]
    start=np.clip(b[members],low,high)
    slack=1-start.sum()
    if slack>0:
        room=high-start
        if room.sum()>0:
            start=start+slack*room/room.sum()
    elif slack<0:
        room=start-low
        if room.sum()>0:
            start=start+slack*room/room.sum()
    result=minimize(objective,start,jac=gradient,method="SLSQP",
                    bounds=list(zip(low,high)),constraints=constraints,
                    options={"maxiter":1000,"ftol":1e-10})
    w=full(result.x)
    variance=active_var(result.x)
    valid=(result.success and np.isfinite(w).all() and
           abs(w.sum()-1)<1e-6 and (w>=-1e-7).all() and
           (w<=max_weight+1e-6).all() and
           (tracking_error_limit is None or variance<=(tracking_error_limit+1e-6)**2) and
           all(w[members[local]].sum()<=sector_cap+1e-6 for local in groups.values()))
    if not valid:
        raise IndexInfeasible("Benchmark-relative optimization infeasible or not converged: "+
                              str(result.message),
                              {"solver_message":str(result.message),
                               "tracking_error_limit":tracking_error_limit,
                               "minimum_feasible_tracking_error_not_established":True})
    bindings=[f"security cap {universe[i]}" for i in np.flatnonzero(abs(w-max_weight)<1e-5)]
    bindings.extend("sector cap "+key for key,loc in groups.items()
                    if sector_cap-w[members[loc]].sum()<1e-5)
    if tracking_error_limit is not None and abs(np.sqrt(max(0,variance))-tracking_error_limit)<1e-5:
        bindings.append("tracking error limit")
    return OptimizedIndex(
        pd.Series(np.maximum(w,0),index=universe,name="target_weight"),
        float(max(variance,0)),float(np.sqrt(max(variance,0))),
        float(np.abs(w-old).sum()),bindings,float(-result.fun),str(result.message))
