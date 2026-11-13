"""Research-grade explainability, index methodology and transparent data passports.

Every output is tied to observed source data or a saved immutable calculation.
No human-readable explanation is allowed to silently certify unverified prices.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import math
import os
import uuid

import numpy as np
import pandas as pd

from index_research.data import load_research_inputs
from index_research.factors import composite_scores
from index_research.index import construct_weights
from index_research.sector_data import asof_sectors, read_sector_history
from . import model_lab, model_registry, research_integrity, research_library, service


def _file_sha(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_sources(folder: Path) -> list[dict]:
    allowed=("prices.csv","daily_prices.csv","membership.csv","benchmark.csv",
             "fundamentals.csv","sectors.csv","corporate_actions.csv",
             "factor_returns.csv","benchmark_weights.csv","liquidity.csv")
    rows=[]
    for name in allowed:
        path=folder/name
        if path.exists() and not path.is_symlink() and path.is_file():
            rows.append({"name":name,"sha256":_file_sha(path),
                         "size_bytes":path.stat().st_size})
    return rows


def passport(dataset_id: str) -> dict:
    folder,source=service.dataset_path(dataset_id)
    items=_safe_sources(folder)
    integrity=research_integrity.inspect(dataset_id)
    description=("SYNTHETIC DEMONSTRATION ONLY" if source["kind"]=="synthetic"
                 else "OBSERVED UNVERIFIED" if items else "MISSING PRICE DATA")
    blockers=[]
    for item in integrity["evidence"]:
        if item["status"]=="missing":
            blockers.append({"category":item["category"],"requirement":item["criterion"],
                             "next_action":"Provide dated original source evidence and independently review it."})
    if source["kind"]=="synthetic":
        blockers.insert(0,{"category":"synthetic",
          "requirement":"Actual licensed historical closes and PIT membership",
          "next_action":"Select observed data; never promote demonstration returns as market results."})
    return {
        "dataset_id":dataset_id,"dataset":source["label"],"kind":source["kind"],
        "research_classification":description,
        "monthly_observations":source.get("monthly_price_observations",0),
        "daily_observations":source.get("daily_session_count"),
        "has_daily_prices":source.get("has_daily_prices",False),
        "historical_index":source.get("historical_index"),
        "source_basis":source.get("basis"),
        "available_files":items,
        "evidence":integrity["evidence"],"missing_data":source.get("missing",[]),
        "blockers":blockers,
        "observed_prices_available":bool(integrity["ready_for_descriptive_prices"] and source["kind"]!="synthetic"),
        "investability_certified":False,"publication_dated_fundamentals_certified":False,
        "prospective_trading_certified":False,
        "study_status":"demonstration" if source["kind"]=="synthetic"
                         else "source_documentation_needed",
        "disclosure":integrity["warning"],
    }


def index_preflight(dataset_id: str, config: dict) -> dict:
    folder,record=service.dataset_path(dataset_id)
    factor_weights={name:float(w) for name,w in config.get("factor_weights",{}).items()
                    if isinstance(w,(int,float)) and float(w)>0}
    blockers=[]
    warnings=[]
    if not record.get("ready"):
        blockers.append("Dataset is missing required inputs: "+", ".join(record.get("missing",[])))
    if not factor_weights:
        blockers.append("Select at least one positive factor weight.")
    if not set(factor_weights).issubset({"momentum","low_volatility","value","quality","size","yield"}):
        blockers.append("Only documented registered factor scores can be selected.")
    if set(factor_weights)&{"value","quality","size","yield"} and not record.get("has_fundamentals"):
        blockers.append("Value/Quality/Size/Yield require publication-dated fundamentals.csv.")
    if "yield" in factor_weights and record.get("has_fundamentals"):
        try:
            sample=pd.read_csv(folder/"fundamentals.csv")
            if "yield" not in sample or sample["yield"].notna().sum()<2:
                blockers.append("Yield factor requires sourced, publication-dated dividend yield rows.")
        except (OSError,ValueError):
            blockers.append("Yield factor source is unreadable.")
    if config.get("weighting")=="benchmark_relative":
        try:
            from index_research.institutional_index import read_benchmark_history
            read_benchmark_history(folder/"benchmark_weights.csv")
        except (OSError,ValueError) as exc:
            blockers.append("Benchmark-relative weighting: "+str(exc))
    if config.get("liquidity_aum") is not None:
        try:
            from index_research.liquidity import read_liquidity
            read_liquidity(folder/"liquidity.csv")
        except (OSError,ValueError) as exc:
            blockers.append("Liquidity/capacity scenario: "+str(exc))
    if config.get("sector_cap") is not None and not record.get("has_sectors"):
        blockers.append("Sector caps require effective-dated sectors.csv; today's sector labels are not substitutes.")
    count=int(config.get("top_n",10))
    cap=float(config.get("max_weight",.2))
    if count*cap < 1-1e-10:
        blockers.append("Infeasible weights: top_n × maximum weight is below 1.")
    universe_count=None
    price_path=folder/"prices.csv"
    if price_path.is_file() and not price_path.is_symlink():
        try:
            universe_count=len(pd.read_csv(price_path,nrows=0).columns)-1
            if universe_count>0 and min(count,universe_count)*cap < 1-1e-10:
                blockers.append("Infeasible observed universe: "+str(universe_count)+
                                " names at this weight cap cannot reach full investment.")
        except (OSError,ValueError):
            blockers.append("Unreadable monthly source header")
    if not 1<=count<=300 or not 0<cap<=1:
        blockers.append("Constituent count and weight cap must stay in permitted bounds.")
    if config.get("execution_lag",1)==0:
        warnings.append("Same-close execution is idealized and can introduce optimistic backtests.")
    if record["kind"]=="synthetic":
        warnings.append("All resulting prices are SYNTHETIC demonstration values.")
    else:
        warnings.append("This research is observational, not independently certified index performance.")
    evidence=research_integrity.inspect(dataset_id)
    for item in evidence["evidence"]:
        if item["status"]=="missing":
            warnings.append("Source evidence missing: "+item["label"])
    return {
        "dataset_id":dataset_id,"status":"ready_to_execute_unverified" if not blockers else "blocked",
        "blockers":blockers,"warnings":warnings,
        "factor_names":list(factor_weights),
        "factor_weights":factor_weights,"available_monthly_observations":record.get("monthly_price_observations"),
        "preferred_monthly_observations":max(60,int(config.get("momentum_formation",12))*2),
        "available_universe_securities":universe_count,
        "methodology":"Cross-sectional standardization at formation dates; monthly source "
                      "prices; top-N constituent selection, bounded SLSQP weight construction, "
                      "drift-aware turnover and explicit execution lag.",
        "source_manifest":_safe_sources(folder),
        "historical_investability_certified":False,
        "release_requirement":"Original PIT membership, corporate actions, dividend-reinvested "
                              "benchmark and traded costs require independent evidence.",
    }


def _factor_components(prices: pd.DataFrame, membership: pd.DataFrame,
                       fundamentals: pd.DataFrame | None, config: dict,
                       day: pd.Timestamp) -> dict[str,pd.Series]:
    weights={k:float(v) for k,v in config["factor_weights"].items() if float(v)>0}
    components={}
    for name in weights:
        one=composite_scores(prices,membership,{name:1.0},fundamentals,
            momentum_formation=int(config.get("momentum_formation",12)),
            momentum_skip=int(config.get("momentum_skip",1)),
            volatility_lookback=int(config.get("volatility_lookback",12)))
        components[name]=one.loc[day]
    return components


def index_decisions(run_id: str, requested_date: str | None = None,
                    ticker: str | None = None) -> dict:
    """Reconstruct an actual rebalance from the saved config and exact source files.

    No hidden inference: ranks, weighted factor z-scores, target and
    concentration constraints come from the same production math engine.
    """
    result=service.run_details(run_id)
    origin=result["source"]
    dataset_id=origin.get("dataset_id")
    if not dataset_id:
        raise ValueError("Archived run lacks its source dataset identifier")
    folder,record=service.dataset_path(dataset_id)
    prices,membership,benchmark,fundamentals=load_research_inputs(folder)
    if prices.shape[1]>350 or len(prices)>2000:
        raise ValueError("Explain up to 350 constituents and 2,000 monthly observations per run")
    saved_hashes=result["meta"].get("input_sha256",{})
    for name,digest in saved_hashes.items():
        source=folder/name
        if not source.is_file() or source.is_symlink() or _file_sha(source)!=digest:
            raise ValueError("Saved research input changed: "+name+
                             "; cannot explain historical decisions using different data")
    cfg=result["meta"]["config"]
    scores=composite_scores(prices,membership,cfg["factor_weights"],fundamentals,
        momentum_formation=cfg["momentum_formation"],
        momentum_skip=cfg["momentum_skip"],
        volatility_lookback=cfg["volatility_lookback"])
    sectors=None
    if cfg.get("sector_cap") is not None:
        path=folder/"sectors.csv"
        if not path.is_file() or path.is_symlink():
            raise ValueError("Effective-dated sectors.csv missing")
        sectors=asof_sectors(read_sector_history(str(path)),prices.index,prices.columns)
    benchmark_history=None
    if cfg["weighting"]=="benchmark_relative":
        from index_research.institutional_index import read_benchmark_history
        benchmark_history=read_benchmark_history(folder/"benchmark_weights.csv")
    targets=construct_weights(scores,membership,top_n=cfg["top_n"],
        weighting=cfg["weighting"],cap=cfg["max_weight"],rebalance_every=cfg["rebalance_every"],
        prices=prices,vol_lookback=cfg["volatility_lookback"],
        sectors=sectors,sector_cap=cfg.get("sector_cap"),
        benchmark_history=benchmark_history,
        optimizer_risk_aversion=cfg.get("optimizer_risk_aversion",3.),
        optimizer_turnover_penalty=cfg.get("optimizer_turnover_penalty",.02),
        optimizer_tracking_error_limit=cfg.get("optimizer_tracking_error_limit"),
        optimizer_max_trade_weight=cfg.get("optimizer_max_trade_weight"))
    rebalance=targets.dropna(how="all")
    if rebalance.empty:
        raise ValueError("This run has no rebalance decisions")
    if requested_date is None:
        day=rebalance.index[-1]
    else:
        day=pd.Timestamp(date.fromisoformat(requested_date))
        if day not in rebalance.index:
            raise ValueError("Requested date is not an actual rebalance decision date")
    components=_factor_components(prices,membership,fundamentals,cfg,day)
    current_scores=scores.loc[day]
    eligible=membership.loc[day]
    ranks=current_scores[eligible].dropna().sort_values(ascending=False,kind="stable")
    target=targets.loc[day].fillna(0)
    names=list(ranks.index)
    selected=set(names[:cfg["top_n"]])
    requested=[ticker] if ticker else list(target[target>0].nlargest(35).index)
    for name in requested:
        if name not in prices.columns:
            raise ValueError("Requested constituent not in archived universe")
    factor_sum=sum(v for v in cfg["factor_weights"].values() if v>0)
    rows=[]
    for name in requested:
        contributions={key: (float(value.loc[name])*cfg["factor_weights"][key]/factor_sum
                             if pd.notna(value.loc[name]) else None)
                       for key,value in components.items()}
        row={
            "ticker":name,"member_at_decision":bool(eligible.loc[name]),
            "score":float(current_scores.loc[name]) if pd.notna(current_scores.loc[name]) else None,
            "rank":names.index(name)+1 if name in names else None,
            "selected_in_top_n":name in selected,
            "target_weight":float(target.loc[name]),
            "weighted_factor_contributions":contributions,
            "at_weight_cap":bool(target.loc[name]>0 and
                                 abs(target.loc[name]-cfg["max_weight"])<1e-5),
            "sector":str(sectors.loc[day,name]) if sectors is not None and pd.notna(sectors.loc[day,name]) else None,
        }
        row["explanation"]=(
            "Ineligible at this date." if not row["member_at_decision"] else
            "No complete source-supported factor score." if row["score"] is None else
            "Ranked outside the selected top-N." if name not in selected else
            "Chosen by ranked factors; final weight determined by the selected weighting "
            "rule and active allocation constraints.")
        rows.append(row)
    return {
        "run_id":run_id,"decision_date":day.date().isoformat(),
        "available_rebalance_dates":[d.date().isoformat() for d in rebalance.index[-50:]],
        "dataset_id":dataset_id,"dataset_kind":record["kind"],
        "source_hashes":saved_hashes,
        "selection_rule":"Eligible stocks ranked by weighted cross-sectional factor z-scores.",
        "weighting_rule":cfg["weighting"],
        "maximum_single_weight":cfg["max_weight"],"sector_cap":cfg.get("sector_cap"),
        "selected_names":len(selected),"positive_target_positions":int((target>0).sum()),
        "rows":rows,
        "explainability_status":"exact_reconstruction_from_unchanged_saved_inputs",
        "disclosure":"An exact calculation explanation is not causal attribution. Source inputs "
                     "may be unadjusted, survivorship-biased or independently unverified.",
    }


def explain_saved(kind: str, run_id: str, level: str = "researcher") -> dict:
    if level not in {"beginner","researcher","mathematical"}:
        raise ValueError("Choose beginner, researcher or mathematical explanation")
    if kind=="model_run":
        saved=model_lab.read_saved_model(run_id)
        spec=model_registry.CATALOG[saved["model_id"]]
        source=saved.get("source") or {}
        metrics=[{"name":m.get("label") or m.get("name"),"value":m.get("value"),"unit":m.get("unit","")}
                 for m in saved.get("metrics",[])[:35]]
        statements={
            "beginner":spec["description"],
            "researcher":spec["description"]+" Parameters, source type, fitted sample and "
                         "reported limitations must be reviewed before drawing conclusions.",
            "mathematical":spec["description"]+" Governing relation: "+spec["formula"],
        }
        return {"kind":kind,"id":run_id,"level":level,"model":spec["title"],
                "explanation":statements[level],"formula":spec["formula"],
                "parameters":saved.get("parameters",{}),"metrics":metrics,
                "assumptions":saved.get("assumptions",[]),"limitations":saved.get("limitations",[]),
                "source":source,"source_sha256":saved.get("source_sha256"),
                "execution_environment":saved.get("execution_environment"),
                "evidence_class":spec["mode"],
                "warning":"This is a deterministic explanation of archived output, not a "
                          "generative claim that the model predicts the market."}
    if kind=="research_run":
        result=service.run_details(run_id)
        meta=result["meta"]
        status=result["source"]
        cfg=meta.get("config",{})
        message={
            "beginner":"This experiment ranks eligible stocks by research factors, "
                       "constructs an index and compares the simulated returns to a benchmark.",
            "researcher":"As-of factor ranks determine rebalance decisions. Allocation bounds, "
                         "drift-aware turnover, transaction costs and an execution-delay assumption "
                         "affect the saved returns. Repeated parameter selection can overfit.",
            "mathematical":"Factor score s_i,t = Σ_k w_k z_k(i,t); constructed weights solve "
                           "a bounded constrained objective; simulated net return accounts for "
                           "pre-trade drift, turnover and cost; active risk uses r_p - r_b.",
        }
        return {"kind":kind,"id":run_id,"level":level,"model":"Multi-Factor Index Research",
                "explanation":message[level],"formula":message["mathematical"],
                "parameters":cfg,"metrics_by_split":meta.get("metrics_by_split",{}),
                "latest_positions":result["latest_weights"],
                "source":status,"source_hashes":meta.get("input_sha256",{}),
                "limitations":meta.get("limitations",[]),
                "evidence_class":"synthetic_demo" if status.get("dataset_kind")=="synthetic"
                                 else "observed_not_independently_verified",
                "warning":"Methodology and saved arithmetic are inspectable; a return series "
                          "does not establish a causal factor effect or investable alpha."}
    raise ValueError("Choose archived model_run or research_run")
