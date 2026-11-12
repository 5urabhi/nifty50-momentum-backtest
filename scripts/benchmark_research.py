#!/usr/bin/env python3
"""Bounded CPU/time/memory benchmark of the real factor and index engine.

ALL DATA GENERATED HERE ARE SYNTHETIC. This script never downloads market
data, touches canonical candles, or compares trading profitability.
"""
from __future__ import annotations
import argparse
import json
import platform
import time
import tracemalloc
from pathlib import Path
import numpy as np
import pandas as pd
from index_research.factors import composite_scores
from index_research.index import construct_weights,backtest_index


def benchmark(securities:int,periods:int,seed:int=2026)->dict:
    if not 5<=securities<=300 or not 50<=periods<=500:
        raise ValueError("Bound performance tests to 5–300 assets and 50–500 periods")
    rng=np.random.default_rng(seed+securities)
    dates=pd.date_range("2015-01-31",periods=periods,freq="ME")
    names=["FAKE_%03d"%i for i in range(securities)]
    market=rng.normal(.004,.035,periods)
    changes=np.clip(market[:,None]+rng.normal(0,.06,(periods,securities)),-.5,1.)
    frame=pd.DataFrame(100*np.cumprod(1+changes,axis=0),index=dates,columns=names)
    membership=pd.DataFrame(True,index=dates,columns=names)
    benchmark_returns=pd.Series(market,index=dates)
    tracemalloc.start()
    started=time.perf_counter()
    scores=composite_scores(frame,membership,{"momentum":.5,"low_volatility":.5},
                            momentum_formation=12,momentum_skip=1,
                            volatility_lookback=12)
    scored=time.perf_counter()
    count=min(20,securities)
    weights=construct_weights(scores,membership,top_n=count,
                              weighting="equal",cap=max(.10,1/count),
                              rebalance_every=3,prices=frame)
    weighted=time.perf_counter()
    result=backtest_index(frame,weights,benchmark_returns,
                          cost_bps=10.,execution_lag=1)
    finished=time.perf_counter()
    _,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "test_kind":"synthetic_software_performance_only",
        "assets":securities,"monthly_observations":periods,
        "security_months":securities*periods,
        "factor_score_seconds":round(scored-started,6),
        "weight_construction_seconds":round(weighted-scored,6),
        "backtest_seconds":round(finished-weighted,6),
        "total_seconds":round(finished-started,6),
        "python_peak_tracemalloc_bytes":peak,
        "positive_weight_periods":int(result.weights.gt(0).any(axis=1).sum()),
        "return_periods":len(result.returns),
        "seed":seed,
        "disclosure":"CPU and Python allocation benchmark only; not investment performance.",
    }


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets",default="20,50,100",
                        help="Comma-separated synthetic security universe sizes")
    parser.add_argument("--periods",type=int,default=120)
    parser.add_argument("--seed",type=int,default=2026)
    parser.add_argument("--output",default=None,help="Optional JSON output file")
    args=parser.parse_args()
    sizes=[int(x.strip()) for x in args.assets.split(",")]
    if len(sizes)>6 or not sizes:
        raise ValueError("At most six benchmark configurations")
    rows=[benchmark(n,args.periods,args.seed) for n in sizes]
    payload={"suite":"quantlab-software-scalability-v1",
             "python":platform.python_version(),"numpy":np.__version__,
             "pandas":pd.__version__,
             "cases":rows,
             "notice":"Deterministic synthetic benchmark; numbers depend on local hardware."}
    print(json.dumps(payload,indent=2))
    if args.output:
        filename=Path(args.output).expanduser().resolve()
        if filename.exists():raise FileExistsError("Refusing to overwrite existing benchmark output")
        filename.parent.mkdir(parents=True,exist_ok=True)
        filename.write_text(json.dumps(payload,indent=2)+"\n")


if __name__=="__main__":
    main()
