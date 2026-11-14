"""Versioned read-only option-quote snapshots supplied by an authorized source.

Quote values must come from an original licensed export; no synthetic
option prices are produced by this importer. Source claims remain user
declared. No broker order endpoint, authentication token or remote request.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import hashlib
import json
import math
import os
import re
import uuid

import pandas as pd

from . import service

NAME=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._&-]{0,31}$")
QUOTE_ID=re.compile(r"^oq_[0-9a-f]{20}$")
COLUMNS={"captured_at","provider","underlying","underlying_spot",
         "expiry_at","strike","option_type","bid","ask"}
MAX_BYTES=350_000
MAX_ROWS=300
MAX_LIST=100


def _root() -> Path:
    return service.DATA / "model_option_quotes"


def _entry_path(quote_id: str) -> tuple[Path,Path]:
    if not QUOTE_ID.fullmatch(quote_id):
        raise ValueError("Invalid option quote identifier")
    root=_root()
    return root/(quote_id+".csv"),root/(quote_id+".json")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate(raw: bytes) -> list[dict]:
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:
        raise ValueError("Choose an original option quote CSV under 350 KB")
    try:
        frame=pd.read_csv(BytesIO(raw),dtype=str,keep_default_na=False)
    except (ValueError,UnicodeDecodeError) as err:
        raise ValueError("Option source must be a valid UTF-8 CSV") from err
    if not COLUMNS.issubset(frame.columns):
        raise ValueError("Original quote CSV needs: "+", ".join(sorted(COLUMNS)))
    if len(frame)<1 or len(frame)>MAX_ROWS:
        raise ValueError("One to 300 original contracts per quote CSV are allowed")
    rows=[]
    for i,row in frame.iterrows():
        values={k:str(row[k]).strip() for k in COLUMNS}
        if not NAME.fullmatch(values["underlying"]):
            raise ValueError(f"Row {i+1}: invalid underlying ticker")
        provider=values["provider"]
        if not 2<=len(provider)<=65 or any(ord(c)<32 for c in provider):
            raise ValueError(f"Row {i+1}: original provider name required")
        try:
            captured=pd.Timestamp(values["captured_at"])
            expiry=pd.Timestamp(values["expiry_at"])
            if captured.tzinfo is None:
                raise ValueError("Capture time needs explicit UTC offset")
            captured=captured.tz_convert("UTC")
            if captured>pd.Timestamp.now(tz="UTC")+pd.Timedelta(minutes=10):
                raise ValueError("Source quote timestamp lies in the future")
            if expiry.tzinfo is None:
                raise ValueError("Option expiry needs an exact timezone-aware timestamp")
            expiry=expiry.tz_convert("UTC")
            if expiry<=captured:
                raise ValueError("Option expiry must follow captured quote date")
            if (expiry-captured).days>3650:
                raise ValueError("Option expiry is implausibly far away")
        except (TypeError,OverflowError,ValueError) as err:
            raise ValueError(f"Row {i+1}: invalid captured_at/expiry: {err}") from err
        option=values["option_type"].lower()
        if option not in {"call","put"}:
            raise ValueError(f"Row {i+1}: option_type must be call or put")
        try:
            spot,strike,bid,ask=[float(values[k]) for k in
                                 ("underlying_spot","strike","bid","ask")]
        except (TypeError,ValueError):
            raise ValueError(f"Row {i+1}: quote/strike/underlying values must be numbers")
        if not all(math.isfinite(x) for x in (spot,strike,bid,ask)):
            raise ValueError(f"Row {i+1}: non-finite option quotes")
        if spot<=0 or strike<=0 or bid<=0 or ask<=0 or bid>ask:
            raise ValueError(f"Row {i+1}: invalid positive bid/ask/spot/strike or crossed quote")
        # Disallow obviously contradictory quotes; full model bounds depend
        # on rate and dividend conventions, checked during IV inference.
        if (bid+ask)/2>=100*max(spot,strike):
            raise ValueError(f"Row {i+1}: implausible option premium")
        rows.append({
            "captured_at":captured.isoformat(), "provider":provider,
            "underlying":values["underlying"],"underlying_spot":spot,
            "expiry_at":expiry.isoformat(),"strike":strike,
            "option_type":option,"bid":bid,"ask":ask,
            "mid_price":.5*(bid+ask),
        })
    return rows


def import_quotes(dataset_id: str, raw: bytes, *,
                  source_type: str = "user_uploaded_original_option_quote_csv",
                  provider_raw_json: bytes | None = None,
                  provider_metadata: dict | None = None) -> dict:
    service.dataset_path(dataset_id)
    rows=_validate(raw)
    root=_root()
    root.mkdir(parents=True,exist_ok=True)
    if source_type not in {"user_uploaded_original_option_quote_csv",
                           "dhan_readonly_optionchain_api_v2"}:
        raise ValueError("Unsupported quote source type")
    if provider_raw_json is not None and (
            not isinstance(provider_raw_json,bytes) or
            len(provider_raw_json)>1_500_000):
        raise ValueError("Original vendor response exceeds protected source limit")
    quote_id="oq_"+uuid.uuid4().hex[:20]
    csv,manifest=_entry_path(quote_id)
    vendor_path=_root()/(quote_id+".vendor.json")
    metadata={
        "id":quote_id,"dataset_id":dataset_id,
        "source_sha256":_hash(raw),
        "contracts":rows,
        "captured_at":datetime.now(timezone.utc).isoformat(),
        "source_type":source_type,
        "original_vendor_response_sha256":_hash(provider_raw_json) if provider_raw_json else None,
        "provider_metadata":provider_metadata or {},
        "independently_source_certified":False,
        "model_inputs_are_market_quotes":True,
        "risk_free_yield_source":"model_assumptions_until_user_supplies_verified_rates",
        "warning":"Bid and ask originate from the user's provider export. "
                  "Provider identity, option style, liquidity, risk-free curve, "
                  "dividend timing and quote freshness are not independently audited.",
    }
    if len(json.dumps(metadata))>190_000:
        raise ValueError("Quote manifest exceeds safe bounded size")
    try:
        with csv.open("xb") as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        if provider_raw_json is not None:
            with vendor_path.open("xb") as out:
                out.write(provider_raw_json);out.flush();os.fsync(out.fileno())
        with manifest.open("x",encoding="utf-8") as out:
            json.dump(metadata,out,indent=2,allow_nan=False)
            out.flush();os.fsync(out.fileno())
    except Exception:
        csv.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        vendor_path.unlink(missing_ok=True)
        raise
    return {"id":quote_id,"dataset_id":dataset_id,"contracts":rows,
            "source_sha256":metadata["source_sha256"],
            "warning":metadata["warning"],"independently_source_certified":False}


def get(quote_id: str, dataset_id: str) -> dict:
    file,meta=_entry_path(quote_id)
    if any(p.is_symlink() for p in (file,meta)):
        raise ValueError("Unsafe quoted source path")
    if not file.is_file() or not meta.is_file():
        raise ValueError("Option quote source not found; upload original market quotes")
    if file.stat().st_size>MAX_BYTES or meta.stat().st_size>200_000:
        raise ValueError("Option quote evidence exceeds the safety limit")
    content=json.loads(meta.read_text(encoding="utf-8"))
    if content.get("id")!=quote_id or content.get("dataset_id")!=dataset_id:
        raise ValueError("Option quotes belong to another dataset")
    if _hash(file.read_bytes())!=content.get("source_sha256"):
        raise ValueError("Original option quote file changed after import: source integrity failure")
    vendor_hash=content.get("original_vendor_response_sha256")
    if vendor_hash:
        raw_path=_root()/(quote_id+".vendor.json")
        if raw_path.is_symlink() or not raw_path.is_file() or raw_path.stat().st_size>1_500_000:
            raise ValueError("Dhan original option-chain source missing or unsafe")
        if _hash(raw_path.read_bytes())!=vendor_hash:
            raise ValueError("Original Dhan option-chain provider response checksum mismatch")
    parsed=_validate(file.read_bytes())
    if parsed!=content.get("contracts"):
        raise ValueError("Option quote manifest no longer matches original source records")
    return content


def list_for(dataset_id: str) -> list[dict]:
    service.dataset_path(dataset_id)
    root=_root()
    if not root.is_dir():
        return []
    snapshots=[]
    for file in sorted(root.glob("oq_*.json"),key=lambda p:p.stat().st_mtime,reverse=True)[:MAX_LIST]:
        if file.is_symlink():
            continue
        try:
            quote_id=file.stem
            entry=get(quote_id,dataset_id)
        except (ValueError,FileNotFoundError,KeyError,OSError,json.JSONDecodeError):
            continue
        snapshots.append({
            "id":quote_id,"dataset_id":dataset_id,
            "captured_at":entry["captured_at"],
            "contracts":[{**q,"row_index":i,
                          "quote_age_days":round((pd.Timestamp.now(tz="UTC")-
                            pd.Timestamp(q["captured_at"])).total_seconds()/86400,2)}
                         for i,q in enumerate(entry["contracts"])],
            "source_sha256":entry["source_sha256"],
            "warning":entry["warning"],
        })
    return snapshots


def read_contract(quote_id: str, dataset_id: str, row_index: int) -> tuple[dict,dict]:
    snapshot=get(quote_id,dataset_id)
    if not isinstance(row_index,int) or isinstance(row_index,bool) or not 0<=row_index<len(snapshot["contracts"]):
        raise ValueError("Select an existing original option contract row")
    quote=snapshot["contracts"][row_index]
    return quote,snapshot
