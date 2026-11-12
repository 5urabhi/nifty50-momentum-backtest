"""Predeclared sensitivity experiments, never maximize over the final holdout.

A returned ranking of robustness alternatives is descriptive, not a model
selection recommendation; data mining can bias all displayed outcomes.
"""
from dataclasses import replace
import numpy as np
import pandas as pd
from .experiment import ExperimentConfig, run_experiment, performance_metrics


def sensitivity_grid(prices: pd.DataFrame, membership: pd.DataFrame,
                     benchmark: pd.Series, fundamentals: pd.DataFrame | None,
                     baseline: ExperimentConfig, sectors: pd.DataFrame | None = None,
                     costs_bps: tuple[float,...]=(0.,10.,25.),
                     rebalance_months: tuple[int,...]=(1,3,6),
                     execution_lags: tuple[int,...]=(0,1),
                     segment: str="validation") -> pd.DataFrame:
    """Run matched conditions over an explicitly specified grid.

    Final holdout should be reserved for ONE frozen method; this function
    refuses to select/focus on final_test. Use only development/validation.
    """
    if segment not in {"development","validation","full_history"}:
        raise ValueError("sensitivity cannot select the frozen final_test")
    if any(x<0 for x in costs_bps) or any(x<1 for x in rebalance_months) or any(x not in (0,1) for x in execution_lags):
        raise ValueError("invalid sensitivity parameters")
    if len(costs_bps)*len(rebalance_months)*len(execution_lags)>60:
        raise ValueError("sensitivity grid exceeds 60 experiments")
    evaluations=[]
    for rebalance in rebalance_months:
        for lag in execution_lags:
            for cost in costs_bps:
                config=replace(baseline,rebalance_every=rebalance,execution_lag=lag,
                               cost_bps=float(cost))
                result,_,meta=run_experiment(prices,membership,benchmark,
                                              fundamentals,config,sectors=sectors)
                stats=meta["metrics_by_split"].get(segment)
                if stats is None:
                    continue
                evaluations.append({
                    "reconstitution_months":int(rebalance),
                    "execution_lag_months":int(lag),
                    "transaction_cost_bps":float(cost),
                    **stats
                })
    return pd.DataFrame(evaluations)


def parameter_dispersion(results: pd.DataFrame, metric: str="strategy_cagr") -> dict:
    """Report dispersion, never select best-performing config as definitive."""
    if results.empty or metric not in results:
        raise ValueError("no observations or missing metric")
    values=pd.to_numeric(results[metric],errors="coerce").dropna()
    if values.empty:
        raise ValueError("no finite metric observations")
    return {
        "runs_with_metric":int(len(values)),
        "median":float(values.median()),
        "min":float(values.min()),
        "max":float(values.max()),
        "interquartile_range":float(values.quantile(.75)-values.quantile(.25)),
        "warning":"Many tested configurations create selection bias; do not choose the maximum as a final-test performance claim."
    }
