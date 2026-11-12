#!/usr/bin/env python3
"""One-command reproduction of a saved index experiment using original LOCAL inputs.

Examples:
    python scripts/reproduce_study.py --run-id 20261113T123000_abcd1234
    python scripts/reproduce_study.py --run-id ... --json

No licensed market input is downloaded and no original output is overwritten.
Exit 0 only if all checked source files and numerical tables match.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

import numpy as np
import pandas as pd

from index_research.experiment import ExperimentConfig,run_from_directory
from workstation_api import research_next,service


def reproduce(run_id: str) -> dict:
    archive=service._run_path(run_id)
    raw=service.run_details(run_id)
    origin=raw["source"]
    dataset=origin.get("dataset_id")
    if not dataset:raise ValueError("Archived run has no linked source dataset")
    folder,_=service.dataset_path(dataset)
    recorded=raw["meta"].get("input_sha256",{})
    if not recorded:
        raise ValueError("Archived study lacks source-file checksums")
    hashes={}
    for name,digest in recorded.items():
        if Path(name).name!=name or not name.endswith(".csv"):
            raise ValueError("Invalid archived data source file")
        path=folder/name
        if not path.is_file() or path.is_symlink():
            raise ValueError("Missing original source file: "+name)
        current=research_next._file_sha(path)
        hashes[name]={"saved":digest,"current":current,"matches":digest==current}
    if not all(row["matches"] for row in hashes.values()):
        return {"run_id":run_id,"status":"source_changed","input_hashes":hashes,
                "verified":False,"investment_evidence_certified":False}
    config=ExperimentConfig(**raw["meta"]["config"])
    inspected={}
    with TemporaryDirectory(prefix="quantlab_repro_") as workspace:
        temp=Path(workspace)/"new_run"
        run_from_directory(folder,temp,config)
        for filename in ("monthly_results.csv","post_rebalance_weights.csv","factor_scores.csv"):
            a=archive/filename
            b=temp/filename
            if not a.is_file() or not b.is_file():
                inspected[filename]={"matched":False,"reason":"Missing numeric output"}
                continue
            old=pd.read_csv(a,index_col=0)
            new=pd.read_csv(b,index_col=0)
            if not old.columns.equals(new.columns) or not old.index.equals(new.index):
                inspected[filename]={"matched":False,"reason":"Dates or columns differ"}
                continue
            x=old.to_numpy(dtype=float)
            y=new.to_numpy(dtype=float)
            same_nan=np.array_equal(np.isnan(x),np.isnan(y))
            finite=np.isfinite(x)&np.isfinite(y)
            max_delta=(float(np.max(np.abs(x[finite]-y[finite]))) if finite.any() else 0.)
            close=(same_nan and bool(np.isfinite(x[~np.isnan(x)]).all())
                   and bool(np.isfinite(y[~np.isnan(y)]).all())
                   and bool(np.allclose(x,y,rtol=1e-8,atol=1e-10,equal_nan=True)))
            inspected[filename]={"matched":close,"observations":len(old),
                                 "max_absolute_difference":max_delta}
    success=all(row["matched"] for row in inspected.values())
    return {"run_id":run_id,"status":"numerically_reproduced" if success else "numeric_mismatch",
            "verified":success,"source_dataset":dataset,
            "input_hashes":hashes,"numeric_tables":inspected,
            "investment_evidence_certified":False,
            "warning":"Numerical reproducibility does not audit historical data, "
                      "PIT constituents, dividend TRIs, trading costs or actual execution."}


def main(argv=None)->int:
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run-id",required=True,help="Archived local QuantLab index run ID")
    cli.add_argument("--json",action="store_true",help="Print structured JSON verification record")
    args=cli.parse_args(argv)
    try:
        output=reproduce(args.run_id)
        if args.json:print(json.dumps(output,indent=2,allow_nan=False))
        else:
            print("Reproduction:",output["status"])
            for file,check in output.get("numeric_tables",{}).items():
                print(" ",file,check)
            print("Investment evidence: NOT independently certified")
        return 0 if output["verified"] else 2
    except (ValueError,FileNotFoundError) as exc:
        print("REPRODUCTION BLOCKED:",exc,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
