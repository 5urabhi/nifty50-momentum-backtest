"""Empirical asset-pricing statistics and honest statistical inference.

All regressions are descriptive. Testing many candidate index parameters can
inflate significance; adjusted p-values and untouched holdout are required.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.stats import norm, t as student_t


@dataclass(frozen=True)
class HACRegression:
    coefficients: pd.Series
    standard_errors: pd.Series
    t_statistics: pd.Series
    p_values_normal_approx: pd.Series
    r_squared: float
    observations: int
    nw_lags: int


def newey_west_ols(y: pd.Series, factors: pd.DataFrame | None = None,
                   lags: int | None = None) -> HACRegression:
    """OLS with Bartlett-weight Newey-West heteroskedasticity/autocorrelation
    robust standard errors, finite-sample sandwich n/(n-k) correction.

    Applies two-sided Gaussian asymptotic p-values (NOT exact t tests).
    Constant and factors must have full column rank. Observations are
    aligned by date before dropping null rows.
    """
    if factors is None:
        factors=pd.DataFrame(index=y.index)
    if not isinstance(y,pd.Series) or not isinstance(factors,pd.DataFrame):
        raise ValueError("y and factors must be pandas objects")
    if factors.columns.has_duplicates or y.index.has_duplicates or factors.index.has_duplicates:
        raise ValueError("duplicate identifiers or dates")
    merged=factors.astype(float).join(y.rename("__dependent__").astype(float),how="inner").dropna()
    if not np.isfinite(merged.to_numpy()).all():
        raise ValueError("nonfinite observations")
    n=len(merged)
    k=len(factors.columns)+1
    if n<=max(k+5,10):
        raise ValueError("insufficient observations for robust covariance")
    lag=min(n-1,int(np.floor(4*(n/100)**(2/9)))) if lags is None else int(lags)
    if lag<0 or lag>=n:
        raise ValueError("Newey-West lags must be in [0,n)")
    xx=np.column_stack([np.ones(n),merged[factors.columns].to_numpy()])
    yy=merged["__dependent__"].to_numpy()
    if np.linalg.matrix_rank(xx)<k:
        raise ValueError("rank-deficient factor model")
    beta=np.linalg.lstsq(xx,yy,rcond=None)[0]
    residual=yy-xx@beta
    bread=np.linalg.inv(xx.T@xx)
    xe=xx*residual[:,None]
    meat=xe.T@xe
    for lag_idx in range(1,lag+1):
        cross=xe[lag_idx:].T@xe[:-lag_idx]
        meat+=(1-lag_idx/(lag+1))*(cross+cross.T)
    vcov=bread@meat@bread*n/(n-k)
    se=np.sqrt(np.maximum(np.diag(vcov),0))
    z=np.divide(beta,se,out=np.full(k,np.nan),where=se>0)
    p=2*norm.sf(np.abs(z))
    names=["alpha",*list(factors.columns)]
    denom=float(np.sum(np.square(yy-yy.mean())))
    r2=1-float(np.sum(residual**2))/denom if denom>0 else float("nan")
    return HACRegression(pd.Series(beta,index=names),pd.Series(se,index=names),
                         pd.Series(z,index=names),pd.Series(p,index=names),
                         float(r2),n,lag)


def regression_with_known_factors(asset_excess: pd.Series, factor_returns: pd.DataFrame,
                                  model: str="carhart4", lags: int | None=None) -> HACRegression:
    """Named academic factor *regression*, NOT recreation of factor portfolios.

    Input columns must be authentic return series matching the asset's frequency
    and risk-free convention. 'mkt_rf' = market minus risk-free, 'mom' = momentum.
    The Fama-French five-factor model does not automatically include momentum.
    """
    required={
        "capm":["mkt_rf"],
        "fama_french_3":["mkt_rf","smb","hml"],
        "carhart4":["mkt_rf","smb","hml","mom"],
        "fama_french_5":["mkt_rf","smb","hml","rmw","cma"],
        "ff5_momentum":["mkt_rf","smb","hml","rmw","cma","mom"],
    }
    if model not in required:
        raise ValueError("model must be capm/ff3/carhart4/ff5/ff5_momentum")
    names=required[model]
    if not set(names).issubset(factor_returns.columns):
        raise ValueError(f"missing required factor columns {sorted(set(names)-set(factor_returns.columns))}")
    return newey_west_ols(asset_excess,factor_returns[names],lags=lags)


def moving_block_bootstrap_mean(returns: pd.Series, block_length: int = 6,
                                resamples: int = 2000, level: float = 0.95,
                                seed: int = 42) -> dict:
    """Circular moving-block bootstrap CI for the sample mean per period.

    A dependence-aware *exploratory* CI; not a strategy-selection-adjusted
    inference procedure and not a promise of predictive performance.
    """
    x=pd.Series(returns,dtype=float).dropna().to_numpy()
    n=len(x)
    if n<12 or block_length<1 or block_length>n or resamples<100 or not 0<level<1 or not np.isfinite(x).all():
        raise ValueError("invalid block bootstrap input")
    rng=np.random.default_rng(seed)
    blocks=int(np.ceil(n/block_length))
    estimates=np.empty(resamples)
    for i in range(resamples):
        starts=rng.integers(0,n,size=blocks)
        positions=np.concatenate([(np.arange(s,s+block_length)%n) for s in starts])[:n]
        estimates[i]=x[positions].mean()
    alpha=(1-level)/2
    return {"sample_mean":float(x.mean()),
            "ci_lower":float(np.quantile(estimates,alpha)),
            "ci_upper":float(np.quantile(estimates,1-alpha)),
            "standard_error":float(estimates.std(ddof=1)),
            "block_length":block_length,"resamples":resamples}


def benjamini_hochberg(p_values: pd.Series) -> pd.Series:
    """FDR-adjusted q-values under standard BH assumptions; no selection correction."""
    if not isinstance(p_values,pd.Series) or p_values.empty:
        raise ValueError("nonempty pandas p-value series required")
    p=p_values.astype(float)
    if p.isna().any() or ((p<0)|(p>1)).any():
        raise ValueError("all p values must be finite within [0,1]")
    order=np.argsort(p.to_numpy())
    ranked=p.to_numpy()[order]
    n=len(p)
    adjusted=ranked*n/np.arange(1,n+1)
    adjusted=np.minimum.accumulate(adjusted[::-1])[::-1]
    out=np.empty(n)
    out[order]=np.minimum(adjusted,1)
    return pd.Series(out,index=p.index,name="bh_q_value")


def cross_sectional_rank_ic(scores: pd.DataFrame, future_returns: pd.DataFrame,
                            minimum_names: int=5) -> pd.Series:
    """Timestamp-aligned cross-sectional Spearman rank correlation."""
    if not scores.index.equals(future_returns.index) or not scores.columns.equals(future_returns.columns):
        raise ValueError("scores and forward returns must share exact axes")
    if minimum_names<3:
        raise ValueError("need at least three assets")
    result={}
    for date in scores.index:
        a,b=scores.loc[date].astype(float),future_returns.loc[date].astype(float)
        valid=a.notna() & b.notna() & np.isfinite(a) & np.isfinite(b)
        result[date]=float(a[valid].corr(b[valid],method="spearman")) if int(valid.sum())>=minimum_names else np.nan
    return pd.Series(result,name="rank_ic")


def quantile_spread(scores: pd.DataFrame, forward_returns: pd.DataFrame,
                    fraction: float=0.2, minimum_names: int=10) -> pd.Series:
    """Equal-weight high-score minus low-score forward-return spread.

    This is a zero-cost gross diagnostic, NOT an investable fully-funded index.
    Forward returns must be from the period AFTER signal availability.
    """
    if not scores.index.equals(forward_returns.index) or not scores.columns.equals(forward_returns.columns):
        raise ValueError("unmatched axes")
    if not 0<fraction<=0.5 or minimum_names<2:
        raise ValueError("invalid quantile fraction or size")
    out={}
    for date in scores.index:
        s=scores.loc[date].astype(float)
        r=forward_returns.loc[date].astype(float)
        valid=s.notna() & r.notna() & np.isfinite(s) & np.isfinite(r)
        if valid.sum()<minimum_names:
            out[date]=np.nan
            continue
        ordered=s[valid].sort_index().sort_values(kind="stable")
        count=max(1,int(np.floor(len(ordered)*fraction)))
        out[date]=float(r.loc[ordered.index[-count:]].mean()-r.loc[ordered.index[:count]].mean())
    return pd.Series(out,name="gross_quantile_spread")


def rolling_time_splits(index: pd.DatetimeIndex, train: int, test: int,
                        step: int | None=None, expanding: bool=False,
                        embargo: int=0) -> list[tuple[np.ndarray,np.ndarray]]:
    """Walk-forward chronological indices; embargo gaps precede test windows."""
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("index dates must be unique ascending")
    if train<12 or test<1 or embargo<0 or (step is not None and step<1):
        raise ValueError("invalid rolling window configuration")
    increment=test if step is None else step
    splits=[]
    for end in range(train,len(index)-embargo-test+1,increment):
        train_start=0 if expanding else end-train
        train_ids=np.arange(train_start,end)
        test_ids=np.arange(end+embargo,end+embargo+test)
        splits.append((train_ids,test_ids))
    return splits


def annualized_information_ratio(active_returns: pd.Series, periods_per_year: int=12):
    x=pd.Series(active_returns,dtype=float).dropna()
    if len(x)<12 or periods_per_year<1:
        raise ValueError("need >=12 active returns")
    volatility=x.std(ddof=1)
    return float(x.mean()*np.sqrt(periods_per_year)/volatility) if volatility>0 else float("nan")
