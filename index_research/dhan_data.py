"""Read-only DhanHQ v2 historical-data adapter.

No order endpoints, no credential persistence, no synthetic adjustments.
Client accepts a mock transport for offline unit tests. Access token is
read from environment at runtime and never included in stored artifacts.

Official API:
https://dhanhq.co/docs/v2/historical-data/
https://dhanhq.co/docs/v2/authentication/
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Load only the repository-local .env, never write secrets to source files.
# An explicitly exported environment variable takes precedence.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)

BASE = "https://api.dhan.co/v2"
MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
ALLOWED_INTERVALS = {1, 5, 15, 25, 60}


@dataclass(frozen=True)
class Instrument:
    label: str
    security_id: str
    exchange_segment: str = "NSE_EQ"
    instrument: str = "EQUITY"
    expiry_code: int = 0

    def __post_init__(self):
        if not self.label or not self.security_id or not self.exchange_segment or not self.instrument:
            raise ValueError("instrument label, security ID, segment and type are required")
        if any(c in self.label for c in "/\\\\") or self.label.startswith("."):
            raise ValueError("unsafe instrument label")
        if not str(self.security_id).isdigit():
            raise ValueError("security_id must be a numeric Dhan identifier")
        if str(self.security_id) in {"00000","00001"}:
            raise ValueError("replace illustrative Security IDs with reviewed Dhan master values")


def read_instruments(path: str | Path) -> list[Instrument]:
    """Local explicit mapping, not an inferred current-symbol historical mapping."""
    rows = pd.read_csv(path, dtype={"security_id": str})
    required = {"label", "security_id", "exchange_segment", "instrument"}
    if not required.issubset(rows.columns):
        raise ValueError(f"instruments CSV missing: {sorted(required-set(rows.columns))}")
    if rows.empty or rows["label"].duplicated().any():
        raise ValueError("instruments must be nonempty and have unique labels")
    out = []
    for _, row in rows.iterrows():
        value = row.get("expiry_code", 0)
        expiry = int(value) if pd.notna(value) else 0
        out.append(Instrument(label=str(row["label"]), security_id=str(row["security_id"]),
                              exchange_segment=str(row["exchange_segment"]),
                              instrument=str(row["instrument"]), expiry_code=expiry))
    return out


def _parse_date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def date_windows(first: str | date, end_exclusive: str | date, max_days: int):
    """Nonoverlapping [start,end) chunks: no more than max_days calendar days."""
    start = _parse_date(first)
    end = _parse_date(end_exclusive)
    if max_days < 1 or end <= start:
        raise ValueError("end date must follow start date")
    while start < end:
        stop = min(end, start + timedelta(days=max_days))
        yield start, stop
        start = stop


def _post_json(path: str, payload: dict, token: str, *, attempts: int=4,
               opener: Callable = urlopen, sleeper: Callable=time.sleep) -> dict:
    if not token:
        raise ValueError("DHAN_ACCESS_TOKEN environment variable is required")
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "access-token": token}
    request = Request(BASE+path, data=data, headers=headers, method="POST")
    for attempt in range(attempts):
        try:
            with opener(request, timeout=30) as response:
                body = response.read()
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError("Unexpected Dhan API response")
            if result.get("status") == "failure" or result.get("errorCode"):
                # Vendor messages might contain account context; do not print body.
                raise RuntimeError("Dhan returned an error: verify token, instrument, subscription and dates")
            return result
        except HTTPError as exc:
            if exc.code in (429,500,502,503,504) and attempt < attempts-1:
                sleeper(min(30,2**attempt+random.random()))
                continue
            raise RuntimeError(f"Dhan HTTP {exc.code} (response body hidden)") from None
        except (URLError, TimeoutError):
            if attempt < attempts-1:
                sleeper(min(30,2**attempt+random.random()))
                continue
            raise RuntimeError("Dhan network request failed") from None
    raise RuntimeError("Dhan retry limit reached")


def candles_to_frame(response: dict, instrument: Instrument,
                     timezone: str="Asia/Kolkata") -> pd.DataFrame:
    """Dhan v2 column arrays -> validated, timezone-aware OHLCV candles."""
    data = response.get("data", response)
    if not isinstance(data, dict):
        raise ValueError("Dhan response data must be a dict")
    required = ("timestamp","open","high","low","close","volume")
    if any(k not in data for k in required):
        raise ValueError("Dhan response missing OHLCV/timestamp fields")
    count=len(data["timestamp"])
    if any(len(data[k]) != count for k in required):
        raise ValueError("Dhan response columns have inconsistent lengths")
    columns = {k:data[k] for k in required}
    if "open_interest" in data and len(data["open_interest"]) == count:
        columns["open_interest"]=data["open_interest"]
    frame=pd.DataFrame(columns)
    if frame.empty:
        return pd.DataFrame(columns=[
            "datetime","label","security_id","exchange_segment","instrument",
            "open","high","low","close","volume"
        ])
    stamp=pd.to_datetime(frame["timestamp"],unit="s",utc=True,errors="raise")
    frame["datetime"]=stamp.dt.tz_convert(timezone)
    if frame["datetime"].isna().any() or frame["datetime"].duplicated().any():
        raise ValueError("Dhan supplied missing or duplicate timestamps")
    for col in ("open","high","low","close","volume"):
        frame[col]=pd.to_numeric(frame[col],errors="raise")
    if not np.isfinite(frame[["open","high","low","close","volume"]].to_numpy()).all():
        raise ValueError("nonfinite OHLCV")
    if (frame[["open","high","low","close"]]<=0).any().any() or (frame["volume"]<0).any():
        raise ValueError("nonpositive OHLC or negative volume")
    if (frame["high"]+1e-8<frame[["open","low","close"]].max(axis=1)).any():
        raise ValueError("impossible candle high")
    if (frame["low"]-1e-8>frame[["open","high","close"]].min(axis=1)).any():
        raise ValueError("impossible candle low")
    frame["label"]=instrument.label
    frame["security_id"]=instrument.security_id
    frame["exchange_segment"]=instrument.exchange_segment
    frame["instrument"]=instrument.instrument
    return frame.drop(columns="timestamp").sort_values("datetime").reset_index(drop=True)


def download_candles(instrument: Instrument, from_date: str, to_date: str,
                     *, interval: int | None = None,
                     token: str | None = None,
                     post: Callable | None = None,
                     pause_seconds: float=.25) -> pd.DataFrame:
    """Fetch daily or intraday OHLCV in chunks.

    from_date inclusive, to_date exclusive; 90 day max intraday per docs.
    Uses 365 day daily windows conservatively (not a published daily limit).
    post injection supports offline no-network tests.
    """
    if interval is not None and interval not in ALLOWED_INTERVALS:
        raise ValueError(f"unsupported interval, choose {sorted(ALLOWED_INTERVALS)}")
    if pause_seconds < 0:
        raise ValueError("pause must be nonnegative")
    if token is None:
        token=os.environ.get("DHAN_ACCESS_TOKEN","")
    if not token and post is None:
        raise ValueError("DHAN_ACCESS_TOKEN missing; set it in your shell")
    parts=[]
    for first,last in date_windows(from_date,to_date,90 if interval is not None else 365):
        payload={"securityId":instrument.security_id,
                 "exchangeSegment":instrument.exchange_segment,
                 "instrument":instrument.instrument,
                 "oi":False}
        if interval is None:
            payload.update({"expiryCode":instrument.expiry_code,
                            "fromDate":first.isoformat(),
                            "toDate":last.isoformat()})
            endpoint="/charts/historical"
        else:
            payload.update({"interval":str(interval),
                            "fromDate":first.strftime("%Y-%m-%d")+" 00:00:00",
                            "toDate":last.strftime("%Y-%m-%d")+" 00:00:00"})
            endpoint="/charts/intraday"
        response=post(endpoint,payload,token) if post else _post_json(endpoint,payload,token)
        df=candles_to_frame(response,instrument)
        if not df.empty:
            local_dates=df.datetime.dt.date
            df=df.loc[(local_dates>=first)&(local_dates<last)].copy()
            parts.append(df)
        if pause_seconds and post is None:
            time.sleep(pause_seconds)
    if not parts:
        raise ValueError(f"No candles returned for {instrument.label}; verify symbol and date range")
    result=pd.concat(parts,ignore_index=True).sort_values("datetime")
    if result.datetime.duplicated().any():
        raise ValueError("Duplicate candle timestamps across Dhan chunks")
    return result.reset_index(drop=True)


def save_download(frame: pd.DataFrame, instrument: Instrument, folder: str | Path,
                  from_date: str, to_date: str, interval: int | None) -> tuple[Path,Path]:
    root=Path(folder)
    root.mkdir(parents=True,exist_ok=True)
    name=instrument.label + ("_daily" if interval is None else f"_intraday_{interval}m")
    csv_path=root/(name+".csv")
    if csv_path.exists():
        raise FileExistsError(f"{csv_path} exists; choose new output folder to preserve evidence")
    frame.to_csv(csv_path,index=False)
    digest=hashlib.sha256(csv_path.read_bytes()).hexdigest()
    metadata={
        "source":"DhanHQ REST API v2",
        "retrieved_utc":datetime.now(timezone.utc).isoformat(),
        "instrument":asdict(instrument),
        "from_inclusive":from_date,"to_exclusive":to_date,
        "interval_minutes":interval,"row_count":len(frame),
        "sha256":digest,
        "price_adjustment":"Dhan reports DAILY candles adjusted for splits and bonus shares; dividend/other action adjustment NOT established",
        "license":"User must confirm own Dhan data usage and redistribution rights",
        "warning":"Dhan daily split/bonus adjustment does not prove dividend total returns, PIT universe data, or complete corporate-action evidence."
    }
    manifest=root/(name+".manifest.json")
    manifest.write_text(json.dumps(metadata,indent=2))
    return csv_path,manifest


def build_monthly_close(raw_folder: str | Path, instruments: list[Instrument],
                        target_folder: str | Path) -> Path:
    """Daily OHLCV -> month-end *observed trading date* close matrix.

    Does not synthesize a benchmark or membership and does not replace missing
    delisted instruments with survivor prices. Excludes months with no candles
    for a security; labels on a common calendar month-end for matrix alignment.
    """
    series=[]
    for inst in instruments:
        file=Path(raw_folder)/(inst.label+"_daily.csv")
        if not file.exists():
            raise FileNotFoundError(file)
        df=pd.read_csv(file)
        required={"datetime","close","security_id","label"}
        if not required.issubset(df.columns):
            raise ValueError(f"{file} missing candle metadata")
        if not (df.security_id.astype(str)==inst.security_id).all() or not (df.label==inst.label).all():
            raise ValueError("Candle instrument metadata mismatch")
        dates=pd.to_datetime(df.datetime,utc=True,errors="raise").dt.tz_convert("Asia/Kolkata")
        values=pd.to_numeric(df.close,errors="raise")
        if (values<=0).any() or values.isna().any():
            raise ValueError("Candle prices must be positive")
        local=pd.Series(values.to_numpy(),index=dates.dt.tz_localize(None)).sort_index()
        if local.index.has_duplicates:
            raise ValueError("Duplicate daily timestamps")
        monthly=local.groupby(local.index.to_period("M")).last()
        monthly.index=monthly.index.to_timestamp("M")
        monthly.name=inst.label
        series.append(monthly)
    prices=pd.concat(series,axis=1).sort_index()
    if prices.empty:
        raise ValueError("no monthly observations")
    out=Path(target_folder)
    out.mkdir(parents=True,exist_ok=True)
    target=out/"prices.csv"
    if target.exists():
        raise FileExistsError(f"{target} exists; refusing silent overwrite")
    prices.to_csv(target,index_label="date")
    (out/"DHAN_UNADJUSTED_DATA_WARNING.txt").write_text(
        "Dhan daily CLOSE resampled to calendar month-end label. Dhan reports "
        "split/bonus-adjusted DAILY closes; these are NOT established dividend-reinvested "
        "total-return data. No index membership, corporate actions, "
        "benchmark returns or fundamental vintages have been fabricated. "
        "Supply and audit membership.csv, benchmark.csv, sectors.csv and "
        "fundamentals.csv as appropriate before research use.\n")
    return target
