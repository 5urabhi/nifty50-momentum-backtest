"""Statistical inference, cross-sectional factor evaluation and stress tests.

No mathematical test can repair biased historical universe selection.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm, t as student_t


def newey_west_mean_test(returns: pd.Series, lags: int | None = None) -> dict:
    """HAC z statistic for mean != 0 with Bartlett weights and Gaussian p-value.

    Returns are periodic. For short samples do not interpret normal asymptotic
    p-values as exact small-sample inference. Mean and SE use decimal returns.
    """
    r=pd.Series(returns,dtype=float).dropna().to_numpy()
    if len(r)<10 or not np.isfinite(r).all():
        raise ValueError("at least 10 finite observations required")
    n=len(r)
    L = int(np.floor(4*(n/100)**(2/9))) if lags is None else lags
    if L<0 or L>=n:
        raise ValueError("lags must be in [0, n-1]")
    centered=r-r.mean()
    long_run=float(centered@centered/n)
    for k in range(1,L+1):
        covariance=float(centered[k:]@centered[:-k]/n)
        long_run += 2*(1-k/(L+1))*covariance
    se=float(np.sqrt(max(long_run,0)/n))
    stat=float(r.mean()/se) if se>1e-15 else np.nan
    return {"observations":n,"mean_per_period":float(r.mean()),
            "hac_standard_error":se,"z_statistic":stat,
            "two_sided_normal_p_value":float(2*norm.sf(abs(stat))) if np.isfinite(stat) else None,
            "lags":L}


def block_bootstrap_sharpe(returns: pd.Series, block_length: int = 6,
                           simulations: int = 2000, seed: int = 2026,
                           periods_per_year: int = 12, confidence: float = .95) -> dict:
    """Circular moving-block bootstrap interval for zero-risk-free Sharpe.

    Assumes sample is approximately stationary. Interval is percentile bootstrap,
    not multiple-testing corrected or a proof of out-of-sample profitability.
    """
    r=pd.Series(returns,dtype=float).dropna().to_numpy()
    n=len(r)
    if n<24 or not np.isfinite(r).all() or not 1<=block_length<=n or simulations<100 or not 0<confidence<1:
        raise ValueError("need >=24 finite returns, valid block length and >=100 simulations")
    rng=np.random.default_rng(seed)
    count=int(np.ceil(n/block_length))
    starts=rng.integers(0,n,size=(simulations,count))
    offsets=np.arange(block_length)
    sampled=(starts[:,:,None]+offsets[None,None,:])%n
    paths=r[sampled.reshape(simulations,-1)[:,:n]]
    means=paths.mean(axis=1)
    vols=paths.std(axis=1,ddof=1)
    ratios=np.divide(means*np.sqrt(periods_per_year),vols,
                     out=np.full_like(means,np.nan),where=vols>1e-12)
    finite=ratios[np.isfinite(ratios)]
    if len(finite)<simulations*.95:
        raise ValueError("bootstrap samples degenerate")
    q=(1-confidence)/2
    sample_vol=r.std(ddof=1)
    return {"point_estimate":float(r.mean()*np.sqrt(periods_per_year)/sample_vol) if sample_vol>1e-12 else None,
            "lower":float(np.quantile(finite,q)),"upper":float(np.quantile(finite,1-q)),
            "seed":seed,"block_length":block_length,"replications":simulations}


def false_discovery_bh(p_values: pd.Series, alpha: float = .05) -> pd.DataFrame:
    """Benjamini-Hochberg FDR adjusted p-values; assumes suitable dependence."""
    if not 0<alpha<1:
        raise ValueError("alpha must be in (0,1)")
    p=pd.Series(p_values,dtype=float)
    if p.isna().any() or (~np.isfinite(p)).any() or ((p<0)|(p>1)).any():
        raise ValueError("p-values must be in [0,1] and finite")
    if len(p)==0:
        raise ValueError("nonempty p-values required")
    order=np.argsort(p.to_numpy(),kind="stable")
    ps=p.to_numpy()[order]
    m=len(ps)
    adjusted=np.minimum.accumulate((ps*m/np.arange(1,m+1))[::-1])[::-1]
    original=np.empty(m)
    original[order]=np.minimum(adjusted,1)
    return pd.DataFrame({"raw_p":p,"bh_adjusted_p":original,
                         "reject_at_alpha":original<=alpha},index=p.index)


def quantile_spread(scores: pd.DataFrame, future_returns: pd.DataFrame,
                    eligible: pd.DataFrame, quantiles: int = 5) -> pd.DataFrame:
    """Monthly top-minus-bottom and quantile portfolio equal-weight returns.

    Scores and returns indexed by *decision date*. Future returns must be
    precisely the subsequent holding interval and never used in formation.
    Returns informational series only; does not handle turnover/costs.
    """
    if quantiles<2 or not scores.index.equals(future_returns.index) or not scores.columns.equals(future_returns.columns):
        raise ValueError("bad quantile or score/return alignment")
    if not scores.index.equals(eligible.index) or not scores.columns.equals(eligible.columns):
        raise ValueError("eligibility must align")
    rows=[]
    for date in scores.index:
        s=scores.loc[date].where(eligible.loc[date].astype(bool))
        r=future_returns.loc[date]
        valid=s.notna() & r.notna() & np.isfinite(s) & np.isfinite(r)
        ranked=s[valid].sort_index().sort_values(kind="stable")
        if len(ranked)<2*quantiles:
            continue
        # Deterministic equal-sized bucket by ordered rank, including ties.
        idx=np.array_split(ranked.index.to_numpy(),quantiles)
        bucket=[float(r.loc[group].mean()) for group in idx]
        rows.append({"date":date,**{f"Q{k+1}":v for k,v in enumerate(bucket)},
                     "top_minus_bottom":bucket[-1]-bucket[0],
                     "n_assets":len(ranked)})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def scenario_loss(weights: pd.Series, shocks: pd.Series,
                  sector_map: dict[str,str] | None = None,
                  sector_shocks: dict[str,float] | None = None) -> dict:
    """Linear instantaneous arithmetic shock P&L; ignores nonlinear derivatives.

    Percent shocks in decimal simple-return terms. Names without individual
    shock default to zero unless sector-level scenario supplied.
    """
    w=weights.astype(float)
    if w.isna().any() or (~np.isfinite(w)).any() or (w<0).any() or w.sum()>1+1e-8:
        raise ValueError("long-only weights must be finite and <=100% invested")
    s=shocks.reindex(w.index).fillna(0).astype(float)
    if sector_shocks is not None:
        if sector_map is None or any(k not in sector_map for k in w.index):
            raise ValueError("sector shock needs all securities mapped")
        for key in w.index:
            if key not in shocks.index:
                s[key]=float(sector_shocks.get(sector_map[key],0))
    if not np.isfinite(s.to_numpy()).all() or (s<=-1).any():
        raise ValueError("shock must be finite and above -100%")
    contributions=w*s
    return {"portfolio_simple_return":float(contributions.sum()),
            "per_security_contributions":contributions.to_dict()}
