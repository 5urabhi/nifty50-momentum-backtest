"""Observed-data stochastic experiments: OU volatility, Merton tails and Heston proxy.

The original stochastic demos remain untouched. These are fitted *physical*
descriptive/proxy models using only TRAIN returns; 20% chronological diagnostics.
Simulated paths remain artificial. Heston parameter estimates are NOT
risk-neutral option-market calibration or identifiable latent variance truth.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm, poisson

from index_research import advanced_models, derivatives
from .gbm_calibration import _series

MINIMUM = {"ou_fit": 90, "merton_fit": 120, "heston_proxy": 252}


def _observed(dataset_id: str, model_id: str, params: dict):
    levels, log_return, source = _series(dataset_id, params["target"], params["ticker"])
    if len(log_return) < MINIMUM[model_id]:
        raise ValueError(
            f"{model_id} needs at least {MINIMUM[model_id]} consecutive observed returns; "
            f"found {len(log_return)}. Extend the source history.")
    if model_id in {"ou_fit", "heston_proxy"} and source["frequency"] != "daily":
        raise ValueError(
            model_id + " needs DAILY observed prices; monthly TRI returns cannot "
            "identify short-horizon volatility dynamics. Select a Dhan daily stock.")
    return levels, log_return, source


def inspect(dataset_id: str | None, model_id: str, params: dict) -> dict:
    minimum=MINIMUM[model_id]
    if not dataset_id:
        return {"status":"select_dataset", "runnable":False,"common_returns":0,
                "assets_found":0,"can_download":False,
                "message":"Choose an observed dataset for this stochastic model."}
    try:
        _, returns, source = _observed(dataset_id, model_id, params)
        n=len(returns)
        buffer=math.ceil(minimum*1.2)
        return {"status":"ready_with_buffer" if n>=buffer else "ready_minimum",
                "runnable":True,"common_returns":n,"assets_found":1,
                "frequency":source["frequency"], "can_download":False,
                "message":f"{n} original {source['frequency']} log returns; "
                          "fit first 80%, evaluate final 20%. "
                          "The generated scenario fan is still simulated.",
                "download_explanation":"Use Data Library or the Dhan downloader to extend historical candles."}
    except (ValueError, FileNotFoundError, OSError) as exc:
        return {"status":"insufficient","runnable":False,"common_returns":0,
                "assets_found":0,"can_download":False,"message":str(exc),
                "download_explanation":str(exc)}


def _split(x: np.ndarray, length: int):
    n_test=max(12, math.ceil(length*.20))
    n_train=length-n_test
    if n_train<30:
        raise ValueError("Insufficient strictly prior training observations")
    return x[:n_train], x[n_train:], n_train, n_test


def _ar1(train: np.ndarray):
    """OLS on prior-only x_t to forecast x_(t+1)."""
    regressors=np.column_stack([np.ones(len(train)-1),train[:-1]])
    intercept, phi=map(float,np.linalg.lstsq(regressors,train[1:],rcond=None)[0])
    residual=train[1:]-(intercept+phi*train[:-1])
    sigma=float(np.std(residual,ddof=1))
    if not np.isfinite([intercept,phi,sigma]).all() or sigma<1e-11:
        raise ValueError("Observed series has no valid conditional variation")
    return intercept,phi,sigma


def fit(model_id: str, dataset_id: str, params: dict) -> dict:
    from .model_lab import fan, line, metric, xy
    levels, returns, source=_observed(dataset_id,model_id,params)
    annual=int(source["periods_per_year"])
    count=int(params["paths"]);seed=int(params["seed"]);steps=int(params["steps"])
    horizon=float(params["years"])
    x=returns.to_numpy(dtype=float)
    limits=["Fitted on the chronological first 80% only; last 20% reserved for descriptive diagnostics.",
            "Source provenance and valid price returns are separate from claims of predictive performance.",
            "Any stochastic price/variance paths are seeded hypothetical simulations, never observed prices.",
            "A retrospective holdout does not prove prospective performance or exclude previous researcher selection."]
    if source["is_synthetic_fixture"]:
        limits.append("SYNTHETIC FIXTURE: source is generated; these are NOT observed market returns.")
    if model_id=="ou_fit":
        # Fit Gaussian mean reversion to log of 20-session trailing realized
        # volatility. Equity log-price levels are not assumed stationary.
        vol=returns.rolling(20).std(ddof=1)*math.sqrt(annual)
        process=np.log(vol.dropna())
        if len(process)<60:
            raise ValueError("OU needs at least 60 valid trailing-volatility observations")
        train,test,ntrain,ntest=_split(process.to_numpy(dtype=float),len(process))
        a,phi,sigma_eps=_ar1(train)
        if not 0<phi<1:
            raise ValueError("No positive stationary mean reversion in log realized volatility "
                             "(estimated AR(1) coefficient outside 0..1); a positive-kappa OU fit "
                             "would misrepresent this sample. Select another ticker/period.")
        dt=1/annual
        kappa=-math.log(phi)/dt
        theta=a/(1-phi)
        diffusion=sigma_eps*math.sqrt(2*kappa/(1-phi*phi))
        predicted=a+phi*process.to_numpy(dtype=float)[ntrain-1:-1]
        observed=test
        rmse=float(np.sqrt(np.mean((observed-predicted)**2)))
        flat=float(np.sqrt(np.mean((observed-process.to_numpy(dtype=float)[ntrain-1:-1])**2)))
        residual=(observed-predicted)/sigma_eps
        coverage=float(np.mean(np.abs(residual)<=1.96))
        # Model's own OU state is log-volatility; NOT a stock price path.
        simulated=advanced_models.simulate_ou(
            float(process.iloc[ntrain-1]),theta,kappa,diffusion,horizon/steps,
            steps,count,seed)
        result={
            "metrics":[metric("Estimated mean-reversion κ",kappa,"per year"),
                       metric("OU equilibrium log realized vol θ",theta,"log annualized σ"),
                       metric("OU diffusion coefficient",diffusion),
                       metric("AR(1) persistence",phi),
                       metric("Held-out one-step RMSE",rmse,"log realized vol"),
                       metric("Flat-volatility benchmark RMSE",flat,"log realized vol"),
                       metric("Held-out Gaussian 95% coverage",coverage,"fraction")],
            "plots":[xy("OU holdout · observed and prior-only one-step predictions",
                        [t.date().isoformat() for t in process.index[ntrain:]],
                        [line("Observed log realized volatility",observed),
                         line("Prior observed state OU forecast",predicted)],
                        "Actual trading session","Log 20-session realized volatility"),
                     fan("OU · hypothetical forward log-realized-volatility scenarios",
                         simulated,horizon,"Years after fitted sample")],
            "notes":["OU models log 20-session trailing realized VOLATILITY, not stock-price levels.",
                     "AR(1) exact discretization: phi=exp(-kappa * 1/252).",
                     "One-step holdout predictions use the preceding observed volatility proxy only."],
            "calibration":{"method":"AR1_exact_OU_on_log_trailing_realized_vol",
                           "kappa":kappa,"theta":theta,"diffusion":diffusion,
                           "phi":phi,"train_count":ntrain,"test_count":ntest,
                           "test_used_in_fit":False},
            "source":{**source,"assets":source["assets"],
                      "source_transform":"log(20_session_realized_volatility)"},
        }
        limits.append("Overlapping 20-day volatility windows create serial dependence; Gaussian residual bands are descriptive.")
    elif model_id=="merton_fit":
        train,test,ntrain,ntest=_split(x,len(x))
        med=float(np.median(train))
        robust=1.4826*float(np.median(np.abs(train-med)))
        if robust<1e-10:
            raise ValueError("Cannot estimate a jump threshold from essentially constant returns")
        threshold=3*robust
        mask=np.abs(train-med)>threshold
        nj=int(mask.sum())
        diffusion_data=train[~mask]
        if len(diffusion_data)<30:
            raise ValueError("Too many tail observations to estimate a diffusion component")
        vol=float(np.std(diffusion_data,ddof=1))*math.sqrt(annual)
        lam=float(nj*annual/ntrain)
        jump_mean=float(np.mean(train[mask]-med)) if nj else 0.
        jump_sd=float(np.std(train[mask]-med,ddof=1)) if nj>=3 else 0.
        avg=float(np.mean(train))*annual
        correction=math.expm1(jump_mean+.5*jump_sd**2)
        drift=avg+.5*vol**2+lam*(correction-jump_mean)
        if not np.isfinite([vol,lam,jump_mean,jump_sd,drift]).all():
            raise ValueError("Non-finite jump-diffusion moment estimate")
        # A stable continuous diffusion can be measured without claiming
        # sparse jump parameters identified by 0-2 observed threshold events.
        simulated=derivatives.merton_jump_diffusion(
            float(levels.iloc[-1]),horizon,steps,count,drift,vol,lam,
            jump_mean,jump_sd,seed)
        variance=(vol**2+lam*(jump_mean**2+jump_sd**2))/annual
        predicted_mean=(drift-.5*vol*vol-lam*correction+lam*jump_mean)/annual
        z=(test-predicted_mean)/math.sqrt(max(variance,1e-12))
        coverage=float(np.mean(np.abs(z)<1.96))
        single_likelihood=float(np.mean(norm.logpdf(test,loc=predicted_mean,
                                                    scale=math.sqrt(variance))))
        baseline_sd=float(np.std(train,ddof=1))
        gaussian_likelihood=float(np.mean(norm.logpdf(test,loc=float(np.mean(train)),
                                      scale=baseline_sd)))
        result={
            "metrics":[metric("Detected training tail events",nj,"threshold crossings"),
                       metric("Tail threshold (3 × training MAD scale)",threshold,"log return"),
                       metric("Annual threshold-event intensity",lam,"per year"),
                       metric("Estimated diffusion volatility",vol,"annualized"),
                       metric("Tail-event mean log size",jump_mean,"log return"),
                       metric("Tail-event log size std",jump_sd,"log return"),
                       metric("Held-out normal-moment 95% coverage",coverage,"fraction"),
                       metric("Held-out moment-matched log likelihood",single_likelihood),
                       metric("Historical Gaussian baseline log likelihood",gaussian_likelihood)],
            "plots":[xy("Merton · observed returns with fixed train-only jump threshold",
                        [t.date().isoformat() for t in returns.index],
                        [line("Observed log return",x),
                         line("Upper training threshold",[med+threshold]*len(x)),
                         line("Lower training threshold",[med-threshold]*len(x))],
                        "Trading session","Log return"),
                     fan("Merton · seeded forward jump-diffusion scenarios",
                         simulated,horizon,"Years after last observed close")],
            "notes":["Exceedance-count fit to a 3×MAD training threshold is a heuristic, not a full MLE.",
                     "Threshold exceedances are not uniquely identifiable as actual market jumps.",
                     "No option-market jump-risk premium is estimated."],
            "calibration":{"method":"fixed_3mad_tail_threshold_moments",
                           "mu":drift,"sigma":vol,"lambda":lam,
                           "jump_mean_log":jump_mean,"jump_std_log":jump_sd,
                           "threshold":threshold,"train_count":ntrain,
                           "test_count":ntest,"test_used_in_fit":False},
            "source":source,
        }
        if nj<3:
            limits.append("FEWER THAN 3 threshold events: jump-size variance is NOT identifiable; "
                          "a zero assumed jump spread was used in illustrative paths.")
        limits.append("Holdout scores use a moment-matched normal approximation, NOT an exact jump-mixture likelihood.")
    elif model_id=="heston_proxy":
        if len(x)<252 or source["frequency"]!="daily":
            raise ValueError("Heston proxy requires 252+ actual daily stock returns")
        annual=252
        rv=returns.rolling(20).var(ddof=1).mul(annual).dropna()
        if len(rv)<180:
            raise ValueError("Insufficient 20-session realized variance observations")
        z=rv.to_numpy(dtype=float)
        tr,te,ntrain,ntest=_split(z,len(z))
        floor=1e-9
        dt=1/annual
        a,phi,_=_ar1(tr)
        if not 0<phi<1:
            raise ValueError("Estimated realized-variance AR(1) is not stationary. "
                             "Cannot infer a defensible Heston mean-reversion proxy.")
        kappa=-math.log(phi)/dt
        theta=float(a/(1-phi))
        if theta<=floor:
            raise ValueError("Unrealistic nonpositive fitted long-run variance")
        prediction=a+phi*tr[:-1]
        err=tr[1:]-prediction
        scale=np.sqrt(np.maximum(tr[:-1],floor)*dt)
        xi=float(np.sqrt(np.mean(np.square(err/scale))))
        # Discrete approx correlation between return and observed variance proxy
        # shocks on synchronized training days. NOT latent Brownian correlation.
        corresponding_returns=returns.loc[rv.index].to_numpy(dtype=float)
        paired=corresponding_returns[1:ntrain]
        rh=float(np.corrcoef((paired-np.mean(paired)),
                             err/np.maximum(scale,1e-12))[0,1])
        if not np.isfinite([xi,rh]).all():
            raise ValueError("Unidentifiable variance-shock correlation")
        rh=float(np.clip(rh,-.95,.95))
        # Simulate with empirical physical drift, NOT risk-neutral option price.
        # derivatives.heston_paths uses 'rate' as the price drift; supply the
        # empirical training drift but do not call this a risk-free rate.
        physical_drift=float(np.mean(x[:ntrain+19])*annual+
                             .5*float(np.mean(tr)))
        sv=derivatives.heston_paths(
            float(levels.iloc[-1]), float(np.clip(rv.iloc[-1],floor,2)),
            horizon,steps,count,rate=physical_drift,
            kappa=float(np.clip(kappa,.01,20)),
            long_variance=float(np.clip(theta,floor,2)),
            vol_of_vol=float(np.clip(xi,0,3)),rho=rh,seed=int(params["seed"]))
        hold_before=rv.to_numpy(dtype=float)[ntrain-1:-1]
        one_step=a+phi*hold_before
        rmse=float(np.sqrt(np.mean((te-one_step)**2)))
        flat=float(np.sqrt(np.mean((te-hold_before)**2)))
        result={
            "metrics":[metric("Estimated variance persistence φ",phi),
                       metric("Realized-variance mean-reversion proxy κ",kappa,"per year"),
                       metric("Proxy long-run variance θ",theta,"annualized return variance"),
                       metric("Proxy variance-of-variance ξ",xi),
                       metric("Proxy return/variance-shock correlation",rh),
                       metric("Held-out variance RMSE",rmse,"annualized squared return"),
                       metric("No-change variance RMSE",flat,"annualized squared return"),
                       metric("Synthetic Heston paths",count,"seeded paths")],
            "plots":[xy("Heston proxy · realized variance and one-step holdout estimates",
                        [t.date().isoformat() for t in rv.index[ntrain:]],
                        [line("Observed 20-session realized variance",te),
                         line("Prior-state predicted realized variance",one_step)],
                        "Actual trading session","Annualized rolling variance"),
                     fan("Heston-style forward scenarios · NOT options calibrated",
                         sv["prices"],horizon,"Years after observed sample")],
            "notes":["Proxy uses rolling 20-trading-day realized variance; Heston latent instantaneous variance is NOT directly observed.",
                     "Correlation and vol-of-vol are APPROXIMATIONS from the realized-variance proxy.",
                     "Simulation uses an estimated physical stock-return drift, not risk-neutral option pricing."],
            "calibration":{"method":"realized_variance_AR1_proxy_not_identified_heston",
                           "kappa_proxy":kappa,"theta_proxy":theta,
                           "xi_proxy":xi,"rho_proxy":rh,"train_count":ntrain,
                           "test_count":ntest,"test_used_in_fit":False,
                           "risk_neutral_option_calibration":False},
            "source":{**source,"source_transform":"20_session_realized_variance"},
        }
        limits.extend([
            "Heston latent factors and risk-neutral variance parameters CANNOT be uniquely recovered from stock closes alone.",
            "For a true options-market Heston calibration, provide liquid dated option quotes across strikes and expiries; that workflow is a separate requirement.",
            "Simulation parameter clipping prevents numerical explosions; the model is a constrained PROXY, not an MLE.",
            "Overlapping rolling windows make standard OLS uncertainty formulas inappropriate.",
        ])
    else:
        raise ValueError("Unsupported stochastic calibration model")
    result.update({
        "limitations":limits,
        "evidence_type":"historical_stochastic_fit_with_seeded_simulation" if model_id!="heston_proxy"
                       else "historical_realized_variance_proxy_not_heston_option_calibration",
    })
    return result
