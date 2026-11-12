"""Prepare an explicitly biased static-universe exercise from the original CSV.

This is NOT a Nifty 50 history, NOT a historical membership reconstruction,
NOT a real benchmark and NOT a source of defensible performance claims.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd


def prepare(src: str | Path, out: str | Path, minimum_names: int = 15) -> Path:
    root=Path(out)
    root.mkdir(parents=True,exist_ok=True)
    x=pd.read_csv(src)
    dates=pd.to_datetime(x.iloc[:,0],errors="raise")
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("legacy source dates not unique/ordered")
    values=x.iloc[:,1:].apply(pd.to_numeric,errors="coerce")
    if values.columns.has_duplicates:
        raise ValueError("duplicate identifiers")
    # Conservative demonstration cohort: complete-case selection across the
    # entire period. This is textbook survivorship bias; it is disclosed.
    chosen=values.columns[(values.notna() & (values>0) & np.isfinite(values)).all(axis=0)]
    if len(chosen)<minimum_names:
        raise ValueError("Too few full-history tickers for demonstration; no imputation attempted")
    if len(dates)<30:
        raise ValueError("Need >=30 monthly observations")
    prices=values[chosen].copy()
    prices.index=dates
    # Preserve ambiguous source labels exactly; do not claim true month end.
    prices.to_csv(root/"prices.csv",index_label="date")
    pd.DataFrame({"date":[str(dates.iloc[0].date())]*len(chosen),
        "ticker":chosen,"eligible":[True]*len(chosen)}).to_csv(root/"membership.csv",index=False)
    simple=prices.pct_change(fill_method=None)
    equal_weight=simple.mean(axis=1)
    equal_weight.iloc[0]=0.0
    pd.DataFrame({"date":dates, "return":equal_weight.to_numpy()}).to_csv(root/"benchmark.csv",index=False)
    caveats={
        "status":"STATIC UNIVERSE DEMONSTRATION - NOT POINT-IN-TIME",
        "source_file":str(src),
        "dates":"Source month labels preserved; day-of-month may not reflect true execution/close.",
        "survivorship":"Includes only symbols with complete price records across the entire source.",
        "membership":"All selected assets marked eligible historically, NOT historical index evidence.",
        "benchmark":"Synthetic construct: equal-weighted COMPLETE-CASE cohort monthly returns, NOT Nifty 50.",
        "factor_universe":"Momentum and low-volatility only; Value/Quality/Size require as-of fundamentals.",
        "resume":"Never claim this exercise measures verified Nifty index outperformance."
    }
    (root/"DEMONSTRATION_LIMITATIONS.json").write_text(json.dumps(caveats,indent=2))
    return root


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="nifty50_prices_monthly.csv")
    p.add_argument("--output-dir",default="data/legacy_static_demo")
    args=p.parse_args()
    print(prepare(args.source,args.output_dir))
    print("STATIC UNIVERSE DEMONSTRATION WITH SURVIVORSHIP BIAS ONLY")


if __name__=="__main__":
    main()
