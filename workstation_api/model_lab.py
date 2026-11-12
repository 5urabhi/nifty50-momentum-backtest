"""Local, deterministic model laboratory for mathematical finance research.

All modeling uses existing index_research implementations and immutable
per-request input validation. No broker orders, network data fetching, secret
access, synthetic substitute for missing real history, or claims of OOS alpha.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import uuid
import math
import numpy as np
import pandas as pd

from index_research import advanced_models, derivatives, inference, math_models
from index_research import model_validation, portfolio_extensions, portfolio_math, tail_risk
from index_research.data import read_matrix
from . import model_registry, service

CATALOG = model_registry.CATALOG
PER_YEAR = {"daily": 252, "monthly": 12}


def metric(name: str, value: float | int | str | None, unit: str = "") -> dict:
    if isinstance(value, (float, np.floating)) and not math.isfinite(value):
        value = None
    return {"label": name, "value": float(value) if isinstance(value, (np.floating, np.integer))
            else value, "unit": unit}


def xy(title: str, x: list, traces: list[dict], x_label: str, y_label: str,
       *, kind: str = "line2d", band: dict | None = None) -> dict:
    result = {"kind": kind, "title": title, "x": x, "traces": traces,
              "x_label": x_label, "y_label": y_label}
    if band:
        result["band"] = band
    return result


def line(name: str, values, color: str | None = None) -> dict:
    series = {"name": name, "y": [float(v) if np.isfinite(v) else None for v in values]}
    if color:
        series["color"] = color
    return series


def fan(title: str, paths: np.ndarray, horizon: float, x_label: str) -> dict:
    if not np.isfinite(paths).all():
        raise ValueError("Simulation produced a nonfinite path; reduce volatility or horizon")
    q = np.percentile(paths, [5, 50, 95], axis=1)
    stride = max(1, math.ceil((len(q[0])-1)/120))
    indices = list(range(0, len(q[0]), stride))
    if indices[-1] != len(q[0]) - 1:
        indices.append(len(q[0])-1)
    return xy(title, [round(float(i * horizon / (paths.shape[0]-1)),5) for i in indices],
              [line("5th percentile",q[0,indices]),
               line("Median",q[1,indices]),
               line("95th percentile",q[2,indices])],
              x_label, "Simulated level", kind="fan2d",
              band={"lower":q[0,indices].tolist(),"upper":q[2,indices].tolist()})


def surface(title: str, x, y, matrix, x_label: str, y_label: str, z_label: str) -> dict:
    arr=np.asarray(matrix, dtype=float)
    if (arr.ndim != 2 or arr.shape != (len(y),len(x)) or arr.size > 1000
            or not np.isfinite(arr).all()):
        raise ValueError("Invalid theoretical surface dimensions or results")
    return {"kind":"surface3d","title":title,"x":list(map(float,x)),
            "y":list(map(float,y)),"z":arr.tolist(),
            "x_label":x_label,"y_label":y_label,"z_label":z_label}


def histogram(title: str, values: pd.Series, tail: float | None = None) -> dict:
    counts,edges=np.histogram(values.to_numpy(dtype=float),bins=23)
    centers=((edges[:-1]+edges[1:])/2).tolist()
    result=xy(title,centers,[line("Observed sessions",counts)],"Loss per period","Count",kind="bar2d")
    if tail is not None and np.isfinite(tail):
        result["threshold"] = float(tail)
    return result


def _historical_input(dataset_id: str, required: int, assets: int) -> tuple[pd.DataFrame, dict]:
    if not dataset_id:
        raise ValueError("Choose an observed research dataset for this model")
    folder,record=service.dataset_path(dataset_id)
    selected_file="daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
    if not record.get("has_prices"):
        raise ValueError("Selected dataset has no verified local prices")
    prices=read_matrix(folder/selected_file,positive=True)
    if len(prices.columns)<2:
        raise ValueError("At least two securities are needed for portfolio analysis")
    returns=prices.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan)
    eligible=sorted((name for name in returns.columns
                     if int(returns[name].notna().sum())>=required),
                    key=lambda name:(-int(returns[name].notna().sum()),name))
    if len(eligible)<2:
        raise ValueError(f"Not enough securities with {required} observed common daily/monthly returns")
    if len(eligible) < assets:
        raise ValueError(f"Need {assets} securities with at least {required} returns; "
                         f"found {len(eligible)}. Choose fewer assets or extend the market history.")
    names=eligible[:assets]
    aligned=returns[names].dropna()
    if len(aligned)<required:
        raise ValueError(f"Need at least {required} common observed returns across {len(names)} assets; "
                         f"found {len(aligned)}. Use a longer date range or fewer assets. "
                         "Missing prices are never forward-filled.")
    if (aligned.std(ddof=1) <= 1e-10).any():
        raise ValueError("Selected return series includes a constant asset")
    frequency="daily" if selected_file=="daily_prices.csv" else "monthly"
    source={
        "dataset_id":dataset_id,
        "dataset_label":record["label"],
        "dataset_kind":record.get("kind","unverified"),
        "frequency":frequency,
        "periods_per_year":PER_YEAR[frequency],
        "observations":len(aligned),
        "from_date":aligned.index.min().date().isoformat(),
        "to_date":aligned.index.max().date().isoformat(),
        "source_file":selected_file,
        "assets":names,
        "dataset_basis":record.get("basis",""),
        "benchmark_kind":record.get("benchmark_kind","missing"),
        "selection_rule":"Most complete observed return histories, tie-broken by symbol",
        "eligible_asset_count":len(eligible),
        "missing_prices_forward_filled":False,
    }
    return aligned, source


def readiness(dataset_id: str) -> dict:
    folder,record=service.dataset_path(dataset_id)
    source_file="daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
    if not record.get("has_prices"):
        return {"dataset_id":dataset_id,"has_prices":False,"message":"Dataset lacks prices",
                "frequency":None,"observed_dates":0,"eligible_assets":0}
    prices=read_matrix(folder/source_file,positive=True)
    returns=prices.pct_change(fill_method=None)
    count=returns.notna().sum()
    return {
        "dataset_id":dataset_id, "has_prices":True,
        "frequency":"daily" if source_file=="daily_prices.csv" else "monthly",
        "observed_dates":len(prices),
        "eligible_assets_60":int((count>=60).sum()),
        "eligible_assets_180":int((count>=180).sum()),
        "sample_start":prices.index.min().date().isoformat(),
        "sample_end":prices.index.max().date().isoformat(),
        "benchmark_kind":record.get("benchmark_kind"),
        "warning":("Synthetic fixture: data are generated and are not observed market prices."
                   if record.get("kind")=="synthetic" else
                   "Observed-price availability is not audited total-return investability."),
    }


def _optimization_metrics(w: pd.Series, returns: pd.DataFrame, covariance: pd.DataFrame) -> list:
    if not np.isclose(w.sum(),1,atol=1e-5) or (w < -1e-6).any():
        raise ValueError("Optimizer returned infeasible asset weights")
    risk=float(np.sqrt(max(w.to_numpy()@covariance.to_numpy()@w.to_numpy(),0)))
    expected=float(returns.mean().dot(w)*252)  # replaced by caller's frequency below
    return [metric("Portfolio annualized volatility",risk,"decimal"),
            metric("Portfolio expected return, daily convention",expected,"decimal")]


def run_model(model_id: str, dataset_id: str | None = None,
              raw_parameters: dict | None = None) -> dict:
    params=model_registry.validate_parameters(model_id,raw_parameters or {})
    spec=CATALOG[model_id]
    response={
        "model_id":model_id,"title":spec["title"],"group":spec["group"],
        "mode":spec["mode"],"formula":spec["formula"],"params":params,
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source":None,"metrics":[],"plots":[],"table":[],
        "notes":[],"limitations":[],
    }
    plots=response["plots"]
    metrics=response["metrics"]
    warnings=response["limitations"]
    seed=int(params.get("seed",2026))
    if spec["mode"]=="historical":
        minimum = spec["min_observations"]
        if model_id == "rolling_vol":
            minimum = max(minimum, int(params["train_window"]) + 30)
        data,meta=_historical_input(dataset_id or "", minimum,int(params.get("assets",8)))
        response["source"]=meta
        if meta.get("dataset_kind")=="synthetic":
            warnings.append("SYNTHETIC FIXTURE: input prices were generated for a demo. "
                            "These are not observed market prices; fitted results "
                            "must not be reported as empirical backtests.")
        obs=len(data)
        annual=meta["periods_per_year"]
        basket=data.mean(axis=1)
        warnings.append("DESCRIPTIVE IN-SAMPLE calculation. Selection favors data completeness; "
                        "not a point-in-time investable portfolio or out-of-sample validation.")
        warnings.append("Historical close series may omit dividend reinvestment and corporate actions. "
                        "No missing prices were forward-filled.")
    else:
        data=None
        meta=None
        annual=252
        if spec["mode"]=="synthetic":
            warnings.append("Seeded synthetic/theoretical simulation. No empirical calibration or predictive claim.")
        else:
            warnings.append("Theoretical formula with manually specified inputs, not observed executable market prices.")
        if dataset_id:
            response["notes"].append("Selected dataset was not used by this theoretical/synthetic model.")

    if model_id in {"gbm","ou","heston","merton"}:
        steps=int(params["steps"])
        count=int(params["paths"])
        horizon=float(params["years"])
        if model_id=="gbm":
            paths=math_models.simulate_gbm(params["spot"],params["drift"],
                params["volatility"],horizon,steps,count,seed)
        elif model_id=="ou":
            paths=advanced_models.simulate_ou(params["initial"],params["mean"],
                params["reversion"],params["diffusion"],horizon/steps,steps,count,seed)
        elif model_id=="heston":
            simulated=derivatives.heston_paths(params["spot"],params["initial_variance"],horizon,
                steps,count,rate=params["risk_free_rate"],kappa=params["mean_reversion"],
                long_variance=params["long_variance"],vol_of_vol=params["vol_of_vol"],
                rho=params["rho"],seed=seed)
            paths=simulated["prices"]
            warnings.append(simulated["warning"])
        else:
            paths=derivatives.merton_jump_diffusion(params["spot"],horizon,steps,count,
                drift=params["drift"],vol=params["volatility"],
                jump_intensity=params["jump_intensity"],
                jump_mean_log=params["jump_mean_log"],
                jump_std_log=params["jump_std_log"],seed=seed)
        plots.append(fan(spec["title"]+" · simulated distribution",paths,horizon,"Time (years)"))
        terminal=np.asarray(paths[-1],dtype=float)
        metrics.extend([metric("Path count",count),
                        metric("Terminal median",float(np.median(terminal))),
                        metric("Terminal 5th percentile",float(np.quantile(terminal,.05))),
                        metric("Terminal 95th percentile",float(np.quantile(terminal,.95)))])
        response["table"]=[{"quantile":"5%","value":float(np.quantile(terminal,.05))},
                           {"quantile":"50%","value":float(np.quantile(terminal,.5))},
                           {"quantile":"95%","value":float(np.quantile(terminal,.95))}]
    elif model_id=="black_scholes":
        values=math_models.black_scholes(params["spot"],params["strike"],params["years"],
            params["risk_free_rate"],params["volatility"],params["option_type"],
            params["dividend_yield"])
        metrics.extend(metric(k.replace("_"," ").title(),v) for k,v in values.items())
        levels=np.linspace(max(1,params["spot"]*.65),params["spot"]*1.35,45)
        prices=[math_models.black_scholes(float(s),params["strike"],params["years"],
             params["risk_free_rate"],params["volatility"],params["option_type"],
             params["dividend_yield"])["price"] for s in levels]
        plots.append(xy("BSM option price vs underlying",levels.tolist(),
                        [line("BSM price",prices)],"Underlying spot","Option model value"))
    elif model_id=="binomial":
        steps=int(params["steps"])
        value=derivatives.binomial_option(params["spot"],params["strike"],params["years"],
            params["risk_free_rate"],params["volatility"],steps,params["option_type"],
            params["exercise"])
        metrics.extend([metric("Binomial model value",value),metric("Tree steps",steps)])
        ns=sorted(set([10,20,40,80,160,steps]))
        model_values=[derivatives.binomial_option(params["spot"],params["strike"],
               params["years"],params["risk_free_rate"],params["volatility"],n,
               params["option_type"],params["exercise"]) for n in ns]
        plots.append(xy("CRR discretization convergence",ns,[line("Binomial value",model_values)],
                        "Tree steps","Option model value"))
        warnings.append("American exercise can differ from European BSM; tree discretization and assumptions matter.")
    elif model_id=="implied_vol":
        result=derivatives.implied_volatility(params["market_price"],params["spot"],
            params["strike"],params["years"],params["risk_free_rate"],params["option_type"])
        metrics.append(metric("Implied volatility",result,"decimal annualized"))
        grid=np.linspace(max(.01,result*.45),min(5,result*1.55),48)
        options=[math_models.black_scholes(params["spot"],params["strike"],params["years"],
                params["risk_free_rate"],float(v),params["option_type"])["price"] for v in grid]
        plots.append(xy("Option price as a function of volatility",grid.tolist(),
                        [line("BSM model price",options),
                         line("Input option premium",[params["market_price"]]*len(grid))],
                        "Annualized volatility","Option premium"))
        warnings.append("User-provided premium; root-solved from BSM, not a market data feed.")
    elif model_id=="mc_option":
        ns=[200,500,1500,5000]
        estimates=[]
        last=None
        for count in ns:
            last=derivatives.monte_carlo_european(params["spot"],params["strike"],
                params["years"],params["risk_free_rate"],params["volatility"],
                paths=count,option=params["option_type"],seed=seed)
            estimates.append(last["price"])
        theoretical=math_models.black_scholes(params["spot"],params["strike"],
                params["years"],params["risk_free_rate"],params["volatility"],
                params["option_type"])["price"]
        metrics.extend([metric("Monte Carlo estimate",last["price"]),
                        metric("95% Monte Carlo CI low",last["ci95_lower"]),
                        metric("95% Monte Carlo CI high",last["ci95_upper"]),
                        metric("Analytical BSM comparator",theoretical)])
        plots.append(xy("Monte Carlo convergence and analytical BSM",ns,
                        [line("Antithetic Monte Carlo",estimates),
                         line("Analytical benchmark",[theoretical]*len(ns))],
                        "Simulated antithetic paths","Estimated option price"))
    elif model_id=="option_surface":
        spots=np.linspace(params["spot"]*.65,params["spot"]*1.35,21)
        vols=np.linspace(.08,.85,17)
        z=[[math_models.black_scholes(float(price),params["strike"],params["years"],
                 params["risk_free_rate"],float(vol),params["option_type"])["price"]
                 for price in spots] for vol in vols]
        plots.append(surface("Theoretical option-price response",spots,vols,z,
                             "Underlying spot","Annualized vol","Model premium"))
        metrics.append(metric("Grid points",len(spots)*len(vols)))
        warnings.append("Surface grid is an assumed spot/volatility grid, not traded option chain data.")
    elif model_id in {"garch","pca","covariance","rolling_vol"}:
        if model_id=="garch":
            fit=advanced_models.fit_garch11(basket)
            r=np.asarray(basket,dtype=float)
            center=100*(r-r.mean())
            h=np.empty(len(r),dtype=float)
            h[0]=np.var(center,ddof=1)
            for i in range(1,len(r)):
                h[i]=fit.omega*10000+fit.alpha*center[i-1]**2+fit.beta*h[i-1]
            vols=np.sqrt(h/10000*annual)
            metrics.extend([metric("Omega",fit.omega,"variance"),
                            metric("Alpha",fit.alpha),metric("Beta",fit.beta),
                            metric("Persistence α+β",fit.alpha+fit.beta),
                            metric("Next period forecast volatility",math.sqrt(fit.next_variance),"decimal")])
            dates=[x.date().isoformat() for x in basket.index]
            plots.append(xy("Fitted conditional volatility vs observed absolute return",dates,
                            [line("Fitted annualized σ",vols),
                             line("Observed |r| annualized proxy",np.abs(r)*math.sqrt(annual))],
                            "Observed date","Annualized volatility"))
            warnings.append("Gaussian GARCH estimates are fitted on the full sample, not out-of-sample forecast scores.")
        elif model_id=="pca":
            components=int(params["components"])
            valid=data.loc[:,data.std(ddof=1)>.000001]
            if valid.shape[1]<components:
                raise ValueError("Not enough variable securities for PCA components")
            result=advanced_models.principal_components(valid,n_components=components)
            ratios=np.asarray(result["explained_variance_ratio"])
            metrics.extend(metric(f"PC{i+1} variance explained",float(v),"fraction")
                           for i,v in enumerate(ratios))
            plots.append(xy("Explained variance by component",list(range(1,len(ratios)+1)),
                            [line("Explained share",ratios)],"Component","Variance share",kind="bar2d"))
            if components>=2:
                points=result["scores"]
                plots.append({"kind":"scatter2d","title":"PC1 vs PC2 · in-sample scores",
                              "x":points["PC1"].tolist(),"y":points["PC2"].tolist(),
                              "x_label":"PC1","y_label":"PC2"})
            response["table"]=[{"asset":str(i),**{k:float(v) for k,v in row.items()}}
                                for i,row in result["loadings"].iterrows()]
        elif model_id=="covariance":
            sample=math_models.sample_covariance(data,annual)
            shrink=math_models.shrinkage_covariance(data,params["shrinkage"],annual)
            ewma=math_models.ewma_covariance(data,params["decay"],annual)
            names=data.columns.tolist()
            metrics.extend([metric("Sample covariance trace",float(np.trace(sample))),
                            metric("Shrinkage covariance trace",float(np.trace(shrink))),
                            metric("EWMA covariance trace",float(np.trace(ewma)))])
            plots.append(xy("Asset volatility across covariance estimators",names,
                            [line("Sample",np.sqrt(np.diag(sample))),
                             line("Diagonal shrinkage",np.sqrt(np.diag(shrink))),
                             line("EWMA",np.sqrt(np.diag(ewma)))],
                            "Assets","Annualized σ",kind="bar2d"))
            plots.append({"kind":"heatmap2d","title":"Sample correlation matrix",
                          "labels":names,"values":data.corr().round(4).to_numpy().tolist(),
                          "x_label":"Assets","y_label":"Assets"})
            warnings.append("Shrinkage is fixed-intensity diagonal, not Ledoit–Wolf estimation.")
        else:
            train=int(params["train_window"])
            if len(basket)<train+12:
                raise ValueError(f"Walk-forward validation needs at least {train+12} observations")
            result=model_validation.rolling_volatility_forecasts(basket,
                   train_window=train,periods_per_year=annual,include_garch=False)
            scores=model_validation.variance_forecast_scores(result)
            metrics.extend([metric("Strict holdout sessions",len(result)),
                            metric("Train window",train)])
            plots.append(xy("One-step variance forecasts vs noisy realized proxy",
                            [d.date().isoformat() for d in result.index],
                            [line("Realized squared return",result["realized_variance"]),
                             line("Sample prior-window variance",result["sample_variance_forecast"]),
                             line("EWMA prior-window variance",result["ewma_variance_forecast"])],
                            "Holdout date","Variance"))
            response["table"]=scores.to_dict("records")
            warnings.append("Strict walk-forward: target dates were excluded from model fitting. "
                            "Realized squared return is a noisy variance proxy; not conditional variance truth.")
    elif model_id in {"min_variance","risk_parity","max_diversification",
                      "cvar","black_litterman","efficient_frontier","risk_surface"}:
        sigma=math_models.shrinkage_covariance(data,intensity=.25,periods_per_year=annual)
        mu=data.mean()*annual
        if model_id=="risk_surface":
            names=data.columns[:2].tolist()
            v=np.sqrt(np.diag(sigma.to_numpy()))[:2]
            weights=np.linspace(0,1,25)
            correlations=np.linspace(-.95,.95,21)
            z=[[math.sqrt(max(w*w*v[0]**2+(1-w)**2*v[1]**2
                +2*w*(1-w)*rho*v[0]*v[1],0))
                for w in weights] for rho in correlations]
            plots.append(surface(f"Correlation stress: {names[0]} + {names[1]}",
                                 weights,correlations,z,"Weight of "+names[0],
                                 "Assumed correlation","Annualized σ"))
            metrics.extend([metric(names[0]+" observed σ",float(v[0])),
                            metric(names[1]+" observed σ",float(v[1])),
                            metric("Observed correlation",float(data[names].corr().iloc[0,1]))])
            warnings.append("The correlation axis is a hypothetical stress assumption; only the two marginal vols are empirical.")
        elif model_id=="black_litterman":
            names=data.columns
            bm=pd.Series(1/len(names),index=names)
            view=pd.DataFrame(np.array([[1,-1]+[0]*(len(names)-2)]),
                              index=["hypothetical_relative_view"],columns=names)
            target=pd.Series([params["view_spread"]],index=view.index)
            post=portfolio_extensions.black_litterman_posterior(sigma,bm,
                            params["risk_aversion"],view,target,tau=.05)
            prior=post["equilibrium_returns"]
            posterior=post["posterior_expected_returns"]
            metrics.extend([metric("Assumed view spread",params["view_spread"],"annual decimal"),
                            metric("Posterior expected return, equal-weight",float(posterior.mean()),"annual decimal")])
            plots.append(xy("Implied equilibrium vs hypothetical posterior",list(names),
                            [line("Equilibrium",prior),line("Posterior",posterior)],
                            "Security","Expected annual return",kind="bar2d"))
            response["table"]=[{"security":str(k),"prior":float(prior[k]),
                                "posterior":float(posterior[k])} for k in names]
            warnings.append("Illustrative equal-weight market proxy and explicit hypothetical spread between first two assets; not a market-cap benchmark or forecast alpha.")
        elif model_id=="efficient_frontier":
            cap=params["max_weight"]
            mu_array=mu.to_numpy(dtype=float)
            def feasible_target(reverse):
                order=np.argsort(mu_array)
                if reverse:
                    order=order[::-1]
                slots=1.
                result=0.
                for idx in order:
                    a=min(slots,cap)
                    result+=a*mu_array[idx]
                    slots-=a
                    if slots<1e-9: break
                return result
            lower,upper=feasible_target(False),feasible_target(True)
            if upper-lower<1e-8:
                raise ValueError("Expected returns too similar to form a meaningful frontier")
            targets=np.linspace(lower+.08*(upper-lower),upper-.08*(upper-lower),13).tolist()
            frame=portfolio_math.efficient_frontier(mu,sigma,targets,max_weight=cap)
            viable=frame.loc[frame["feasible"]].copy()
            if len(viable)<3:
                raise ValueError("Fewer than three feasible efficient-frontier targets")
            plots.append(xy("In-sample constrained efficient frontier",
                            viable["volatility"].tolist(),
                            [line("Expected annual return",viable["realized_expected_return"])],
                            "Annualized volatility","Annualized expected return"))
            metrics.extend([metric("Feasible frontier solutions",len(viable)),
                            metric("Low volatility",float(viable["volatility"].min()),"decimal"),
                            metric("High expected return",float(viable["realized_expected_return"].max()),"decimal")])
            response["table"]=[{"volatility":float(r["volatility"]),
                                "expected_return":float(r["realized_expected_return"])}
                                for _,r in viable.iterrows()]
            warnings.append("Sample means are noisy; these feasible allocations have no holdout performance guarantee.")
        else:
            cap=params["max_weight"]
            if model_id=="min_variance":
                res=math_models.minimum_variance(sigma,mu,max_weight=cap)
                w=res.weights
            elif model_id=="risk_parity":
                w=portfolio_math.risk_parity(sigma,max_weight=cap)
            elif model_id=="max_diversification":
                w=portfolio_math.maximum_diversification(sigma,max_weight=cap)
            else:
                fit=portfolio_extensions.minimize_historical_cvar(data,
                              confidence=params["confidence"],max_weight=cap)
                w=fit["weights"]
                metrics.extend([metric("Historical optimized CVaR",fit["optimization_objective_cvar"],"decimal loss"),
                                metric("Scenario count",fit["scenarios"])])
            if abs(float(w.sum())-1)>1e-4 or (w < -1e-6).any() or (w > cap+1e-6).any():
                raise ValueError("Optimization returned invalid or uninvestable weights")
            expected=float(mu.dot(w))
            risk=math.sqrt(max(float(w.to_numpy()@sigma.to_numpy()@w.to_numpy()),0))
            metrics.extend([metric("In-sample annual expected return",expected,"decimal"),
                            metric("Annualized volatility",risk,"decimal"),
                            metric("Effective holdings",float(1/(w**2).sum()))])
            plots.append(xy(spec["title"]+" · optimized weights",list(w.index),
                            [line("Portfolio weight",w)],"Security","Portfolio share",kind="bar2d"))
            if model_id=="risk_parity":
                rc=portfolio_math.portfolio_risk_contributions(w,sigma)
                plots.append(xy("Euler volatility contribution",list(rc.index),
                        [line("Fraction of risk",rc["fraction_of_total_risk"])],
                        "Security","Risk share",kind="bar2d"))
            response["table"]=[{"security":str(k),"weight":float(v)} for k,v in w.items()]
    elif model_id in {"historical_tail","gaussian_tail","student_t_tail","evt","newey_west","bootstrap_sharpe"}:
        if model_id=="newey_west":
            stats=inference.newey_west_mean_test(basket)
            metrics.extend(metric(k.replace("_"," ").title(),v) for k,v in stats.items())
            cum=(1+basket).cumprod()
            plots.append(xy("Equal-weight basket · observed cumulative wealth",
                            [d.date().isoformat() for d in cum.index],
                            [line("Observed basket wealth",cum)],"Date","Relative wealth"))
        elif model_id=="bootstrap_sharpe":
            out=inference.block_bootstrap_sharpe(basket,block_length=params["block_length"],
                                                 seed=seed,simulations=1000,periods_per_year=annual)
            metrics.extend([metric("Sharpe point estimate",out["point_estimate"]),
                            metric("Bootstrap 95% low",out["lower"]),
                            metric("Bootstrap 95% high",out["upper"]),
                            metric("Bootstrap replications",out["replications"])])
            plots.append(xy("Equal-weight basket · cumulative observations",
                            [d.date().isoformat() for d in basket.index],
                            [line("Observed sample wealth",(1+basket).cumprod())],
                            "Date","Relative wealth"))
        else:
            losses=-basket
            if model_id=="historical_tail":
                result=math_models.historical_var_es(basket,params["confidence"])
                quantile=result["var"]
                metrics.extend([metric("Historical VaR",result["var"],"decimal loss"),
                                metric("Historical tail mean",result["expected_shortfall"],"decimal loss")])
            elif model_id=="gaussian_tail":
                result=tail_risk.gaussian_var_es(float(basket.mean()),
                    float(basket.std(ddof=1)),params["confidence"])
                quantile=result["var"]
                metrics.extend([metric("Gaussian VaR",result["var"],"decimal loss"),
                                metric("Gaussian ES",result["expected_shortfall"],"decimal loss")])
            elif model_id=="student_t_tail":
                df=params["df"]
                scale=float(basket.std(ddof=1))*math.sqrt((df-2)/df)
                result=tail_risk.student_t_var_es(float(basket.mean()),scale,df,
                                                 params["confidence"])
                quantile=result["var"]
                metrics.extend([metric("Student-t VaR",result["var"],"decimal loss"),
                                metric("Student-t ES",result["expected_shortfall"],"decimal loss"),
                                metric("Assumed degrees of freedom",df)])
                warnings.append("Degrees of freedom are user-specified. Student-t scale was matched to observed variance, not distribution-fit.")
            else:
                result=tail_risk.evt_peak_over_threshold(losses,
                     threshold_quantile=params["threshold_quantile"],
                     confidence=params["confidence"])
                quantile=result["loss_quantile"]
                metrics.extend([metric("POT loss quantile",quantile,"decimal loss"),
                                metric("Fitted GPD shape",result["gpd_shape"]),
                                metric("Tail exceedances",result["exceedance_count"])])
            plots.append(histogram("Observed basket loss distribution",losses,quantile))
            metrics.append(metric("Observed common returns",obs))
    else:
        raise ValueError("Model exists in catalog but has no execution implementation")

    # Final JSON-safety guard: reject invented or nonfinite numerical outputs.
    def assert_finite(value):
        if isinstance(value,dict):
            for val in value.values(): assert_finite(val)
        elif isinstance(value,list):
            for val in value: assert_finite(val)
        elif isinstance(value,(float,np.floating)) and not math.isfinite(value):
            raise ValueError("Nonfinite numerical model result; no figure was published")
    assert_finite(response)
    return response


# Durable model-run artifacts live in Git-ignored results/. No credentials,
# account identities, raw source candles or brokerage positions are serialized.
RUN_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{10}$")


def _run_root() -> Path:
    # Peer of results/workstation_runs; do not mix index experiments and model calculations.
    return service.RESULTS.parent / "model_laboratory"


def save_result(result: dict) -> dict:
    """Append an atomic, source-checksummed copy of a successfully computed model."""
    if result.get("model_id") not in CATALOG:
        raise ValueError("Cannot save an unregistered model result")
    snapshot=dict(result)
    source=snapshot.get("source")
    if source:
        folder,_record=service.dataset_path(source["dataset_id"])
        selected=folder/source["source_file"]
        if not selected.is_file() or selected.is_symlink():
            raise ValueError("Observed source disappeared before result archival")
        snapshot["source_sha256"]=hashlib.sha256(selected.read_bytes()).hexdigest()
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:10]
    snapshot["run_id"]=run_id
    encoded=json.dumps(snapshot,ensure_ascii=False,allow_nan=False,indent=2).encode("utf-8")
    if len(encoded)>4_000_000:
        raise ValueError("Model result exceeds safe local archive size")
    root=_run_root()
    root.mkdir(parents=True,exist_ok=True)
    filename=root/(run_id+".json")
    # Exclusive creation: no overwrite and no unbounded JSON history in memory.
    with open(filename,"xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return snapshot


def list_saved_models(include_archived: bool = False, limit: int = 30) -> list[dict]:
    root=_run_root()
    if not root.is_dir() or root.is_symlink():
        return []
    rows=[]
    for p in sorted(root.glob("*.json"),reverse=True)[:max(60,limit*2)]:
        if p.is_symlink() or not RUN_ID.fullmatch(p.stem):
            continue
        try:
            result=json.loads(p.read_text(encoding="utf-8"))
        except (OSError,ValueError,TypeError):
            continue
        if result.get("run_id")!=p.stem or result.get("model_id") not in CATALOG:
            continue
        rows.append({"id":p.stem,"model_id":result["model_id"],
            "title":result.get("title"),"group":result.get("group"),
            "mode":result.get("mode"),"generated_utc":result.get("generated_utc"),
            "dataset_id":(result.get("source") or {}).get("dataset_id"),
            "observations":(result.get("source") or {}).get("observations"),
            "figures":len(result.get("plots",[]))})
    if not include_archived:
        from . import research_library
        states = research_library.resource_state_map()
        rows = [r for r in rows if not states.get("model_run:"+r["id"],{}).get("archived",False)]
    return rows[:limit]


def read_saved_model(run_id: str) -> dict:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid model-run identifier")
    target=_run_root()/(run_id+".json")
    if not target.is_file() or target.is_symlink():
        raise FileNotFoundError("Saved model run unavailable")
    result=json.loads(target.read_text(encoding="utf-8"))
    if result.get("run_id")!=run_id or result.get("model_id") not in CATALOG:
        raise ValueError("Invalid saved model metadata")
    return result
