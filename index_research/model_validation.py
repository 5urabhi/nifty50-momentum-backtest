"""Leakage-aware quantitative model validation.

Rolling estimators use only rows *before* each forecast observation.
No hyperparameter optimization over the held-out forecast labels is performed.
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from .math_models import shrinkage_covariance, ewma_covariance
from .portfolio_theory import optimize_portfolio


def rolling_volatility_forecasts(returns: pd.Series, train_window: int=60,
                                 ewma_decay: float=0.94,
                                 periods_per_year: int=12) -> pd.DataFrame:
    """One-step variance forecasts: historical sample, EWMA, and GARCH.

    GARCH is deliberately excluded here because numerical nonconvergence is
    possible; fit_garch11 is available as an optional separate model and
    requires independent convergence tracking before inclusion in comparisons.
    Variances are in one-period decimal-return squared units.
    """
    r=pd.Series(returns,dtype=float)
    if (not isinstance(r.index,pd.DatetimeIndex) or r.index.has_duplicates
        or not r.index.is_monotonic_increasing or r.isna().any()
        or not np.isfinite(r.to_numpy()).all() or train_window<24
        or len(r)<train_window+12 or not 0<ewma_decay<1):
        raise ValueError("ordered complete returns, 24+ train and 12+ holdout required")
    records=[]
    x=r.to_numpy()
    for i in range(train_window,len(r)):
        history=x[i-train_window:i]
        sample=float(np.var(history,ddof=1))
        weights=(1-ewma_decay)*ewma_decay**np.arange(len(history)-1,-1,-1)
        weights/=weights.sum()
        center=float(weights@history)
        ewma=float(weights@np.square(history-center))
        records.append({
            "date":r.index[i],"realized_variance":float((x[i]-history.mean())**2),
            "sample_variance_forecast":sample,
            "ewma_variance_forecast":ewma,
            "sample_mean_forecast":float(history.mean()),
        })
    return pd.DataFrame(records).set_index("date")


def variance_forecast_scores(forecasts: pd.DataFrame,
                             epsilon: float=1e-12) -> pd.DataFrame:
    """Model scores on fixed holdout, lower is better.

    QLIKE = mean(log(h)+rv/h), excluding constant log(rv).
    Squared error in variance is reported for a second loss function.
    True conditional variance is unobserved; squared next return minus the prior-history estimated mean is a noisy proxy.
    """
    if "realized_variance" not in forecasts:
        raise ValueError("need realized_variance")
    realized=forecasts["realized_variance"].astype(float)
    if (realized<0).any() or realized.isna().any() or not np.isfinite(realized).all():
        raise ValueError("realized variance must be complete nonnegative")
    results=[]
    for col in forecasts.columns:
        if not col.endswith("_variance_forecast"):
            continue
        pred=forecasts[col].astype(float)
        if (pred<=0).any() or pred.isna().any() or not np.isfinite(pred).all():
            raise ValueError("forecast variances must be finite positive")
        qlike=float((np.log(pred.clip(lower=epsilon))+
                     realized/pred.clip(lower=epsilon)).mean())
        mse=float(np.square(pred-realized).mean())
        results.append({"model":col,"qlike":qlike,"variance_mse":mse,
                        "observations":len(forecasts)})
    if not results:
        raise ValueError("no *_variance_forecast columns")
    return pd.DataFrame(results).sort_values("qlike").reset_index(drop=True)


def rolling_covariance_portfolios(returns: pd.DataFrame, train_window: int=36,
                                  rebalance_every: int=3,max_weight: float=1.0,
                                  shrinkage_intensity: float=0.25,
                                  ewma_decay: float=0.94) -> pd.DataFrame:
    """One-period-ahead min-variance model comparison, monthly return inputs.

    At t, estimate covariance from [t-window,t), choose weights, then apply
    weights to return at t. This is a frictionless REBALANCE-EVERY-K-WINDOW
    illustration; costs and drift are NOT included and must be added before
    index-performance claims.
    """
    if not isinstance(returns,pd.DataFrame) or returns.empty or returns.columns.has_duplicates:
        raise ValueError("returns must be a security return matrix")
    r=returns.astype(float)
    if (not isinstance(r.index,pd.DatetimeIndex) or not r.index.is_monotonic_increasing
        or r.index.has_duplicates or r.isna().any().any()
        or not np.isfinite(r.to_numpy()).all() or train_window<12
        or rebalance_every<1 or len(r)<train_window+12):
        raise ValueError("need 12+ observation train, holdout and complete ordered returns")
    if not 0<=shrinkage_intensity<=1 or not 0<ewma_decay<1:
        raise ValueError("invalid estimator settings")
    models=["equal_weight","sample_min_variance","shrinkage_min_variance","ewma_min_variance"]
    weights={}
    outputs=[]
    for j,t in enumerate(range(train_window,len(r))):
        if j%rebalance_every==0:
            training=r.iloc[t-train_window:t]
            covariances={
                "sample_min_variance":training.cov()*12,
                "shrinkage_min_variance":shrinkage_covariance(training,shrinkage_intensity,12),
                "ewma_min_variance":ewma_covariance(training,ewma_decay,12),
            }
            weights={"equal_weight":pd.Series(1/len(r.columns),index=r.columns)}
            for name,cov in covariances.items():
                try:
                    weights[name]=optimize_portfolio(cov,max_weight=max_weight).weights
                except RuntimeError as exc:
                    raise RuntimeError(f"{name} estimator failed at {r.index[t]}: {exc}") from exc
        realized=r.iloc[t]
        row={"date":r.index[t]}
        for name in models:
            row[name]=float(weights[name]@realized)
        outputs.append(row)
    return pd.DataFrame(outputs).set_index("date")


def grouped_factor_spreads(scores: pd.DataFrame, forward_returns: pd.DataFrame,
                            groups: pd.DataFrame, top_fraction: float=0.2,
                            minimum_per_group: int=5) -> pd.Series:
    """Group-neutral equal-weight long-minus-short factor diagnostic.

    Each group contributes equally to the period spread, regardless of market
    capitalization. Group labels must be as-of decision dates; forward returns
    must correspond to AFTER the score observation. Not investable without costs.
    """
    if not (scores.index.equals(forward_returns.index) and scores.columns.equals(forward_returns.columns)
            and scores.index.equals(groups.index) and scores.columns.equals(groups.columns)):
        raise ValueError("scores, returns and group matrices must align exactly")
    if not 0<top_fraction<=0.5 or minimum_per_group<3:
        raise ValueError("invalid quantile configuration")
    result={}
    for date in scores.index:
        table=pd.DataFrame({"score":scores.loc[date],"return":forward_returns.loc[date],
                            "group":groups.loc[date]}).dropna()
        spreads=[]
        for _,parts in table.groupby("group"):
            if len(parts)<minimum_per_group:
                continue
            ordered=parts.sort_values("score",kind="stable")
            k=max(1,int(np.floor(len(ordered)*top_fraction)))
            spreads.append(float(ordered["return"].iloc[-k:].mean()-
                                 ordered["return"].iloc[:k].mean()))
        result[date]=float(np.mean(spreads)) if spreads else np.nan
    return pd.Series(result,name="group_neutral_gross_spread")
