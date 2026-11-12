"""Evidence ledger for QuantLab market-data research.

This intentionally does not certify returns: submitting an URL, obtaining a
checksum, or successfully downloading a candle is NOT independent evidence
that historical index membership, dividends, or executions were correct.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import os
import re
import uuid

from . import service

CATEGORIES = {
    "prices": ("Observed historical prices", "Source OHLCV, adjustment rules and timestamp checks"),
    "membership": ("Point-in-time membership", "Dated index notices with acquisition-vintage evidence"),
    "actions": ("Corporate actions and dividends", "Split, bonus and cash-distribution adjustments by event date"),
    "benchmark": ("Comparable total-return benchmark", "A matched-frequency independently verified TRI"),
    "delistings": ("Delisted and renamed constituents", "Unavailable/ambiguous historical securities accounted for"),
    "fundamentals": ("Publication-dated fundamentals", "Actual availability timestamps, no future information"),
    "costs": ("Trading costs", "Commissions, spreads, impact and taxes validated for the tested universe"),
    "execution": ("Prospective execution", "Timestamped quotes/fills; simulated results are not live trading"),
}
SENSITIVE = re.compile(r"(?i)(access[_ -]?token|bearer\s+\S+|password|api[_ -]?key|private[_ -]?key)")
SHA = re.compile(r"^[0-9a-f]{64}$")


def _root() -> Path:
    return service.RESULTS.parent / "integrity_evidence"


def _sha(path: Path) -> str:
    value=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _read_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024 * 1024:
        return {}
    try:
        value=json.loads(path.read_text())
        return value if isinstance(value,dict) else {}
    except (ValueError, UnicodeError, OSError):
        return {}


def _price(folder: Path, record: dict) -> tuple[str | None, str | None]:
    source="daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
    file=folder/source
    if not file.is_file() or file.is_symlink():
        return None,None
    return source,_sha(file)


def _ledger(dataset_id: str) -> Path:
    if not service.SAFE_ID.fullmatch(dataset_id):
        raise ValueError("Invalid dataset ID")
    target=_root()/(dataset_id+".json")
    if target.is_symlink():
        raise ValueError("Unsafe review ledger")
    return target


def inspect(dataset_id: str) -> dict:
    folder,record=service.dataset_path(dataset_id)
    source,digest=_price(folder,record)
    pit=_read_json(folder/"PIT_MEMBERSHIP_PROVENANCE.json")
    benchmark=_read_json(folder/"BENCHMARK_PROVENANCE.json")
    review=_read_json(folder/"EVIDENCE_REVIEW.json")
    ledger=_read_json(_ledger(dataset_id))
    submitted=ledger.get("references",[])
    if not isinstance(submitted,list):
        submitted=[]
    missing_pit=pit.get("missing_historical_symbols",[]) or []
    if not isinstance(missing_pit,list):
        missing_pit=[]
    evidence={
        "prices": bool(digest),
        "membership": bool(pit.get("source_sha256") and (folder/"membership.csv").is_file()),
        "actions": bool((folder/"corporate_actions.csv").is_file() and review.get("corporate_actions")),
        "benchmark": bool(benchmark.get("is_total_return_index") and
                          benchmark.get("is_independently_verified") and
                          (folder/"benchmark.csv").is_file()),
        "delistings": bool(pit.get("source_sha256") and not missing_pit and
                           pit.get("historical_universe_reviewed",False)),
        "fundamentals": bool((folder/"fundamentals.csv").is_file() and
                             review.get("publication_dated_fundamentals")),
        "costs": bool(review.get("historical_cost_model_independently_checked")),
        "execution": bool(review.get("prospective_timestamped_execution")),
    }
    rows=[]
    for key,(label,criterion) in CATEGORIES.items():
        refs=[{
            "source_url":v.get("source_url"),"as_of":v.get("as_of"),
            "recorded_utc":v.get("recorded_utc"),
            "stale":v.get("dataset_sha256")!=digest,
        } for v in submitted if isinstance(v,dict) and v.get("category")==key]
        rows.append({
            "category":key,"label":label,"criterion":criterion,
            "status":("documented_not_certified" if evidence[key] else
                      "submitted_for_review" if any(not r["stale"] for r in refs) else "missing"),
            "source_references":refs,
            "evidence_present":evidence[key],
        })
    missing=[r["category"] for r in rows if not r["evidence_present"]]
    return {
        "dataset_id":dataset_id,"dataset":record["label"],
        "source_file":source,"source_sha256":digest,
        "dataset_kind":record.get("kind"),
        "evidence":rows,"unresolved_historical_symbols":len(missing_pit),
        "documented_categories":len(rows)-len(missing),
        "missing_categories":missing,
        "ready_for_descriptive_prices":bool(digest),
        "historical_investability_certified":False,
        "prospective_trading_certified":False,
        "warning":"Available files and human-submitted source links are not independent "
                  "certifications. No trading-performance or dividend TRI conclusion "
                  "is automatically approved. Do not infer missing events are zero.",
    }


def add_source(dataset_id: str, category: str, source_url: str,
               as_of: str, explanation: str = "") -> dict:
    if category not in CATEGORIES:
        raise ValueError("Unknown research evidence category")
    parts=urlsplit(source_url)
    if (parts.scheme!="https" or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment
            or len(source_url)>500 or SENSITIVE.search(source_url)):
        raise ValueError("Use a plain public HTTPS evidence link without credentials or query tokens")
    stamp=date.fromisoformat(as_of)
    if stamp>date.today():
        raise ValueError("Evidence cannot be dated in the future")
    if not isinstance(explanation,str) or len(explanation)>1200 or SENSITIVE.search(explanation):
        raise ValueError("Evidence note must be short and contain no credentials")
    existing=inspect(dataset_id)
    if not existing["source_sha256"]:
        raise ValueError("Attach evidence only to a dataset containing price observations")
    target=_ledger(dataset_id)
    prior=_read_json(target)
    refs=prior.get("references",[])
    if not isinstance(refs,list):refs=[]
    if len(refs)>=80:raise ValueError("Maximum 80 cited evidence references per dataset")
    item={
        "id":"ref_"+uuid.uuid4().hex[:12],"category":category,
        "source_url":source_url,"as_of":as_of,"explanation":explanation.strip(),
        "dataset_sha256":existing["source_sha256"],
        "recorded_utc":datetime.now(timezone.utc).isoformat(),
        "review_status":"submitted_unverified",
    }
    refs.append(item)
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name(target.name+"."+uuid.uuid4().hex[:8]+".tmp")
    try:
        temp.write_text(json.dumps({"dataset_id":dataset_id,"references":refs},
                                   indent=2,ensure_ascii=False,allow_nan=False))
        os.replace(temp,target)
    finally:
        temp.unlink(missing_ok=True)
    return {"id":item["id"],"category":category,
            "review_status":"submitted_unverified",
            "message":"Source reference recorded against the current dataset checksum; "
                      "no statistical or independent certification was granted."}
