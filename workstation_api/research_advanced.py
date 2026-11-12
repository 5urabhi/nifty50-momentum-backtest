"""Advanced QuantLab research operations over observed, versioned local data.

All outputs are built from existing price matrices and saved model artifacts.
No prices, factor labels, events, or statistical significance are fabricated.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from itertools import product
from pathlib import Path
import hashlib
import json
import math

import numpy as np
import pandas as pd
from scipy import stats

from index_research.data import read_matrix
from . import model_lab, model_registry, research_insights, research_library, service

MAX_POINTS = 600
MAX_ASSETS = 18
MAX_GRID_RUNS = 36
PLOT_KINDS = frozenset({"line", "scatter", "histogram", "kde", "qq",
                        "drawdown", "cumulative", "rolling_volatility", "correlation"})
TRANSFORMS = frozenset({"price", "return", "log_return", "base100", "zscore"})
GOALS = {
    "portfolio_allocation": {
        "label": "Compare portfolio allocation methods",
        "models": ["min_variance", "risk_parity", "max_diversification", "efficient_frontier"],
        "evaluation": "walk_forward",
        "explanation": "Compare long-only allocations on strictly later observations, with an equal-weight comparator.",
    },
    "volatility": {
        "label": "Understand changing volatility",
        "models": ["rolling_vol", "garch", "covariance", "bootstrap_sharpe"],
        "evaluation": "out_of_sample_volatility",
        "explanation": "Separate fitted volatility from one-step forecasts; inspect residual autocorrelation.",
    },
    "tail_risk": {
        "label": "Evaluate downside and tail risk",
        "models": ["historical_tail", "gaussian_tail", "student_t_tail", "evt"],
        "evaluation": "holdout_tail_diagnostics",
        "explanation": "Contrast empirical and parametric tails. Rare-event estimates need longer histories.",
    },
    "stochastic_models": {
        "label": "Explore stochastic dynamics",
        "models": ["gbm", "ou", "heston", "merton"],
        "evaluation": "simulation_sensitivity",
        "explanation": "Parameter sweeps compare explicitly synthetic path distributions, not stock forecasts.",
    },
    "derivatives": {
        "label": "Study option pricing sensitivities",
        "models": ["black_scholes", "binomial", "mc_option", "option_surface"],
        "evaluation": "analytical_vs_numerical",
        "explanation": "Option models are hypothetical unless independently calibrated to contemporaneous quotes.",
    },
    "factor_exposures": {
        "label": "Study return-series factor proxies",
        "models": ["pca", "covariance", "black_litterman"],
        "evaluation": "chronological_regression",
        "explanation": "Regress a portfolio proxy on observed return proxies, not inferred unpublished fundamentals.",
    },
}


def _finite(v) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and math.isfinite(float(v))


def _to_float(v):
    return float(v) if _finite(v) else None


def _price_data(dataset_id: str) -> tuple[pd.DataFrame, dict]:
    folder, record = service.dataset_path(dataset_id)
    if record.get("kind") == "synthetic":
        raise ValueError("Select observed market prices; demonstration fixtures cannot be labeled historical.")
    if not record.get("has_prices"):
        raise ValueError("Dataset does not have a price matrix")
    source = "daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
    path = folder / source
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError("Dataset price file unavailable")
    frame = read_matrix(path, positive=True).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    if frame.empty:
        raise ValueError("No usable observed price rows")
    info = {"dataset_id": dataset_id, "dataset": record.get("label", dataset_id),
            "dataset_kind": record.get("kind"), "source_file": source,
            "source_sha256": research_insights.file_sha256(path),
            "from_date": frame.index[0].date().isoformat(),
            "to_date": frame.index[-1].date().isoformat(),
            "frequency": "daily" if source == "daily_prices.csv" else "monthly",
            "annualization": 252 if source == "daily_prices.csv" else 12,
            "note": "Observational prices are not independently adjusted or certified total returns."}
    return frame, info


def columns(dataset_id: str) -> dict:
    frame, info = _price_data(dataset_id)
    return {"source": info, "columns": [str(c) for c in frame.columns[:250]],
            "total_columns": frame.shape[1], "total_dates": len(frame),
            "warning": "Select price columns by their actual dataset labels. The source may contain unadjusted closes."}


def _selected(frame: pd.DataFrame, fields: list[str], first: str | None = None,
              last: str | None = None) -> pd.DataFrame:
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_ASSETS or len(set(fields)) != len(fields):
        raise ValueError("Choose one to eighteen distinct observed columns")
    if any(name not in frame.columns for name in fields):
        raise ValueError("Selected column is not available in this dataset")
    selection = frame[fields].copy()
    if first:
        date.fromisoformat(first)
        selection = selection.loc[selection.index >= pd.Timestamp(first)]
    if last:
        date.fromisoformat(last)
        selection = selection.loc[selection.index <= pd.Timestamp(last)]
    if len(selection) < 5:
        raise ValueError("At least five selected price dates are needed")
    return selection


def _transform(frame: pd.DataFrame, transform: str) -> pd.DataFrame:
    if transform not in TRANSFORMS:
        raise ValueError("Unknown numerical transformation")
    if transform == "price":
        return frame
    if transform == "base100":
        result = frame.copy()
        for col in result:
            clean = result[col].dropna()
            if clean.empty or clean.iloc[0] <= 0:
                raise ValueError("Base-100 requires a positive starting price")
            result[col] = 100 * result[col] / clean.iloc[0]
        return result
    if transform == "zscore":
        result = frame.copy()
        for col in result:
            avg, sigma = result[col].mean(), result[col].std(ddof=1)
            if not _finite(sigma) or sigma <= 1e-12:
                raise ValueError("Z-score requires non-constant observations")
            result[col] = (result[col] - avg) / sigma
        return result
    returns = frame.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan)
    if transform == "log_return":
        with np.errstate(divide="ignore", invalid="ignore"):
            returns = np.log(frame / frame.shift(1))
        returns = returns.replace([np.inf,-np.inf],np.nan)
    return returns


def _downsample(data: pd.DataFrame, max_points: int = MAX_POINTS) -> pd.DataFrame:
    if len(data) <= max_points:
        return data
    # Deterministic endpoint-preserving sampling for viewport speed. Full data
    # remains in the canonical source file; no compressed samples are added to it.
    indices = np.linspace(0, len(data)-1, max_points, dtype=int)
    return data.iloc[np.unique(indices)]


def build_plot(dataset_id: str, fields: list[str], *, kind: str = "line",
               transform: str = "return", first: str | None = None, last: str | None = None,
               lookback: int = 20, title: str | None = None) -> dict:
    if kind not in PLOT_KINDS:
        raise ValueError("Unsupported Plot Builder visualization")
    if not 2 <= lookback <= 252:
        raise ValueError("Rolling window must contain 2–252 observed rows")
    frame, source = _price_data(dataset_id)
    raw = _selected(frame, fields, first, last)
    transformed = _transform(raw, transform)
    if kind in {"drawdown","cumulative","rolling_volatility","correlation"}:
        # Always use returns, never sum prices as if they were portfolio wealth.
        transformed = _transform(raw, "return")
    if kind == "correlation":
        if len(fields) < 2:
            raise ValueError("Correlation heatmap requires at least two asset columns")
        obs = transformed.dropna(how="any")
        if len(obs) < 12:
            raise ValueError("At least twelve complete return rows needed for correlations")
        corr = obs.corr()
        plot = {"kind":"heatmap2d","title":title or "Observed return correlations",
                "labels":fields,"values":corr.values.tolist(),
                "x_label":"Observed assets","y_label":"Observed assets"}
        count = len(obs)
    elif kind == "scatter":
        if len(fields) != 2:
            raise ValueError("Scatter plot requires exactly two distinct numeric series")
        valid = transformed[fields].dropna()
        if len(valid)<5: raise ValueError("At least five paired observations are required")
        valid = _downsample(valid)
        plot = {"kind":"scatter2d","title":title or "Observed scatter: "+fields[0]+" vs "+fields[1],
                "x":[float(v) for v in valid[fields[0]]],
                "y":[float(v) for v in valid[fields[1]]],
                "x_label":fields[0]+" ("+transform+")","y_label":fields[1]+" ("+transform+")"}
        count = len(valid)
    elif kind in {"histogram","kde","qq"}:
        if len(fields) != 1:
            raise ValueError(kind + " needs exactly one series")
        s = transformed[fields[0]].dropna()
        if len(s)<12: raise ValueError("Distribution plots need at least 12 valid observations")
        if len(s)>30000:
            # Deterministic decimation is labeled, not an invented sample.
            s = s.iloc[np.linspace(0,len(s)-1,30000,dtype=int)]
        vals = s.to_numpy(dtype=float)
        if kind=="histogram":
            counts, edges = np.histogram(vals,bins=min(60,max(10,int(math.sqrt(len(vals))))))
            x=((edges[:-1]+edges[1:])/2).tolist()
            plot={"kind":"histogram2d","title":title or "Observed "+fields[0]+" distribution",
                  "x":x,"traces":[{"name":"Observed frequency","y":counts.tolist()}],
                  "x_label":transform,"y_label":"Frequency"}
        elif kind=="kde":
            if np.std(vals,ddof=1) <= 1e-12:
                raise ValueError("KDE is undefined for a constant series")
            estimator = stats.gaussian_kde(vals)
            low,high=np.quantile(vals,[.001,.999])
            width=max(high-low,np.std(vals))
            xx=np.linspace(low-.1*width,high+.1*width,180)
            plot=model_lab.xy(title or "Kernel density: "+fields[0],xx.tolist(),
                  [{"name":"Gaussian kernel density","y":estimator(xx).tolist()}],
                  transform,"Estimated density")
        else:
            sorted_values=np.sort(vals)
            normal_q=stats.norm.ppf((np.arange(len(vals))+.5)/len(vals))
            select=np.linspace(0,len(vals)-1,min(MAX_POINTS,len(vals)),dtype=int)
            plot={"kind":"scatter2d","title":title or "Normal Q–Q: "+fields[0],
                  "x":normal_q[select].tolist(),"y":sorted_values[select].tolist(),
                  "x_label":"Theoretical standard-normal quantiles",
                  "y_label":"Empirical "+transform+" quantiles"}
        count=len(vals)
    else:
        data = transformed
        ylabel = transform.replace("_"," ")
        if kind=="drawdown":
            wealth=(1+transformed).cumprod()
            data=wealth.div(wealth.cummax()).sub(1)
            ylabel="Fractional peak-to-trough drawdown"
        elif kind=="cumulative":
            data=100*(1+transformed).cumprod()
            ylabel="Illustrative wealth index, base 100"
        elif kind=="rolling_volatility":
            data=transformed.rolling(lookback,min_periods=lookback).std(ddof=1)*math.sqrt(source["annualization"])
            ylabel="Annualized rolling volatility"
        data = data.dropna(how="all")
        if len(data)<2:
            raise ValueError("Selected data do not contain enough valid output rows")
        count=len(data)
        compact=_downsample(data)
        traces=[{"name":col,"y":[_to_float(v) for v in compact[col]]} for col in fields]
        plot=model_lab.xy(title or kind.replace("_"," ").title(),[idx.date().isoformat() for idx in compact.index],
                          traces,"Observed date",ylabel)
    return {"plot":plot,"source":source,"sample_observations":count,
            "displayed_observations":len(plot.get("x",[])) if "x" in plot else count,
            "settings":{"kind":kind,"fields":fields,"transform":transform,
                        "first":first,"last":last,"lookback":lookback},
            "warning":"Charts are descriptive observations. Unadjusted prices, corporate actions, "
                      "dividends, survivorship, trading costs and stale sources require independent review."}


def _autocorr(values: np.ndarray, lag: int) -> float:
    if lag >= len(values) or np.std(values)<=1e-14:
        return float("nan")
    return float(np.corrcoef(values[:-lag],values[lag:])[0,1])


def diagnose(dataset_id: str, asset: str, *, start: str | None = None,
             end: str | None = None) -> dict:
    prices, source = _price_data(dataset_id)
    samples=_selected(prices,[asset],start,end)
    series=samples[asset].pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan).dropna()
    x=series.to_numpy(dtype=float)
    n=len(x)
    if n<30: raise ValueError("At least thirty valid return observations are required for diagnostics")
    sd=float(np.std(x,ddof=1))
    if sd <= 1e-12: raise ValueError("Diagnostics are undefined for an effectively constant return series")
    jb=stats.jarque_bera(x)
    # Ljung-Box with sample autocorrelations; chi-square approximation.
    lag=min(10,max(2,n//10))
    rho=np.array([_autocorr(x,i) for i in range(1,lag+1)])
    q=float(n*(n+2)*np.sum(np.nan_to_num(rho)**2/(n-np.arange(1,lag+1))))
    lbp=float(stats.chi2.sf(q,lag))
    # ARCH diagnostic: regress demeaned squared errors against their lags.
    arch_lags=min(5,max(1,n//20))
    sq=(x-np.mean(x))**2
    yy=sq[arch_lags:]
    xx=np.column_stack([np.ones(len(yy))]+[sq[arch_lags-k:n-k] for k in range(1,arch_lags+1)])
    beta=np.linalg.lstsq(xx,yy,rcond=None)[0]
    fitted=xx@beta
    tss=float(np.sum((yy-np.mean(yy))**2))
    r2=1-float(np.sum((yy-fitted)**2))/tss if tss>0 else 0.
    lm=max(0.,len(yy)*r2)
    arch_p=float(stats.chi2.sf(lm,arch_lags))
    ann=source["annualization"]
    return {"asset":asset,"source":source,"observations":n,
            "statistics":{"mean_return":float(np.mean(x)),
                          "annualized_volatility":sd*math.sqrt(ann),
                          "skewness":float(stats.skew(x,bias=False)),
                          "excess_kurtosis":float(stats.kurtosis(x,fisher=True,bias=False)),
                          "lag_1_autocorrelation":_to_float(_autocorr(x,1)),
                          "jarque_bera":float(jb.statistic),"jarque_bera_p":float(jb.pvalue),
                          "ljung_box_lag":lag,"ljung_box_q":q,"ljung_box_p":lbp,
                          "arch_lags":arch_lags,"arch_lm":lm,"arch_lm_p":arch_p},
            "interpretation":{
                "normality":"Reject normality at nominal 5%." if jb.pvalue<.05 else
                            "Insufficient evidence to reject normality at 5%.",
                "autocorrelation":"Some serial correlation indicated at nominal 5%." if lbp<.05 else
                            "No serial correlation detected at nominal 5%.",
                "conditional_variance":"Potential volatility clustering at nominal 5%." if arch_p<.05 else
                            "ARCH signal not detected at nominal 5%."},
            "warning":"Exploratory diagnostics, not proof of market efficiency or independent predictive skill. "
                      "Approximate p-values assume suitable sampling and may fail under nonstationarity."}


def factor_proxy_attribution(dataset_id: str, target: str, factors: list[str], *,
                             training_fraction: float = .7) -> dict:
    if not isinstance(factors,list) or not 1<=len(factors)<=6 or target in factors or len(set(factors))!=len(factors):
        raise ValueError("Choose 1–6 distinct return-series proxies excluding the target")
    if not .5<=training_fraction<=.85:
        raise ValueError("Training fraction must lie between 0.50 and 0.85")
    prices, source=_price_data(dataset_id)
    frame=_selected(prices,[target]+factors)
    returns=frame.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan).dropna()
    n=len(returns)
    if n < max(75,12*(len(factors)+1)):
        raise ValueError("Need at least 75 aligned returns and 12 per regression parameter")
    split=int(n*training_fraction)
    if n-split<20:
        raise ValueError("Need at least 20 later holdout returns")
    xx=returns[factors].to_numpy(dtype=float)
    yy=returns[target].to_numpy(dtype=float)
    x=np.column_stack([np.ones(n),xx])
    xtrain,xtest=x[:split],x[split:]
    ytrain,ytest=yy[:split],yy[split:]
    if np.linalg.matrix_rank(xtrain)<xtrain.shape[1]:
        raise ValueError("Observed factors are collinear; remove a factor proxy")
    beta=np.linalg.lstsq(xtrain,ytrain,rcond=None)[0]
    resid=ytrain-xtrain@beta
    dof=len(ytrain)-xtrain.shape[1]
    sigma2=float(resid@resid/dof)
    cov=sigma2*np.linalg.inv(xtrain.T@xtrain)
    se=np.sqrt(np.diag(cov))
    tstats=np.divide(beta,se,out=np.zeros_like(beta),where=se>0)
    pvalues=2*stats.t.sf(np.abs(tstats),dof)
    pred=xtest@beta
    base=np.mean(ytrain)
    mse=float(np.mean((ytest-pred)**2))
    mse_base=float(np.mean((ytest-base)**2))
    r2_oos=1-mse/mse_base if mse_base>1e-14 else None
    factors_info=[{"factor_proxy":name,"beta":float(beta[i+1]),
                   "standard_error":float(se[i+1]),"t_stat":float(tstats[i+1]),
                   "nominal_p_value":float(pvalues[i+1])} for i,name in enumerate(factors)]
    return {"target":target,"source":source,"factor_proxies":factors_info,
            "intercept":float(beta[0]),"train_observations":split,
            "holdout_observations":len(ytest),
            "train_to":returns.index[split-1].date().isoformat(),
            "holdout_from":returns.index[split].date().isoformat(),
            "holdout_r2_vs_train_mean":_to_float(r2_oos),
            "holdout_mse":mse,"holdout_baseline_mse":mse_base,
            "plot":model_lab.xy("Later-period factor-proxy predictions",
                [d.date().isoformat() for d in returns.index[split:]],
                [{"name":"Observed "+target,"y":ytest.tolist()},
                 {"name":"Train-fitted proxy model","y":pred.tolist()}],
                "Observed holdout date","Return"),
            "warning":"These are user-selected observed return-series proxies, not "
                      "licensed benchmark factors or publication-dated fundamental exposures. "
                      "OLS standard errors are in-sample and assume iid errors; verify HAC "
                      "and multiple-testing corrections before inference."}


def significance(study_ids: list[str], *, seed: int = 2026) -> dict:
    if not isinstance(study_ids,list) or not 1<=len(study_ids)<=6 or len(set(study_ids))!=len(study_ids):
        raise ValueError("Choose 1–6 distinct chronological validation studies")
    if not 0<=seed<=2**32-1: raise ValueError("Invalid bootstrap seed")
    outputs=[]
    rng=np.random.default_rng(seed)
    for study_id in study_ids:
        source=research_insights.study_returns_path(study_id)
        record=research_library.get(study_id)
        frame=pd.read_csv(source,usecols=["date","strategy","equal_weight"])
        if len(frame)<30: raise ValueError("Inference needs at least 30 untouched observations")
        active=pd.to_numeric(frame["strategy"],errors="coerce")-pd.to_numeric(frame["equal_weight"],errors="coerce")
        if active.isna().any() or not np.isfinite(active).all():
            raise ValueError("Study contains invalid active returns")
        a=active.to_numpy(dtype=float)
        n=len(a); mean=float(np.mean(a))
        # Newey-West HAC SE for mean with Bartlett kernel; p-value normal
        # approximation, explicitly labeled asymptotic.
        lag=min(10,max(1,int(n**.25)))
        demean=a-mean
        variance=float(demean@demean/n)
        for k in range(1,lag+1):
            cov=float(np.dot(demean[k:],demean[:-k])/n)
            variance+=2*(1-k/(lag+1))*cov
        se=math.sqrt(max(0,variance)/n)
        tstat=mean/se if se>1e-14 else None
        p=float(2*stats.norm.sf(abs(tstat))) if tstat is not None else None
        block=min(10,max(2,int(math.sqrt(n))))
        boot=np.empty(500)
        for b in range(500):
            picks=[]
            while len(picks)<n:
                start=int(rng.integers(0,n))
                picks.extend(((start+np.arange(block))%n).tolist())
            boot[b]=np.mean(a[np.array(picks[:n])])
        ci=np.quantile(boot,[.025,.975])
        meta=record["payload"].get("source") or {}
        outputs.append({"study_id":study_id,"name":record["title"],"observations":n,
                        "frequency":meta.get("frequency"),"active_mean":mean,
                        "newey_west_lag":lag,"newey_west_se":se,
                        "normal_approx_statistic":_to_float(tstat),
                        "nominal_p_value":p,"block_size":block,
                        "bootstrap_mean_ci95":[float(ci[0]),float(ci[1])],
                        "bootstrap_seed":seed})
    # Holm step-down familywise p-value adjustment for tested hypotheses.
    indexed=sorted([(i,o["nominal_p_value"]) for i,o in enumerate(outputs)
                   if o["nominal_p_value"] is not None],key=lambda item:item[1])
    running=0.
    m=len(indexed)
    for rank,(i,p) in enumerate(indexed):
        running=max(running,(m-rank)*p)
        outputs[i]["holm_adjusted_p_value"]=min(1.,running)
    return {"studies":outputs,"hypothesis":"Mean strategy-minus-equal-weight return = 0",
            "correction":"Holm familywise multiplicity correction on available p-values",
            "warning":"Exploratory retrospective inference. Bootstrap dependence assumptions, "
                      "selection over many configurations, PIT membership, trading costs "
                      "and independently untouched tests still require evidence."}


def grid_estimate(model_id: str, axes: dict[str,list], params: dict | None = None) -> dict:
    spec=model_registry.CATALOG.get(model_id)
    if not spec: raise ValueError("Unknown registered model")
    if not isinstance(axes,dict) or not 1<=len(axes)<=2:
        raise ValueError("Choose one or two numerical parameters")
    lengths=[]
    permitted={p["key"]:p for p in spec["parameters"] if p["type"] in {"number","integer"}}
    for key, values in axes.items():
        if key not in permitted or not isinstance(values,list) or not 2<=len(values)<=12:
            raise ValueError("Every sweep axis requires 2–12 registered numerical values")
        if len(set(map(str,values)))!=len(values):
            raise ValueError("Sweep-axis values must be distinct")
        lengths.append(len(values))
    total=math.prod(lengths)
    if total>MAX_GRID_RUNS:
        raise ValueError(f"Grid has {total} runs, limit {MAX_GRID_RUNS}. Narrow the grid.")
    base=model_registry.validate_parameters(model_id,params or {})
    keys=list(axes)
    configurations=[]
    for choices in product(*(axes[k] for k in keys)):
        settings={**base,**dict(zip(keys,choices))}
        configurations.append((dict(zip(keys,choices)),
            model_registry.validate_parameters(model_id,settings)))
    horizon=max(int(p.get("steps",1)) for _,p in configurations)
    paths=max(int(p.get("paths",1)) for _,p in configurations)
    relative_units=total*horizon*paths if spec["mode"]=="synthetic" else total
    return {"model_id":model_id,"axes":axes,"configurations":configurations,
            "run_count":total,"estimated_relative_work_units":relative_units,
            "calibration":"Work units are not a wall-clock-time or cloud-compute estimate.",
            "warning":"Confirm requested numerical workload and data readiness before executing."}


def grid_sweep(model_id: str, dataset_id: str | None, axes: dict[str,list],
               params: dict | None = None, *, metric_name: str | None = None) -> dict:
    estimated=grid_estimate(model_id,axes,params)
    if model_registry.CATALOG[model_id]["mode"]=="historical" and not dataset_id:
        raise ValueError("Historical grid requires an observed dataset")
    result_rows=[]
    for controls,settings in estimated["configurations"]:
        run=model_lab.run_model(model_id,dataset_id,settings)
        saved=model_lab.save_result(run)
        metrics={m["label"]:float(m["value"]) for m in run.get("metrics",[])
                 if _finite(m.get("value"))}
        result_rows.append({"run_id":saved["run_id"],"params":controls,
                            "metrics":metrics})
    common=set.intersection(*(set(row["metrics"]) for row in result_rows))
    chosen=metric_name or (sorted(common)[0] if common else None)
    if chosen and chosen not in common:
        raise ValueError("Metric is not available across the grid")
    keys=list(axes)
    plot=None
    if chosen:
        if len(keys)==1:
            plot=model_lab.xy("Sensitivity: "+chosen,[r["params"][keys[0]] for r in result_rows],
                  [{"name":chosen,"y":[r["metrics"][chosen] for r in result_rows]}],
                  keys[0],chosen)
        else:
            xkeys,ykeys=axes[keys[0]],axes[keys[1]]
            lookup={tuple(r["params"][k] for k in keys):r["metrics"][chosen] for r in result_rows}
            values=[[lookup[(x,y)] for x in xkeys] for y in ykeys]
            # Heatmaps now support arbitrary finite metrics and explicit scale.
            plot={"kind":"heatmap2d","title":"Grid response: "+chosen,
                  "labels":[str(v) for v in xkeys], "row_labels":[str(v) for v in ykeys],
                  "values":values,"scale":"sequential","x_label":keys[0],"y_label":keys[1]}
    report={"model_id":model_id,"dataset_id":dataset_id,
            "source_sha256":next((r.get("source_sha256") for r in
                [model_lab.read_saved_model(row["run_id"]) for row in result_rows] if r.get("source_sha256")),None),
            "axes":axes,"run_count":len(result_rows),"metric_name":chosen,
            "runs":result_rows,"plot":plot,"relative_work_units":estimated["estimated_relative_work_units"],
            "warning":"Parameter selection on these results is exploratory. Preserve an independent "
                      "untouched test period before claims of out-of-sample predictive skill."}
    saved=research_library.create("study","Grid sweep: "+model_registry.CATALOG[model_id]["title"],
                                  report,tags=["parameter-grid"])
    return {**report,"study_id":saved["id"]}


def guided(goal: str, dataset_id: str | None) -> dict:
    spec=GOALS.get(goal)
    if not spec: raise ValueError("Choose a supported research objective")
    items=[]
    for model_id in spec["models"]:
        m=model_registry.CATALOG[model_id]
        info={"model_id":model_id,"title":m["title"],"mode":m["mode"],
              "minimum":m["min_observations"],"formula":m["formula"],
              "description":m["description"]}
        if m["mode"]=="historical" and dataset_id:
            from . import model_data_manager
            try:
                requirement=model_data_manager.inspect(model_id,dataset_id)
                info.update(readiness=requirement["status"], observed=requirement.get("common_returns"),
                            target=requirement.get("target_returns"), can_extend=requirement.get("can_download"))
            except (FileNotFoundError,ValueError) as exc:
                info.update(readiness="unavailable",readiness_message=str(exc))
        items.append(info)
    return {"goal":goal,"title":spec["label"],"explanation":spec["explanation"],
            "suggested_evaluation":spec["evaluation"],"models":items,
            "steps":["Select trustworthy market-data inputs where required",
                     "Inspect sample sufficiency (+20% target) and model assumptions",
                     "Save each configuration and run Python research models",
                     "Compare compatible saved curves; use split views otherwise",
                     "Evaluate later observations where mathematically possible",
                     "Document limitations and export a reproducible report"],
            "warning":"These are rule-based recommendations from the registered model catalog, "
                      "not an AI performance ranking or assurance of profitability."}
