"""Transparent benchmark-relative factor risk: Σ = B F Bᵀ + D.

Requires *actual supplied* monthly factor-proxy returns and dated benchmark
security weights. Never manufactures Barra/MSCI factors, price histories or
benchmark constituents when required evidence is absent.
"""
from __future__ import annotations

from pathlib import Path
import math
import numpy as np
import pandas as pd

from index_research.data import read_matrix
from . import research_next, service


def _read_factor_returns(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.is_symlink():
        raise ValueError("factor_returns.csv is required: date and actual named factor-proxy returns")
    frame=pd.read_csv(path)
    if not 1<=len(frame.columns)-1<=12 or frame.columns[0]!="date":
        raise ValueError("Factor return CSV must have date and 1–12 explicit factor series")
    date=pd.to_datetime(frame["date"],errors="raise")
    if date.isna().any() or date.duplicated().any() or not date.is_monotonic_increasing:
        raise ValueError("Factor-return dates must be unique and chronological")
    out=frame.drop(columns="date").apply(pd.to_numeric,errors="raise")
    if out.isna().any().any() or not np.isfinite(out.to_numpy()).all() or (out.abs()>2).any().any():
        raise ValueError("Factor returns must be finite signed decimal returns, not prices")
    out.index=pd.DatetimeIndex(date)
    return out.astype(float)


def _read_benchmark_weights(path: Path, decision: pd.Timestamp,
                            tickers: pd.Index) -> tuple[pd.Series,str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("benchmark_weights.csv required: date,ticker,weight. "
                         "No artificial equal-weight benchmark is substituted.")
    rows=pd.read_csv(path)
    if not {"date","ticker","weight"}.issubset(rows.columns):
        raise ValueError("benchmark_weights.csv must contain date,ticker,weight")
    rows["date"]=pd.to_datetime(rows["date"],errors="raise")
    rows["weight"]=pd.to_numeric(rows["weight"],errors="raise")
    if rows["date"].isna().any() or rows[["date","ticker"]].duplicated().any():
        raise ValueError("Invalid or duplicate dated benchmark constituents")
    if rows["weight"].isna().any() or not np.isfinite(rows["weight"]).all() or (rows["weight"]<0).any():
        raise ValueError("Benchmark weights must be complete and nonnegative")
    earlier=rows.loc[rows["date"]<=decision]
    if earlier.empty:
        raise ValueError("No benchmark weights available before the analysis date")
    formation=earlier["date"].max()
    observed=earlier.loc[earlier["date"]==formation]
    if observed["ticker"].duplicated().any() or set(observed["ticker"])!=set(tickers):
        raise ValueError("Benchmark snapshot must list every modeled security, "
                         "including explicit zero-weight names; never infer missing weights")
    series=observed.set_index("ticker")["weight"].reindex(tickers)
    if abs(series.sum()-1)>1e-6:
        raise ValueError("Dated benchmark weights must sum to one")
    return series,formation.date().isoformat()


def attribution(run_id: str, as_of: str | None = None, lookback: int = 36) -> dict:
    if not 18<=lookback<=120:
        raise ValueError("Choose a lookback of 18–120 monthly observations")
    path=service._run_path(run_id)
    source=service.run_details(run_id)["source"]
    dataset_id=source.get("dataset_id")
    if not dataset_id:
        raise ValueError("Saved index run does not identify a source dataset")
    folder,dataset=service.dataset_path(dataset_id)
    saved=service.run_details(run_id)["meta"].get("input_sha256",{})
    for name,digest in saved.items():
        filename=folder/name
        if not filename.is_file() or filename.is_symlink() or research_next._file_sha(filename)!=digest:
            raise ValueError("Saved index input changed since the run: "+name)
    prices=read_matrix(folder/"prices.csv",positive=True)
    weights=pd.read_csv(path/"post_rebalance_weights.csv")
    if weights.empty or "date" not in weights:
        raise ValueError("No completed simulated index portfolio weights")
    weights["date"]=pd.to_datetime(weights["date"],errors="raise")
    if weights["date"].isna().any() or weights["date"].duplicated().any():
        raise ValueError("Invalid simulated index-weight dates")
    if as_of is None:
        row=weights.iloc[-1]
    else:
        target=pd.Timestamp(as_of)
        selected=weights.loc[weights["date"]==target]
        if len(selected)!=1:
            raise ValueError("Choose an exact archived post-rebalance weight date")
        row=selected.iloc[0]
    day=pd.Timestamp(row["date"])
    if day not in prices.index:
        raise ValueError("Saved weights and monthly prices must share a calendar")
    if set(weights.columns)-{"date"}!=set(prices.columns):
        raise ValueError("Saved holdings do not match source-universe columns")
    portfolio=pd.to_numeric(row.drop(labels="date"),errors="raise").reindex(prices.columns)
    if portfolio.isna().any() or (portfolio<0).any() or portfolio.sum()>1+1e-6:
        raise ValueError("Saved simulated holdings must be complete, nonnegative and <=100%")
    if portfolio.sum()<.99:
        raise ValueError("Portfolio contains material cash weight; explicit cash factor required "
                         "before a full-investment factor-risk comparison")
    benchmark,benchmark_date=_read_benchmark_weights(folder/"benchmark_weights.csv",
                                                       day,prices.columns)
    factors=_read_factor_returns(folder/"factor_returns.csv")
    returns=prices.pct_change(fill_method=None)
    eligible_dates=returns.index[(returns.index<day)&returns.index.isin(factors.index)]
    dates=eligible_dates[-lookback:]
    if len(dates)<max(18,factors.shape[1]*5):
        raise ValueError("Insufficient strictly prior common observations for factor estimation: "
                         f"{len(dates)} available; need at least {max(18,factors.shape[1]*5)}")
    names=list(prices.columns)
    if len(names)>250:
        raise ValueError("Bound research factor attribution to 250 securities")
    y=returns.loc[dates,names]
    x=factors.loc[dates]
    if y.isna().any().any() or not np.isfinite(y.to_numpy()).all():
        raise ValueError("Historical security returns contain gaps; no forward filling allowed")
    X=x.to_numpy(dtype=float)
    Y=y.to_numpy(dtype=float)
    if np.linalg.matrix_rank(X-X.mean(axis=0))<X.shape[1]:
        raise ValueError("Factor proxy returns are linearly dependent; covariance is not identifiable")
    Xreg=np.column_stack((np.ones(len(X)),X))
    params=np.linalg.lstsq(Xreg,Y,rcond=None)[0]
    betas=params[1:].T
    residual=Y-Xreg@params
    cov=np.cov(X,rowvar=False,ddof=1)*12.
    if np.ndim(cov)==0:
        cov=np.array([[float(cov)]])
    degrees=len(X)-Xreg.shape[1]
    if degrees<=2:
        raise ValueError("Too few residual degrees of freedom")
    specific=np.sum(residual*residual,axis=0)/degrees*12.
    if np.any(specific<0) or not np.isfinite(specific).all():
        raise ValueError("Invalid estimated specific risk")
    active=portfolio.to_numpy(dtype=float)-benchmark.to_numpy(dtype=float)
    exposed=active@betas
    systematic=float(exposed@cov@exposed)
    specific_risk=float((active**2)@specific)
    var=max(0,systematic+specific_risk)
    if var<=1e-15:
        contributions=[{"factor":f,"active_exposure":float(exposed[i]),
                        "variance_contribution":0.,"fraction_total_variance":None}
                       for i,f in enumerate(x.columns)]
        te=0.
    else:
        marginal=cov@exposed
        contributions=[{"factor":f,"active_exposure":float(exposed[i]),
                        "variance_contribution":float(exposed[i]*marginal[i]),
                        "fraction_total_variance":float(exposed[i]*marginal[i]/var)}
                       for i,f in enumerate(x.columns)]
        te=math.sqrt(var)
    return {
        "run_id":run_id,"dataset_id":dataset_id,
        "portfolio_weight_date":day.date().isoformat(),
        "benchmark_weights_available_date":benchmark_date,
        "factor_estimation_start":dates[0].date().isoformat(),
        "factor_estimation_end":dates[-1].date().isoformat(),
        "fitted_observations":len(dates),
        "factor_names":list(x.columns),"security_count":len(names),
        "annualized_active_tracking_error_estimate":float(te),
        "systematic_variance":systematic,"specific_variance":specific_risk,
        "systematic_fraction":float(systematic/var) if var>0 else None,
        "factor_contributions":contributions,
        "top_active_weights":[{"ticker":names[i],"active_weight":float(active[i])}
                              for i in np.argsort(-np.abs(active))[:15]],
        "source_sha256":{**saved,
            "factor_returns.csv":research_next._file_sha(folder/"factor_returns.csv"),
            "benchmark_weights.csv":research_next._file_sha(folder/"benchmark_weights.csv")},
        "method":"Ex-ante return-proxy factor betas from strictly prior monthly regressions; "
                 "Σ = B F Bᵀ + diag(residual variance), factor covariance annualized ×12.",
        "warning":"Estimated covariance and beta sensitivities are not realized risk, "
                  "not causal exposure and not licensed MSCI/Barra factor definitions. "
                  "Benchmark constituents and factor-return vintages must be externally "
                  "validated. Report is a conditional quantitative estimate, not an "
                  "independently audited index-risk attribution.",
    }
