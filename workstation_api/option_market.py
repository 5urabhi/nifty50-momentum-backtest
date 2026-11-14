"""Read-only market-quote-anchored pricing, not observed backtest returns.

A vendor option bid/ask and spot are OBSERVED INPUTS. BSM, CRR, Monte
Carlo and BSM scenario surfaces are MODEL-BASED VALUATIONS even after
calibrating quoted implied vol. Risk-free rate and dividend yield remain
explicit user assumptions unless a separately sourced curve is available.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from index_research import derivatives, math_models
from . import option_quotes


SUPPORTED = {
    "black_scholes_quote":"BSM observed-quote valuation",
    "binomial_quote":"CRR observed-quote valuation",
    "implied_vol_quote":"Quoted bid/ask implied volatility",
    "mc_option_quote":"Quote-anchored Monte Carlo valuation",
    "option_surface_quote":"3D quote-anchored BSM scenarios",
}


def inspect(dataset_id: str | None, quote_id: str) -> dict:
    if not dataset_id:
        return {"status":"select_dataset","runnable":False,"can_download":False,
                "message":"Select a research dataset to attach actual option quotes.",
                "common_returns":0,"assets_found":0}
    if not quote_id:
        return {"status":"missing_quote","runnable":False,"can_download":False,
                "message":"No original option quote selected. Upload an original bid/ask CSV "
                          "from your data provider, then choose its saved quote snapshot.",
                "common_returns":0,"assets_found":0}
    try:
        quote_id,sep,index_str=quote_id.partition(":")
        if not sep or not index_str.isdigit() or len(index_str)>3:
            raise ValueError("Select a saved quote and one contract from the picker")
        index=int(index_str)
        row,manifest=option_quotes.read_contract(quote_id,dataset_id,index)
        age=(pd.Timestamp.now(tz="UTC")-pd.Timestamp(row["captured_at"])).total_seconds()/86400
        return {"status":"ready_with_buffer","runnable":True,"can_download":False,
                "common_returns":1,"assets_found":1,
                "message":f"Original {row['provider']} quote at {row['captured_at']} "
                          f"for {row['underlying']} {row['strike']:g} {row['option_type']} "
                          f"expiring {row['expiry_at']}. "
                          +("HISTORICAL SNAPSHOT: not a current executable quote. " if age>2 else
                            "Snapshot may already be stale/intraday. ")
                          +"Risk-free rate and dividend yield are user assumptions.",
                "download_explanation":"Use the quote CSV importer. Historical underlying candles "
                                       "alone do not contain option premium or implied volatility."}
    except (ValueError,FileNotFoundError,OSError) as exc:
        return {"status":"missing_quote","runnable":False,"can_download":False,
                "message":str(exc),"common_returns":0,"assets_found":0}


def fit(model_id: str, dataset_id: str, params: dict) -> dict:
    from .model_lab import line, metric, xy, surface
    if model_id not in SUPPORTED:
        raise ValueError("Unsupported option-market evaluation")
    composite=params["quote"]
    quote_id,sep,index_str=composite.partition(":")
    if not sep or not index_str.isdigit() or len(index_str)>3:
        raise ValueError("Select a stored original option quote and one actual contract")
    contract,manifest=option_quotes.read_contract(quote_id,dataset_id,int(index_str))
    t=(pd.Timestamp(contract["expiry_at"])-pd.Timestamp(contract["captured_at"])).total_seconds()
    years=t/(365.25*86400)
    if years<=1e-6 or years>10:
        raise ValueError("Option tenor is invalid or too short for stable Black–Scholes inversion")
    spot=float(contract["underlying_spot"])
    strike=float(contract["strike"])
    option=contract["option_type"]
    bid,ask=map(float,(contract["bid"],contract["ask"]))
    mid=(bid+ask)/2
    rate=float(params["risk_free_rate"])
    dividend=float(params["dividend_yield"])
    try:
        iv_mid=derivatives.implied_volatility(
            mid,spot,strike,years,rate,option,dividend)
    except (ValueError,OverflowError) as exc:
        raise ValueError("Observed quote midpoint violates the selected European BSM "
                         "convention/no-arbitrage or lacks a volatility root: " + str(exc)) from exc
    if not math.isfinite(iv_mid) or not .00001<iv_mid<5:
        raise ValueError("Option quote implied volatility is invalid")
    iv_bid,iv_ask=None,None
    for name,price in (("bid",bid),("ask",ask)):
        try:
            val=derivatives.implied_volatility(price,spot,strike,years,rate,option,dividend)
            if name=="bid": iv_bid=val
            else: iv_ask=val
        except (ValueError,OverflowError):
            pass

    metrics=[
        metric("Original quoted bid",bid,"quote currency"),
        metric("Original quoted ask",ask,"quote currency"),
        metric("Observed midpoint (not last execution)",mid,"quote currency"),
        metric("Observed quote spread",ask-bid,"quote currency"),
        metric("Time to expiry",years,"years from timestamp"),
        metric("Quote-implied European BSM volatility",iv_mid,"annualized"),
    ]
    graphs=[]
    table=[{"field":"Provider","value":contract["provider"]},
           {"field":"Quote timestamp (UTC)","value":contract["captured_at"]},
           {"field":"Exact expiration (UTC)","value":contract["expiry_at"]},
           {"field":"Underlying","value":contract["underlying"]},
           {"field":"Spot in quote","value":spot},
           {"field":"Strike in quote","value":strike},
           {"field":"Bid","value":bid},{"field":"Ask","value":ask},
           {"field":"Quote midpoint","value":mid},
           {"field":"Implied volatility from midpoint","value":iv_mid}]
    if iv_bid is not None: metrics.append(metric("Implied vol from bid",iv_bid,"annualized"))
    if iv_ask is not None: metrics.append(metric("Implied vol from ask",iv_ask,"annualized"))
    if iv_bid is None or iv_ask is None:
        metrics.append(metric("Bid/ask IV bounds","Unavailable: no-arbitrage boundary"))
    restrictions=[
        "OPTION PRICES ARE OBSERVED SOURCE INPUTS, but every calculated BSM/CRR/MC/surface value is a MODEL result.",
        "A bid/ask snapshot is not an actual execution fill. Historical or illiquid quotes must not be represented as live tradable premiums.",
        "The risk-free rate and continuous dividend yield are user-entered ASSUMPTIONS, not a verified instrument-matched rates/dividend curve.",
        "Midpoint IV fitting is tautological for the same contract: reproducing its midpoint is NOT predictive validation.",
        "European Black–Scholes implied volatility is a MODEL conversion, "
        "not an automatically verified exchange-provided IV quote.",
    ]
    if (pd.Timestamp.now(tz="UTC")-pd.Timestamp(contract["captured_at"])).total_seconds()>172800:
        restrictions.append("STALE/HISTORICAL QUOTE: more than two days old; "
                            "analysis is retrospective, not executable now.")
    if model_id in {"black_scholes_quote","binomial_quote","mc_option_quote","option_surface_quote"}:
        # The same observed mid calibrates the volatility input, so any
        # same-contract 'error' is in-sample and not independent evidence.
        metrics.append(metric("Price-vol calibration target",mid,"observed quote midpoint"))
    if model_id=="black_scholes_quote":
        values=math_models.black_scholes(spot,strike,years,rate,iv_mid,option,dividend)
        for name,value in values.items():
            metrics.append(metric("BSM "+name.replace("_"," ").title(),value))
        spots=np.linspace(max(spot*.65,.01),spot*1.35,50)
        values=[math_models.black_scholes(float(v),strike,years,rate,iv_mid,
                                          option,dividend)["price"] for v in spots]
        graphs.append(xy("Observed quote–anchored theoretical BSM price sensitivity",
                         spots.tolist(),[line("BSM theoretical value",values)],
                         "Underlying scenario spot","Model option premium"))
    elif model_id=="binomial_quote":
        steps=int(params["steps"])
        exercise=params["exercise"]
        model_val=derivatives.binomial_option(spot,strike,years,rate,iv_mid,
                       steps,option,exercise,dividend)
        metrics.extend([metric("CRR model premium",model_val,"quote currency"),
                        metric("Tree steps",steps),
                        metric("Observed midpoint minus CRR model",mid-model_val)])
        counts=sorted(set([20,40,80,160,steps]))
        estimates=[derivatives.binomial_option(spot,strike,years,rate,iv_mid,
                        n,option,exercise,dividend) for n in counts]
        graphs.append(xy("CRR step convergence with observed source quote",
                         counts,[line("CRR model value",estimates),
                                 line("Observed quoted midpoint",[mid]*len(counts))],
                         "Number of CRR steps","Option premium"))
        if exercise=="american":
            restrictions.append("American exercise can exceed European BSM values; "
                                "the quote-derived European IV is only a proxy for the American tree.")
    elif model_id=="implied_vol_quote":
        grid=np.linspace(max(.01,iv_mid*.4),min(5.,iv_mid*1.6),60)
        model=[math_models.black_scholes(spot,strike,years,rate,float(v),
                                        option,dividend)["price"] for v in grid]
        graphs.append(xy("Observed bid/ask against European model premiums",
                    grid.tolist(),[line("BSM model premium",model),
                                   line("Original bid",[bid]*len(grid)),
                                   line("Original ask",[ask]*len(grid)),
                                   line("Original midpoint",[mid]*len(grid))],
                    "Annualized implied volatility","Quote currency premium"))
    elif model_id=="mc_option_quote":
        estimates=[]
        counts=[200,500,1500,5000]
        final=None
        for n in counts:
            final=derivatives.monte_carlo_european(
                spot,strike,years,rate,iv_mid,paths=n,option=option,
                dividend_yield=dividend,seed=int(params["seed"]))
            estimates.append(final["price"])
        theoretical=math_models.black_scholes(spot,strike,years,rate,iv_mid,option,dividend)["price"]
        metrics.extend([
            metric("Antithetic MC model premium",final["price"],"quote currency"),
            metric("MC numerical SE",final["standard_error"],"quote currency"),
            metric("MC 95% numerical CI low",final["ci95_lower"],"quote currency"),
            metric("MC 95% numerical CI high",final["ci95_upper"],"quote currency"),
            metric("BSM analytical numerical comparator",theoretical,"quote currency")])
        graphs.append(xy("Quote-calibrated numerical Monte Carlo convergence",
                        counts,[line("Antithetic simulated option value",estimates),
                                line("Analytical BSM value",[theoretical]*len(counts)),
                                line("Observed market midpoint",[mid]*len(counts))],
                        "Monte Carlo antithetic simulations","Model option premium"))
        restrictions.append("Monte Carlo confidence intervals quantify RANDOM NUMERICAL ERROR "
                            "in the model estimator, not future option-market price uncertainty.")
    elif model_id=="option_surface_quote":
        spots=np.linspace(spot*.65,spot*1.35,23)
        vol_bounds=[max(.01,.5*iv_mid),min(4.,1.6*iv_mid)]
        if vol_bounds[0]>=vol_bounds[1]:
            raise ValueError("Quote-implied vol is outside safe surface range")
        vols=np.linspace(*vol_bounds,19)
        matrix=[[math_models.black_scholes(float(v),strike,years,rate,float(sig),
                    option,dividend)["price"] for v in spots] for sig in vols]
        graphs.append(surface("Original market quote–anchored theoretical price surface",
                    spots,vols,matrix,"Scenario spot","Scenario implied volatility",
                    "BSM option premium"))
        metrics.append(metric("Theoretical 3D grid points",len(spots)*len(vols)))
        restrictions.append("3D prices are what-if model scenarios around ONE observed contract, "
                            "NOT a fitted multi-strike/multi-expiry market implied volatility surface.")
    else:
        raise ValueError("Unimplemented market option calculation")

    source={
        "dataset_id":dataset_id,"dataset_label":"Option quote snapshot · "+contract["provider"],
        "dataset_kind":"quoted_market_input","frequency":"original_quote_snapshot",
        "observations":1,"assets":[contract["underlying"]],
        "from_date":contract["captured_at"],"to_date":contract["captured_at"],
        "source_file":"option_quote:"+quote_id,"option_quote_id":quote_id,
        "selection_rule":"Exact selected vendor contract and original bid/ask snapshot",
        "source_sha256":manifest["source_sha256"],
        "underlying_spot_origin":"original vendor quote row",
        "market_quote_observed":True,
        "model_volatility_origin":"Black-Scholes inversion of same vendor quote midpoint",
        "risk_free_rate_origin":"user_assumed","dividend_yield_origin":"user_assumed",
        "source_independently_certified":False,
        "benchmark_kind":"not_applicable",
    }
    return {
        "mode":"market","source":source,"metrics":metrics,"plots":graphs,
        "table":table,"calibration":{"quote_id":quote_id,"row_index":int(index_str),
            "method":"single_contract_bid_ask_midpoint_European_BSM_IV",
            "input_observed":True,"midpoint_used_in_fit":True,
            "historical_oos_validation":False,
            "market_source_sha256":manifest["source_sha256"],
            "assumed_rate":rate,"assumed_dividend_yield":dividend,
            "fitted_implied_volatility":iv_mid},
        "notes":[f"Quote from {contract['provider']} captured at {contract['captured_at']}.",
                 "No market option chain downloads, live quotes, or brokerage orders submitted.",
                 "Original spot/strike/bid/ask/expiry from source, not invented defaults."],
        "limitations":restrictions,
        "evidence_type":"quote_anchored_theoretical_valuation_not_market_backtest",
    }
