"""Explicit, one-instrument Dhan live-candle verification, without overwrites.

A source checksum match is not a verification of dividends or PIT membership.
This only tests a recent, observed, previously cached local instrument against
Dhan's current historical-data endpoint, after a deliberate user confirmation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import math
import os
import uuid

import pandas as pd

from index_research.dhan_data import Instrument, download_candles
from . import dhan_auth, model_data_manager, research_integrity, service


def _result_path(dataset_id: str) -> Path:
    if not service.SAFE_ID.fullmatch(dataset_id):
        raise ValueError("Invalid dataset identifier")
    dest=service.RESULTS.parent/"integrity_evidence"/("dhan_live_"+dataset_id+".json")
    if dest.is_symlink():raise ValueError("Unsafe live-data verification record")
    return dest


def plan(dataset_id: str, column: str | None = None) -> dict:
    folder, record=service.dataset_path(dataset_id)
    if record.get("kind")!="dhan" or not record.get("has_daily_prices"):
        return {"dataset_id":dataset_id,"available":False,"reason":
                "Choose a prepared DAILY Dhan dataset with a verified instrument mapping."}
    path=folder/"daily_prices.csv"
    if path.is_symlink() or not path.is_file():
        return {"dataset_id":dataset_id,"available":False,"reason":"Daily Dhan price matrix unavailable"}
    info=research_integrity.inspect(dataset_id)
    mapping_path=(folder/("SHARED_MARKET_PROVENANCE.json" if dataset_id=="dhan_shared"
                          else "DHAN_BATCH_PROVENANCE.json"))
    provenance=research_integrity._read_json(mapping_path)
    mapped=[v for v in provenance.get("columns",[]) if isinstance(v,dict)]
    keys=[str(v.get("column","")) for v in mapped]
    if not keys:
        return {"dataset_id":dataset_id,"available":False,"reason":
                "No source-mapped Dhan daily-equity columns were found."}
    if column is not None and column not in keys:
        raise ValueError("Requested column is not in the Dhan source mappings")
    # A user can pick a mapped instrument. Do not rely on current ticker name
    # to infer historical security identity.
    choices=[column] if column is not None else keys[:18]
    selected=None
    for key in choices:
        try:
            found,reason=model_data_manager._mapping(dataset_id,[key])
            if reason or not found:continue
            series=pd.read_csv(path,usecols=["date",key],parse_dates=["date"])
            valid=series[["date",key]].dropna().sort_values("date")
            if valid["date"].duplicated().any() or len(valid)<4:continue
            selected=(key,found[0],valid)
            break
        except (OSError,ValueError,KeyError):
            continue
    if selected is None:
        return {"dataset_id":dataset_id,"available":False,"reason":
                "No sampled mapped equity has at least four valid, unique cached dates. "
                "Refresh the Dhan master and inspect local history."}
    key,item,valid=selected
    last=valid.iloc[-1]["date"].date()
    today=date.today()
    if last>today:
        raise ValueError("Cached market data contains future-dated observations")
    recent=valid.tail(10)
    first=recent.iloc[0]["date"].date()
    end=min(today+timedelta(days=1),last+timedelta(days=1))
    return {
        "dataset_id":dataset_id,"available":True,"instrument_column":key,
        "symbol":item["symbol"],"instrument_id":item["id"],
        "from_date":first.isoformat(),"to_date_exclusive":end.isoformat(),
        "cached_sample_sessions":len(recent),
        "source_file":"daily_prices.csv","source_sha256":info["source_sha256"],
        "will_download":True,"will_append":False,"will_submit_orders":False,
        "note":"An explicit read-only single-instrument probe. It does not "
               "overwrite cached candles, extend the shared dataset, or establish TRI/PIT accuracy.",
    }


def previous(dataset_id: str) -> dict:
    record=research_integrity._read_json(_result_path(dataset_id))
    if not record:return {"dataset_id":dataset_id,"status":"not_run"}
    info=research_integrity.inspect(dataset_id)
    return {**record,"stale":record.get("source_sha256")!=info["source_sha256"]}


def probe(dataset_id: str, column: str, *, confirm: bool = False) -> dict:
    if not confirm:
        raise ValueError("Live vendor history probe requires explicit user confirmation")
    spec=plan(dataset_id,column)
    if not spec.get("available"):
        raise ValueError(spec.get("reason","Live verification unavailable"))
    auth=dhan_auth.check_profile()
    if not auth.get("ok"):
        raise ValueError(auth.get("message","Dhan historical-data entitlement cannot be verified"))
    matched,reason=model_data_manager._mapping(dataset_id,[column])
    if reason or len(matched)!=1:
        raise ValueError(reason or "Instrument identity mapping became invalid")
    item=matched[0]
    instrument=Instrument(label="VERIFICATION_"+item["security_id"],
        security_id=item["security_id"],exchange_segment=item["exchange_segment"],
        instrument="EQUITY")
    # The vendor adapter is read-only (market-history endpoint); we never call
    # its save_download() or the shared_market_data.ingest() codepaths.
    live=download_candles(instrument,spec["from_date"],
                         spec["to_date_exclusive"],interval=None)
    if live.empty or not {"datetime","close"}.issubset(live.columns):
        raise ValueError("The vendor did not return valid daily close observations")
    live_dates=pd.to_datetime(live["datetime"],utc=True,errors="raise").dt.tz_convert("Asia/Kolkata").dt.date
    vendor=pd.Series(pd.to_numeric(live["close"],errors="raise").to_numpy(),index=live_dates)
    if vendor.index.has_duplicates:
        raise ValueError("Live Dhan sample has duplicate session dates")
    folder,_=service.dataset_path(dataset_id)
    path=folder/"daily_prices.csv"
    original=pd.read_csv(path,usecols=["date",column],parse_dates=["date"]).dropna()
    original["day"]=original["date"].dt.date
    cached=original.set_index("day")[column]
    aligned=pd.concat([cached.rename("cached"),vendor.rename("live")],axis=1,join="inner")
    aligned=aligned.loc[(aligned.index>=date.fromisoformat(spec["from_date"]))&
                        (aligned.index<date.fromisoformat(spec["to_date_exclusive"]))]
    if len(aligned)<3:
        result_status="insufficient_overlap"
    else:
        diff=abs(aligned["cached"]-aligned["live"])
        tol=0.03 + 0.0005*abs(aligned["live"])
        result_status="matched" if (diff<=tol).all() else "mismatch"
    sha_after=research_integrity._sha(path)
    if sha_after!=spec["source_sha256"]:
        raise ValueError("Source dataset changed during probe; discard live comparison")
    rows_with_mismatch=0
    if len(aligned):
        rows_with_mismatch=int((abs(aligned["cached"]-aligned["live"]) >
                                (0.03+0.0005*abs(aligned["live"]))).sum())
    result={
        "dataset_id":dataset_id,"column":column,"vendor_instrument_id":item["id"],
        "status":result_status,"compared_sessions":len(aligned),
        "vendor_returned_sessions":len(vendor),
        "mismatched_sessions":rows_with_mismatch,
        "source_sha256":sha_after,"source_unchanged":True,
        "checked_utc":datetime.now(timezone.utc).isoformat(),
        "tolerance":"absolute INR 0.03 plus relative 0.05%",
        "live_profile_verified":True,
        "raw_price_data_modified":False,
        "orders_submitted":0,
        "warning":"A match verifies only this sampled instrument/date window against the "
                  "vendor's current endpoint. It does not prove completeness, original "
                  "publication-date availability, dividend total returns or historical membership.",
    }
    dest=_result_path(dataset_id)
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_name(dest.name+"."+uuid.uuid4().hex[:8]+".tmp")
    try:
        temp.write_text(json.dumps(result,indent=2,allow_nan=False))
        os.replace(temp,dest)
    finally:
        temp.unlink(missing_ok=True)
    return result
