"""Explicit opt-in exporter for public static dashboard (Vercel later).

Only summary and aggregated return series are exported. No raw securities or
holdings. This does NOT turn private/licensed data into redistributable data.
"""
import argparse
import json
import shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--results-dir",required=True)
    p.add_argument("--publish",action="store_true",help="Confirm deliberate public export")
    args=p.parse_args()
    if not args.publish:
        p.error("Refusing public export without --publish acknowledgment")
    root=Path(args.results_dir)
    metadata=json.loads((root/"research_manifest.json").read_text())
    source=root/"monthly_results.csv"
    if not source.exists():
        raise FileNotFoundError(source)
    dest=Path(__file__).resolve().parents[1]/"public"/"data"
    dest.mkdir(parents=True,exist_ok=True)
    # Keep only non-identifying summaries; do NOT include source hash/vintage,
    # notes or input tickers in publicly deployed static metadata.
    safe={
        "name":metadata["config"].get("name"),
        "dataset_status":metadata["config"].get("dataset_status"),
        "benchmark_name":metadata["config"].get("benchmark_name"),
        "metrics_by_split":metadata.get("metrics_by_split",{}),
        "limitations":metadata.get("limitations",[]),
    }
    (dest/"summary.json").write_text(json.dumps(safe,indent=2,allow_nan=False))
    import pandas as pd
    values=pd.read_csv(source,usecols=["date","strategy_net","benchmark","turnover"])
    values.to_csv(dest/"returns.csv",index=False)
    print("Vite public snapshot prepared in",dest)
    print("PUBLIC-DATA WARNING: inspect generated public/data files and source licenses before any deploy.")


if __name__=="__main__":
    main()
