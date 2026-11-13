"""Like-for-like multi-methodology index research comparison.

Every methodology uses the same dates, members, benchmark, costs and
evaluation windows. Parameter selection still needs an untouched holdout.
"""
from dataclasses import replace
import pandas as pd
from .experiment import ExperimentConfig, run_experiment
from .research_analytics import compare_methodologies


def compare_index_methods(prices: pd.DataFrame, membership: pd.DataFrame,
                          benchmark: pd.Series, fundamentals: pd.DataFrame | None,
                          baseline: ExperimentConfig,
                          sectors: pd.DataFrame | None = None,
                          benchmark_history: pd.DataFrame | None = None,
                          liquidity_records: pd.DataFrame | None = None) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Compare long-only factor weighting, keeping all inputs and costs fixed.

    Raises on invalid/infeasible variants instead of hiding methods silently.
    Only finite periods at which all methods have observations are compared.
    """
    variants={
        "momentum_equal":replace(baseline,factor_weights={"momentum":1.0},weighting="equal"),
        "momentum_score":replace(baseline,factor_weights={"momentum":1.0},weighting="score"),
        "low_vol_equal":replace(baseline,factor_weights={"low_volatility":1.0},weighting="equal"),
    }
    requested=baseline.factor_weights or {"momentum":1.0}
    variants["selected_composite"]=replace(baseline,factor_weights=requested)
    histories={}
    for name,config in variants.items():
        result,_,_=run_experiment(
            prices,membership,benchmark,fundamentals,config,sectors=sectors,
            benchmark_history=benchmark_history,liquidity_records=liquidity_records)
        histories[name]=result.returns
    series=pd.DataFrame(histories)
    if series.isna().any().any() or series.empty:
        raise ValueError("methodology comparison requires complete aligned results")
    summary=compare_methodologies(histories,benchmark.loc[series.index])
    return series,summary
