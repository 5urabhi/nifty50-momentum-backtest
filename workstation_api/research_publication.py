"""Frozen hypothesis preregistration and publication-safe methodology artifacts."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib
import json
import os
import re
import uuid
import tempfile
from . import research_next,service

ID=re.compile(r"^[A-Za-z0-9_-]{1,90}$")

def _root()->Path:
    return service.RESULTS.parent/"research_hypotheses"

def preregister(question:str,rationale:str,planned_dataset_id:str,
                primary_metric:str,success_criterion:str,design:str)->dict:
    values=(question,rationale,planned_dataset_id,primary_metric,success_criterion,design)
    if any(not isinstance(v,str) for v in values):
        raise ValueError("All hypothesis fields must be strings")
    if not 12<=len(question.strip())<=360 or not 12<=len(rationale.strip())<=2500:
        raise ValueError("Provide a clear hypothesis question and rationale")
    if not 2<=len(primary_metric)<=100 or not 4<=len(success_criterion)<=500:
        raise ValueError("Define an observable metric and criterion before results")
    if not 20<=len(design.strip())<=4000:
        raise ValueError("Specify an explicit data/split/estimator design")
    service.dataset_path(planned_dataset_id)
    body={"kind":"preregistered_hypothesis","id":"hyp_"+uuid.uuid4().hex[:16],
          "question":question.strip(),"rationale":rationale.strip(),
          "dataset_id":planned_dataset_id,"primary_metric":primary_metric.strip(),
          "success_criterion":success_criterion.strip(),"protocol":design.strip(),
          "registered_utc":datetime.now(timezone.utc).isoformat(),
          "status":"recorded_before_results_in_this_workflow",
          "warning":"Timestamp is not independently notarized. Prior exploratory "
                    "hypothesis searches are not excluded by this record."}
    canonical=json.dumps(body,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()
    body["registration_sha256"]=hashlib.sha256(canonical).hexdigest()
    directory=_root()
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/(body["id"]+".json")).open("xb") as f:
        f.write(json.dumps(body,indent=2,ensure_ascii=False).encode())
        f.flush()
        os.fsync(f.fileno())
    return body

def list_hypotheses()->list[dict]:
    root=_root()
    if not root.is_dir():return []
    found=[]
    for file in sorted(root.glob("hyp_*.json"),reverse=True)[:200]:
        if file.is_symlink() or not ID.fullmatch(file.stem):continue
        try:
            record=json.loads(file.read_text())
            if record["id"]!=file.stem:continue
            original=dict(record)
            digest=original.pop("registration_sha256",None)
            actual=hashlib.sha256(json.dumps(original,sort_keys=True,ensure_ascii=False,
                                             allow_nan=False).encode()).hexdigest()
            found.append({**record,"content_unchanged":digest==actual})
        except (OSError,ValueError,KeyError,TypeError):
            continue
    return found

def methodology(run_id:str)->dict:
    details=service.run_details(run_id)
    meta=details["meta"]
    cfg=meta["config"]
    origin=details["source"]
    dataset=origin.get("dataset_id")
    if not dataset:raise ValueError("Saved experiment lacks source identifier")
    port=research_next.passport(dataset)
    hashes={f["name"]:f["sha256"] for f in port["available_files"]}
    original=meta.get("input_sha256",{})
    mismatched=[name for name,digest in original.items() if hashes.get(name)!=digest]
    splits=meta.get("metrics_by_split",{})
    status=("SYNTHETIC EXAMPLE" if origin.get("dataset_kind")=="synthetic"
            else "OBSERVED, NOT INDEPENDENTLY CERTIFIED")
    lines=[
        "# "+str(cfg.get("name","Multi-Factor Equity Index Research")),
        "## Research question",
        "Does a rules-based multifactor index improve benchmark-relative "
        "risk-adjusted results under predefined concentration and turnover constraints?",
        "## Dataset and evidence",
        "- Status: "+status,
        "- Dataset: "+str(dataset),
        "- Observation interval: "+str(meta.get("first_price_date"))+
          " through "+str(meta.get("last_price_date")),
        "- Archived file SHA-256 checksums: "+json.dumps(original,sort_keys=True),
        "- Source unchanged since archived execution: "+str(not mismatched),
        "- Unresolved third-party evidence: "+", ".join(x["category"] for x in port["blockers"]),
        "## Hypothesis design",
        "A separate timestamped preregistration is required before treating a test "
        "as confirmatory. Repeated selection on final-test returns invalidates the holdout.",
        "## Factor and index methodology",
        "- Factor weights: "+json.dumps(cfg.get("factor_weights"),sort_keys=True),
        "- Momentum formation: "+str(cfg.get("momentum_formation"))+" months",
        "- Momentum skip: "+str(cfg.get("momentum_skip")),
        "- Volatility lookback: "+str(cfg.get("volatility_lookback")),
        "- Constituents: "+str(cfg.get("top_n")),
        "- Weighting method: "+str(cfg.get("weighting")),
        "- Security cap: "+str(cfg.get("max_weight")),
        "- Sector cap: "+str(cfg.get("sector_cap")),
        "- Reconstitution frequency: "+str(cfg.get("rebalance_every"))+" monthly observations",
        "- Execution lag: "+str(cfg.get("execution_lag"))+" monthly observations",
        "- Turnover cost basis points: "+str(cfg.get("cost_bps")),
        "## Results — descriptive only", "~~~json",
        json.dumps(splits,ensure_ascii=False,indent=2,sort_keys=True),"~~~",
        "## Failure modes and limitations",
        *["- "+str(v) for v in meta.get("limitations",[])],
        "- Unadjusted prices, survivorship, index memberships, delistings, "
        "licensing, benchmark TRI and execution fees remain external evidence requirements.",
        "- Multiple testing and model-selection bias require independent audit.",
        "## Reproducibility",
        "Run: python scripts/reproduce_study.py --run-id "+run_id,
        "This compares archived source hashes and recalculates selected "
        "numeric tables from original local inputs; it is not a certification "
        "of the original market data."
    ]
    return {"run_id":run_id,"title":str(cfg.get("name")),
            "source_status":status,"source_unchanged":not mismatched,
            "mismatched_input_files":mismatched,
            "markdown":"\n\n".join(lines)+"\n",
            "metrics_by_split":splits,"methodology_config":cfg,
            "dataset_id":dataset,"source_sha256":original,
            "external_research_certified":False,
            "status":"source_changed" if mismatched else "reproducibility_not_yet_recomputed"}

def bundle_path(run_id:str)->Path:
    if not ID.fullmatch(run_id):raise ValueError("Invalid index experiment ID")
    document=methodology(run_id)
    root=service.RESULTS.parent/"research_publications"
    root.mkdir(parents=True,exist_ok=True)
    target=root/(run_id+".zip")
    manifest={
        "format":"quantlab-research-methodology-v1",
        "run_id":run_id,"created_utc":datetime.now(timezone.utc).isoformat(),
        "data_license_policy":"No raw OHLCV, licensed historical membership, "
                              "broker credentials or proprietary source data are exported.",
        "source_sha256":document["source_sha256"],
        "status":document["status"],"independently_certified":False,
        "reproduce_command":"python scripts/reproduce_study.py --run-id "+run_id}
    files={
        "METHODS_AND_FINDINGS.md":document["markdown"].encode(),
        "model_config.json":json.dumps(document["methodology_config"],sort_keys=True,
                                       indent=2,allow_nan=False).encode(),
        "metrics_by_split.json":json.dumps(document["metrics_by_split"],sort_keys=True,
                                           indent=2,allow_nan=False).encode()}
    manifest["sha256"]={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    files["manifest.json"]=json.dumps(manifest,sort_keys=True,indent=2).encode()
    with tempfile.NamedTemporaryFile(dir=root,prefix="ql_",suffix=".zip",delete=False) as tmp:
        staged=Path(tmp.name)
    try:
        with ZipFile(staged,"w",ZIP_DEFLATED,compresslevel=6) as archive:
            for name,data in sorted(files.items()):
                archive.writestr(name,data)
        if staged.stat().st_size>3_000_000:
            raise ValueError("Research bundle exceeds maximum size")
        os.replace(staged,target)
    finally:
        staged.unlink(missing_ok=True)
    return target
