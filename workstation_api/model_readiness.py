"""One-pass model-specific data readiness; never call synthetic runs empirical.

Source sufficiency is a preflight, not a guarantee that an optimizer or
stochastic estimator converges on every numerically pathological series.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from index_research.data import read_matrix, read_returns
from . import model_registry, service, option_quotes


MATH = {"synthetic":"simulation", "theoretical":"theory"}


def overview(dataset_id: str | None = None) -> dict:
    prices: pd.DataFrame | None=None
    daily=False
    tri=False
    tri_count=0
    snapshot_count=0
    dataset_label="No dataset selected"
    data_problem=""
    synthetic_fixture=False
    if dataset_id:
        try:
            folder,info=service.dataset_path(dataset_id)
            dataset_label=info.get("label",dataset_id)
            synthetic_fixture=info.get("kind")=="synthetic" or (folder/"DO_NOT_CITE.txt").exists()
            file="daily_prices.csv" if info.get("has_daily_prices") else "prices.csv"
            daily=file=="daily_prices.csv"
            if info.get("has_prices"):
                prices=read_matrix(folder/file,positive=True)
            benchmark=folder/"benchmark.csv"
            proof=folder/"BENCHMARK_SOURCE.json"
            if benchmark.is_file() and proof.is_file() and not (
                    benchmark.is_symlink() or proof.is_symlink()):
                import json
                meta=json.loads(proof.read_text(encoding="utf-8"))
                if meta.get("return_convention") in {"gross_total_return","net_total_return"}:
                    series=read_returns(benchmark)
                    tri_count=len(series)
                    tri=tri_count>=10
            snapshot_count=sum(len(s["contracts"]) for s in option_quotes.list_for(dataset_id))
        except (OSError,ValueError,KeyError,TypeError) as exc:
            data_problem=str(exc)[:160]
    returns=None if prices is None else prices.pct_change(fill_method=None).replace(
        [np.inf,-np.inf],np.nan)
    assets_with10=0 if returns is None else int((returns.notna().sum()>=10).sum())
    source_counts={}

    def historical_ready(model_id: str, minimum: int) -> tuple[bool,str,str]:
        if prices is None or returns is None:
            return (False,"No historical price panel available",
                    "Import or download original Dhan stock prices")
        if model_id=="gbm_fit":
            if tri:
                return (True,f"{tri_count} source-linked NIFTY TRI returns",
                        "Choose NIFTY TRI as target")
            if assets_with10:
                return (True,f"{assets_with10} stock(s) have 10+ observed returns",
                        "Choose target=stock and its exact ticker")
            return (False,"GBM requires ≥10 returns for one series",
                    "Extend original price history")
        if model_id in {"ou_fit","heston_proxy","merton_fit"}:
            needed={"ou_fit":90,"heston_proxy":252,"merton_fit":120}[model_id]
            count=int((returns.notna().sum()>=needed).sum())
            if model_id!="merton_fit" and not daily:
                return (False,"Daily observations required; monthly index is insufficient",
                        "Choose an original Dhan daily stock dataset")
            if count>0:
                return (True,f"{count} stock(s) with ≥{needed} observed returns",
                        "Choose one exact ticker; no stock is silently substituted")
            return (False,f"No stock has ≥{needed} nonmissing returns",
                    "Extend genuine Dhan daily history")
        count=8
        rows=sorted(returns.columns,
            key=lambda c:(-int(returns[c].notna().sum()),str(c)))[:count]
        if len(rows)<count:
            return (False,f"{len(rows)}/{count} required stock series present",
                    "Select a dataset with more securities")
        common=returns[rows].dropna()
        required=max(minimum,90) if model_id=="rolling_vol" else minimum
        if len(common)<required:
            return (False,f"{len(common)}/{required} aligned return observations for {count} stocks",
                    "Extend common observed Dhan returns or lower configured asset count")
        if (common.std(ddof=1)<=1e-10).any():
            return (False,"Constant or unusable return series in the selected subset",
                    "Review stock mappings and price history")
        return (True,f"{len(common)} aligned observed returns for {count} stocks",
                "Choose parameters and run; this is a source preflight, not validation")

    for spec in model_registry.MODELS:
        key=spec["id"]; mode=spec["mode"]
        if mode in MATH:
            status="math_ready"
            detail=("Numerical/analytical algorithm runs with explicit parameters."
                    " Simulated curves remain hypothetical.")
            action="Run mathematics mode or switch to its market-data companion"
            source_ready=False
        elif mode=="market":
            source_ready=snapshot_count>0
            status="source_available" if source_ready else "need_option_quote"
            detail=(f"{snapshot_count} original provider option contracts available"
                    if source_ready else "No timestamped original option bid/ask snapshot imported")
            action=("Select one stored quote and choose rate/dividend assumptions"
                    if source_ready else
                    "Use original option quote CSV importer; don't fabricate a premium")
        else:
            source_ready,detail,action=historical_ready(key,int(spec["min_observations"]))
            if synthetic_fixture:
                source_ready=False
                detail=("SYNTHETIC FIXTURE ONLY — model can execute, but this is not "
                        "observed historical market evidence")
                action="Choose an actual observed Dhan or source-linked NIFTY TRI dataset"
                status="fixture_only"
            else:
                status="source_available" if source_ready else "need_historical_data"
            if key=="heston_proxy":
                detail+="; proxy only — latent risk-neutral Heston NOT calibrated"
        source_counts[key]={
            "id":key,"group":spec["group"],"title":spec["title"],"mode":mode,
            "status":status,"source_ready":source_ready,
            "mathematics_ready":mode in MATH,
            "detail":detail,"next_action":action,
            "warning":"Preflight does not claim external certification or successful numerical convergence.",
        }
    values=list(source_counts.values())
    return {
        "dataset_id":dataset_id,"dataset_label":dataset_label,
        "total_models":len(values),
        "math_ready":sum(x["status"]=="math_ready" for x in values),
        "historical_source_ready":sum(x["status"]=="source_available" and
                                      x["mode"]=="historical" for x in values),
        "option_source_ready":sum(x["status"]=="source_available" and
                                  x["mode"]=="market" for x in values),
        "input_blocked":sum(x["status"] in {
            "need_option_quote","need_historical_data","fixture_only"} for x in values),
        "synthetic_fixture_selected":synthetic_fixture,
        "available_original_option_contracts":snapshot_count,
        "data_problem":data_problem,
        "models":values,
        "not_a_market_performance_certification":True,
    }
