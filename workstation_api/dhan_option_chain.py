"""Authorized read-only DhanHQ option-chain capture for QuantLab model research.

Only GET /profile and POST /optionchain/expirylist /optionchain. No trading
endpoints. Uses ignored local .env credentials; never returns/logs secrets,
client identities, raw vendor errors or proprietary quote JSON to browser.
Dhan expiry API provides a date, NOT an exact settlement timestamp, so
15:30 Asia/Kolkata is explicitly labeled as an assumed regular-session mark.
"""
from __future__ import annotations

from datetime import datetime, date, timezone
from io import StringIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import json
import math
import os
import time
import csv

from . import option_quotes, service

CHAIN_ENDPOINT="https://api.dhan.co/v2/optionchain"
EXPIRY_ENDPOINT="https://api.dhan.co/v2/optionchain/expirylist"
PROFILE_ENDPOINT="https://api.dhan.co/v2/profile"
UNDERLYING={
    "NIFTY50": {"scrip":13,"segment":"IDX_I","symbol":"NIFTY50"},
    "BANKNIFTY": {"scrip":25,"segment":"IDX_I","symbol":"BANKNIFTY"},
}


def _json_http(url: str, *, token: str, client_id: str = "",
               body: dict | None = None) -> tuple[dict,bytes]:
    if url not in {CHAIN_ENDPOINT,EXPIRY_ENDPOINT,PROFILE_ENDPOINT}:
        raise ValueError("Dhan endpoint is not explicitly permitted")
    headers={"access-token":token,"Accept":"application/json"}
    if client_id:
        headers["client-id"]=client_id
    payload=None
    if body is not None:
        headers["Content-Type"]="application/json"
        payload=json.dumps(body,separators=(",",":")).encode()
    request=Request(url,data=payload,headers=headers,
                    method="POST" if body is not None else "GET")
    try:
        with urlopen(request,timeout=20) as response:
            data=response.read(1_500_001)
    except HTTPError as exc:
        # Do not leak response bodies or account-specific vendor diagnostics.
        if exc.code in {401,403}:
            raise ValueError("Dhan authentication/data-plan rejected the read-only option-chain request "
                             f"(HTTP {exc.code}). Refresh local token or check API entitlements.") from None
        if exc.code==429:
            raise ValueError("Dhan option-chain rate limit (HTTP 429); retry after 3+ seconds") from None
        raise ValueError(f"Dhan option-chain HTTP {exc.code}; provider body intentionally hidden") from None
    except (URLError,TimeoutError,OSError):
        raise ValueError("Dhan read-only option-chain connection unavailable; verify network access") from None
    if len(data)>1_500_000 or not data:
        raise ValueError("Dhan returned empty or oversized option-chain data")
    try:
        obj=json.loads(data)
    except (ValueError,UnicodeError):
        raise ValueError("Dhan option-chain response was not valid JSON") from None
    if not isinstance(obj,dict) or obj.get("status")=="failure":
        raise ValueError("Dhan returned an unsuccessful option-chain result (body hidden)")
    return obj,data


def _client_id(token: str) -> str:
    configured=os.getenv("DHAN_CLIENT_ID","").strip()
    if configured:
        if not configured.isdigit() or len(configured)>30:
            raise ValueError("DHAN_CLIENT_ID must be your numeric client ID in ignored .env")
        return configured
    profile,_=_json_http(PROFILE_ENDPOINT,token=token)
    ident=str(profile.get("dhanClientId") or profile.get("clientId") or "").strip()
    if not ident.isdigit():
        raise ValueError("Could not read client-id from Dhan profile. Set DHAN_CLIENT_ID "
                         "in the repository's ignored .env and restart QuantLab.")
    return ident


def _pick_expiry(expiries: object, captured: datetime) -> str:
    if not isinstance(expiries,list):
        raise ValueError("Dhan expiry list was not returned")
    candidates=[]
    india=ZoneInfo("Asia/Kolkata")
    for value in expiries[:200]:
        if not isinstance(value,str) or len(value)!=10:
            continue
        try:
            parsed=date.fromisoformat(value)
        except ValueError:
            continue
        close=datetime(parsed.year,parsed.month,parsed.day,15,30,tzinfo=india)
        if close>captured:
            candidates.append((close,value))
    if not candidates:
        raise ValueError("No non-expired Dhan option expiry available for this underlying")
    candidates.sort(key=lambda v:v[0])
    return candidates[0][1]


def _normalize_chain(response: dict, *, symbol: str, expiry: str,
                     captured: datetime) -> bytes:
    data=response.get("data")
    if not isinstance(data,dict):
        raise ValueError("Dhan option chain missing the index's source data")
    try:
        spot=float(data["last_price"])
    except (ValueError,TypeError,KeyError):
        raise ValueError("Dhan option chain returned no valid index spot") from None
    if not math.isfinite(spot) or spot<=0:
        raise ValueError("Dhan option chain index spot must be a positive finite value")
    book=data.get("oc")
    if not isinstance(book,dict) or not book or len(book)>3000:
        raise ValueError("Dhan option chain has no bounded strike dictionary")
    strikes=[]
    for price,body in book.items():
        try:
            strike=float(price)
        except (ValueError,TypeError):
            continue
        if math.isfinite(strike) and strike>0 and isinstance(body,dict):
            strikes.append((abs(strike-spot),strike,body))
    strikes.sort(key=lambda item:(item[0],item[1]))
    expiry_at=expiry+"T15:30:00+05:30"
    fields=["captured_at","provider","underlying","underlying_spot",
            "expiry_at","strike","option_type","bid","ask"]
    out=StringIO()
    writer=csv.DictWriter(out,fieldnames=fields,lineterminator="\n")
    writer.writeheader()
    selected=0
    for _,strike,contracts in strikes[:100]:
        for side,kind in (("ce","call"),("pe","put")):
            quote=contracts.get(side)
            if not isinstance(quote,dict):
                continue
            try:
                bid=float(quote.get("top_bid_price"))
                ask=float(quote.get("top_ask_price"))
            except (ValueError,TypeError):
                continue
            if not all(map(math.isfinite,(bid,ask))) or bid<=0 or ask<=0 or bid>ask:
                continue
            writer.writerow({"captured_at":captured.isoformat(),
                             "provider":"DhanHQ_OptionChain",
                             "underlying":symbol,"underlying_spot":spot,
                             "expiry_at":expiry_at,"strike":strike,
                             "option_type":kind,"bid":bid,"ask":ask})
            selected+=1
    if selected==0:
        raise ValueError("No quoted strikes had positive, uncrossed Dhan best bid/ask")
    return out.getvalue().encode("utf-8")


def capture(dataset_id: str, underlying: str = "NIFTY50",
            *, sleep=time.sleep) -> dict:
    """One authorized live chain capture. Runs on local job worker, no orders."""
    service.dataset_path(dataset_id)
    if underlying not in UNDERLYING:
        raise ValueError("Choose a supported indexed underlying, NIFTY50 or BANKNIFTY")
    token=os.getenv("DHAN_ACCESS_TOKEN","").strip()
    if not token:
        raise ValueError("Configure DHAN_ACCESS_TOKEN in ignored local .env; "
                         "the browser never receives it")
    ident=_client_id(token)
    index=UNDERLYING[underlying]
    args={"UnderlyingScrip":index["scrip"],"UnderlyingSeg":index["segment"]}
    expiry_json,expiry_raw=_json_http(EXPIRY_ENDPOINT,token=token,client_id=ident,body=args)
    captured=datetime.now(timezone.utc)
    expiry=_pick_expiry(expiry_json.get("data"),captured)
    # Dhan documents a limit of one unique option-chain request per 3 sec;
    # avoid bursting two endpoint calls with the same credentials.
    sleep(3.1)
    chain_json,original_raw=_json_http(CHAIN_ENDPOINT,token=token,client_id=ident,
                                       body={**args,"Expiry":expiry})
    captured=datetime.now(timezone.utc)
    normalized=_normalize_chain(chain_json,symbol=index["symbol"],
                                expiry=expiry,captured=captured)
    result=option_quotes.import_quotes(
        dataset_id,normalized,source_type="dhan_readonly_optionchain_api_v2",
        provider_raw_json=original_raw,
        provider_metadata={
            "underlying":underlying,"underlying_scrip":index["scrip"],
            "underlying_segment":index["segment"],"expiry_date":expiry,
            "captured_at_local_utc":captured.isoformat(),
            "original_expiry_list_sha256":__import__("hashlib").sha256(expiry_raw).hexdigest(),
            "source_expiry_time_is_exact":False,
            "expiry_close_time_assumption":"15:30 Asia/Kolkata regular NSE session",
            "provider_timestamp_is_exchange_event_timestamp":False,
            "warning":"Dhan chain supplies expiry DATE; 15:30 IST regular close is an "
                      "explicit timing assumption, not an exchange-sourced expiry timestamp.",
        })
    return {"id":result["id"],"dataset_id":dataset_id,
            "underlying":underlying,"expiry":expiry,
            "contracts":len(result["contracts"]),
            "source":"read_only_Dhan_v2_option_chain",
            "market_data_not_orders":True,
            "independently_source_certified":False,
            "warning":"Imported a CURRENT Dhan market snapshot. Quotes may change immediately. "
                      "Expiry time assumed 15:30 IST regular session; rates/yield remain model assumptions."}
