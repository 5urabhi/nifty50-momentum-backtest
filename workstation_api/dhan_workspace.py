"""Bulk read-only DhanHQ historical data workspace.

The present-day Dhan instrument master is an instrument *catalog*, not a
point-in-time Nifty 50/500 constituent history. No live trades or credentials
are persisted. Daily/intraday candles are cached by exchange + Dhan Security ID.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import csv
import logging
from collections import deque
import os
from pathlib import Path
import re
import threading
import uuid

import numpy as np
import pandas as pd

from index_research.dhan_data import Instrument, date_windows, download_candles
from . import index_spot, pit_index, service

KEY = re.compile(r"^(NSE_EQ|BSE_EQ):([0-9]{1,12})$")
BATCH_ID = re.compile(r"^batch_[a-f0-9]{16}$")
SAFE_SYMBOL = re.compile(r"^[A-Za-z0-9&_.-]{1,80}$")
ACTIVE_BATCHES: set[str] = set()
ACTIVE_LOCK = threading.Lock()
MAX_INSTRUMENTS = 6000
LOG = logging.getLogger("quantlab.dhan.batch")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _master() -> Path:
    return service.DATA / "dhan" / "instrument_master.csv"


def _batches() -> Path:
    return service.DATA / "dhan" / "batches"


def _history_file(row: dict, interval: int | None) -> Path:
    period = "daily" if interval is None else f"{interval}m"
    segment = row["exchange_segment"]
    identifier = row["security_id"]
    if not KEY.fullmatch(f"{segment}:{identifier}"):
        raise ValueError("Invalid canonical instrument identity")
    return service.DATA / "dhan" / "history" / segment / identifier / (period + ".csv")


def _column(columns: dict[str, str], *aliases: str) -> str | None:
    return next((columns[a] for a in aliases if a in columns), None)


@lru_cache(maxsize=4)
def _catalog_cached(filename: str, modified_ns: int, size: int) -> tuple[dict, ...]:
    data = pd.read_csv(filename, dtype=str, keep_default_na=False, low_memory=False)
    columns = {str(column).strip().upper(): column for column in data.columns}
    exchange = _column(columns, "EXCH_ID", "SEM_EXM_EXCH_ID")
    segment = _column(columns, "SEGMENT", "SEM_SEGMENT")
    security_id = _column(columns, "SECURITY_ID", "SEM_SMST_SECURITY_ID")
    instrument = _column(columns, "INSTRUMENT", "SEM_INSTRUMENT_NAME")
    trading_symbol_column = _column(columns, "SEM_TRADING_SYMBOL", "TRADING_SYMBOL", "SYMBOL")
    symbol = trading_symbol_column or _column(
        columns, "DISPLAY_NAME", "SEM_CUSTOM_SYMBOL", "SYMBOL_NAME", "SM_SYMBOL_NAME")
    display = _column(columns, "SYMBOL_NAME", "SM_SYMBOL_NAME", "DISPLAY_NAME", "SEM_CUSTOM_SYMBOL")
    series = _column(columns, "SERIES", "SEM_SERIES")
    isin = _column(columns, "ISIN")
    if not all([exchange, segment, security_id, instrument]) or not (symbol or display):
        raise ValueError("Dhan instrument master format not recognized; refresh it using the official endpoint")
    seen: set[str] = set()
    items: list[dict] = []
    for _, row in data.iterrows():
        exch = str(row[exchange]).strip().upper()
        seg = str(row[segment]).strip().upper()
        kind = str(row[instrument]).strip().upper()
        ident = str(row[security_id]).strip()
        if exch not in ("NSE", "BSE") or seg not in ("E", "EQ", "NSE_EQ", "BSE_EQ"):
            continue
        if kind != "EQUITY" or not ident.isdigit() or not 1 <= len(ident) <= 12:
            continue
        exchange_segment = exch + "_EQ"
        key = exchange_segment + ":" + ident
        if key in seen:
            continue
        name = str(row[symbol]).strip() if symbol else ""
        shown = str(row[display]).strip() if display else ""
        ticker = name or shown
        if not ticker:
            continue
        trade_series = str(row[series]).strip().upper() if series else ""
        seen.add(key)
        items.append({
            "id": key, "symbol": ticker[:80], "display_name": (shown or ticker)[:160],
            "security_id": ident, "exchange_segment": exchange_segment,
            "instrument": "EQUITY", "series": trade_series or "UNSPECIFIED",
            "isin": str(row[isin]).strip()[:20] if isin else "",
            "regular_eq": exch == "BSE" or trade_series in ("", "EQ"),
            # A detailed Dhan master may have display/company names but
            # no canonical exchange trading ticker. Never use such fallback
            # labels for historical constituent matching.
            "trading_symbol_verified": bool(trading_symbol_column),
            "series_supplied": bool(series),
        })
    return tuple(sorted(items, key=lambda row: (row["exchange_segment"], row["symbol"], row["security_id"])))


def catalog() -> list[dict]:
    path = _master()
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError("Refresh the official Dhan instrument master first")
    stat = path.stat()
    return list(_catalog_cached(str(path), stat.st_mtime_ns, stat.st_size))


def catalog_health() -> dict:
    """Report source-schema faults independently of historical delistings.

    This never guesses missing security IDs. Older detailed-master files are
    detected explicitly, rather than being mistaken for 51 delisted stocks.
    """
    path = _master()
    if not path.is_file() or path.is_symlink():
        return {"ready": False, "code": "master_missing", "nse_equities": 0,
                "verified_nse_tickers": 0, "message": "Download the compact Dhan instrument master."}
    try:
        header = pd.read_csv(path, nrows=0)
        columns = {str(k).strip().upper() for k in header.columns}
        has_trading = "SEM_TRADING_SYMBOL" in columns
        has_key = {"SEM_EXM_EXCH_ID", "SEM_SEGMENT", "SEM_SMST_SECURITY_ID",
                   "SEM_INSTRUMENT_NAME"}.issubset(columns)
        if not has_trading or not has_key:
            return {"ready": False, "code": "outdated_detailed_master",
                    "nse_equities": 0, "verified_nse_tickers": 0,
                    "has_trading_symbol": has_trading,
                    "message": "The local Dhan master does not contain the canonical "
                               "compact exchange trading-symbol schema. Refresh the catalog."}
        rows = catalog()
        equities = [r for r in rows if r["exchange_segment"] == "NSE_EQ"
                    and r["regular_eq"]]
        verified = [r for r in equities if r.get("trading_symbol_verified")]
        expected = {"RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC"}
        seen = {str(r["symbol"]).strip().upper() for r in verified}
        matched = sorted(expected & seen)
        ready = len(verified) >= 100 and len(matched) >= 3
        return {
            "ready": ready,
            "code": "ready" if ready else "master_unusable",
            "nse_equities": len(equities),
            "verified_nse_tickers": len(verified),
            "sample_major_symbols_found": matched,
            "message": ("Compact catalog contains verified NSE trading symbols."
                        if ready else "Compact catalog did not resolve expected actively "
                        "listed NSE companies; refresh it before creating historical batches."),
        }
    except (ValueError, OSError, KeyError) as exc:
        return {"ready": False, "code": "catalog_parse_error", "nse_equities": 0,
                "verified_nse_tickers": 0,
                "message": "Dhan instrument catalog failed schema validation: " +
                           str(exc)[:150]}


def search_catalog(query: str = "", exchange: str = "NSE", page: int = 1,
                   per_page: int = 60, regular_only: bool = True) -> dict:
    if exchange not in {"NSE", "BSE"} or not 1 <= page <= 10000 or not 1 <= per_page <= 100:
        raise ValueError("Invalid instrument search parameters")
    if len(query) > 80:
        raise ValueError("Search query too long")
    q = query.strip().casefold()
    items = [i for i in catalog() if i["exchange_segment"] == exchange + "_EQ"
             and (not regular_only or i["regular_eq"])
             and (not q or q in i["symbol"].casefold() or q in i["display_name"].casefold()
                  or q in i["security_id"] or q in i["isin"].casefold())]
    start = (page - 1) * per_page
    return {"items": items[start:start + per_page], "total": len(items),
            "page": page, "per_page": per_page, "has_more": start + per_page < len(items),
            "exchange": exchange, "regular_only": regular_only,
            "disclaimer": "Current Dhan cash-equity instrument catalog, NOT historical index membership."}


def _choose(selection: str, ids: list[str], tickers: list[str]) -> list[dict]:
    full = catalog()
    by_id = {item["id"]: item for item in full}
    if selection == "all_nse":
        chosen = [row for row in full if row["exchange_segment"] == "NSE_EQ" and row["regular_eq"]]
    elif selection == "all_bse":
        chosen = [row for row in full if row["exchange_segment"] == "BSE_EQ" and row["regular_eq"]]
    elif selection == "selected":
        if len(ids) != len(set(ids)) or not ids:
            raise ValueError("Select at least one unique instrument")
        invalid = [key for key in ids if key not in by_id]
        if invalid:
            raise ValueError(f"Instrument IDs are not in the current Dhan master: {invalid[:5]}")
        chosen = [by_id[key] for key in ids]
    elif selection == "watchlist":
        if not tickers:
            raise ValueError("Paste or upload at least one ticker")
        if len(tickers) > MAX_INSTRUMENTS:
            raise ValueError("Watchlist exceeds 6000 tickers")
        # Watchlists only resolve exact current NSE EQ-series names. Never map
        # ambiguous/expired symbols heuristically to a different security ID.
        by_symbol: dict[str, list[dict]] = {}
        for row in full:
            if row["exchange_segment"] == "NSE_EQ" and row["regular_eq"]:
                by_symbol.setdefault(row["symbol"].casefold(), []).append(row)
        chosen = []
        unknown, ambiguous = [], []
        for symbol in dict.fromkeys(x.strip().casefold() for x in tickers if x.strip()):
            matches = by_symbol.get(symbol, [])
            if not matches:
                unknown.append(symbol)
            elif len(matches) != 1:
                ambiguous.append(symbol)
            else:
                chosen.append(matches[0])
        if unknown or ambiguous:
            raise ValueError("Fix watchlist symbols before downloading. Unknown: "
                             + ", ".join(unknown[:12]) + "; ambiguous: "
                             + ", ".join(ambiguous[:12]))
    else:
        raise ValueError("Unknown selection mode")
    result = list({item["id"]: item for item in chosen}.values())
    if not result or len(result) > MAX_INSTRUMENTS:
        raise ValueError("Selection must contain 1–6000 distinct instruments")
    return result


def _atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex[:8] + ".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _batch_path(batch_id: str) -> Path:
    if not BATCH_ID.fullmatch(batch_id):
        raise ValueError("Invalid batch ID")
    folder = _batches() / batch_id
    if folder.is_symlink() or not folder.is_dir():
        raise FileNotFoundError("Unknown download batch")
    return folder / "manifest.json"


def _load_batch(batch_id: str) -> dict:
    return json.loads(_batch_path(batch_id).read_text())


def _save_batch(data: dict):
    data["updated_utc"] = _now()
    _atomic_json(_batch_path(data["id"]), data)


def _summarize(data: dict) -> dict:
    counts = {status: sum(1 for i in data["items"] if i["status"] == status)
              for status in ("pending", "downloading", "complete", "cached", "no_data", "failed")}
    completed = counts["complete"] + counts["cached"] + counts["no_data"] + counts["failed"]
    status = data["status"]
    with ACTIVE_LOCK:
        active = data["id"] in ACTIVE_BATCHES
    if status in ("running", "queued") and not active:
        status = "interrupted"
    return {
        "id": data["id"], "status": status, "created_utc": data["created_utc"],
        "updated_utc": data.get("updated_utc"), "selection": data["selection"],
        "exchange": data.get("exchange", "NSE"), "interval": data["interval"],
        "from_date": data["from_date"], "to_date": data["to_date"],
        "total": len(data["items"]), "processed": completed,
        "current_window": data.get("current_window"),
        "current_window_chunks": ({"completed": data.get("current_window"),
                                   "symbol": data.get("current_symbol")} if data.get("current_window") else None),
        "counts": counts, "current_symbol": data.get("current_symbol"),
        "prepared_dataset_id": data.get("prepared_dataset_id"),
        "errors": counts["failed"],
        "source": ("DhanHQ OHLCV + reconstructed dated NSE membership"
                   if data.get("historical_index") else "DhanHQ current instrument master"),
        "historical_index_name": data.get("historical_index", {}).get("index_name"),
        "index_spot": data.get("index_spot"),
        "historical_union_count": len(data.get("historical_index", {}).get("union_members", [])),
        "historical_unresolved": data.get("historical_index", {}).get("unresolved", []),
        "membership_covered_through": data.get("historical_index", {}).get("covered_through"),
        "warning": ("Reconstructed historical membership with explicit Dhan mapping gaps. "
                    "OHLCV is not total-return adjusted."
                    if data.get("historical_index") else
                    "OHLCV, not audited total returns or historical Nifty membership"),
    }


def create_batch(selection: str, ids: list[str], tickers: list[str],
                 from_date: str, to_date: str, interval: int | None,
                 acknowledged_bulk: bool, acknowledged_gaps: bool = False,
                 include_index_spot: bool = True) -> dict:
    start, stop = date.fromisoformat(from_date), date.fromisoformat(to_date)
    if not start < stop <= date.today() + timedelta(days=1):
        raise ValueError("Select a valid historical date range (end exclusive)")
    if (stop - start).days > 365 * 30:
        raise ValueError("Download range cannot exceed 30 years")
    if interval is not None and interval not in {1, 5, 15, 25, 60}:
        raise ValueError("Unsupported intraday resolution")
    plan = None
    if selection in pit_index.MODES:
        plan = pit_index.query(selection, from_date, to_date, catalog())
        if plan["unresolved"] and not acknowledged_gaps:
            sample = ", ".join(item["symbol"] for item in plan["unresolved"][:8])
            raise ValueError(
                f"{len(plan['unresolved'])} historical index symbols have no unambiguous "
                f"Dhan cash-equity Security ID ({sample}). Check the membership "
                "preview and explicitly acknowledge incomplete price coverage.")
        instruments = plan["resolved"]
        if not instruments:
            raise ValueError("None of the historical index members resolve in Dhan's current instrument catalog")
    else:
        instruments = _choose(selection, ids, tickers)
    if len(instruments) > 100 and not acknowledged_bulk:
        raise ValueError("Acknowledge the scope of downloads for more than 100 instruments")
    if interval is not None:
        # Dhan permits 90 calendar days per intraday API request, not a
        # maximum of 100 instruments per batch. Larger user-acknowledged
        # batches are processed sequentially and saved per date window.
        if start < date.today() - timedelta(days=365 * 5 + 2):
            raise ValueError("Dhan provides intraday candles for the latest five years; select a newer start date")
    batch_id = "batch_" + uuid.uuid4().hex[:16]
    folder = _batches() / batch_id
    folder.mkdir(parents=True, exist_ok=False)
    data = {
        "id": batch_id, "selection": selection, "exchange": "BSE" if selection == "all_bse" else "NSE",
        "status": "queued", "created_utc": _now(), "from_date": from_date,
        "to_date": to_date, "interval": interval,
        "current_symbol": None, "source_master_sha256": hashlib.sha256(_master().read_bytes()).hexdigest(),
        "items": [{**row, "status": "pending", "rows": 0, "rows_added": 0, "error": None}
                  for row in instruments],
        **({"historical_index": pit_index.pin_selection(plan)} if plan else {}),
        **({"index_spot": {"status": "pending", "warning": "Price-index candles are not TRI"}}
           if plan and include_index_spot else {}),
    }
    _atomic_json(folder / "manifest.json", data)
    return _summarize(data)


def list_batches() -> list[dict]:
    folder = _batches()
    if not folder.exists():
        return []
    result = []
    for sub in sorted(folder.iterdir(), reverse=True):
        if not BATCH_ID.fullmatch(sub.name) or not sub.is_dir() or sub.is_symlink():
            continue
        try:
            result.append(_summarize(_load_batch(sub.name)))
        except (ValueError, OSError, KeyError, json.JSONDecodeError):
            continue
    return result[:100]


def batch_details(batch_id: str, page: int = 1, per_page: int = 60,
                  status: str = "all") -> dict:
    if not 1 <= page <= 10000 or not 1 <= per_page <= 100:
        raise ValueError("Invalid pagination")
    data = _load_batch(batch_id)
    items = data["items"] if status == "all" else [x for x in data["items"] if x["status"] == status]
    start = (page - 1) * per_page
    return {**_summarize(data), "items": items[start:start + per_page],
            "page": page, "per_page": per_page, "filtered_total": len(items)}


def _uncovered(start: date, end: date, spans: list[list[str]]) -> list[tuple[date, date]]:
    cursor, gaps = start, []
    for first, last in sorted((date.fromisoformat(a), date.fromisoformat(b)) for a, b in spans):
        if last <= cursor or first >= end:
            continue
        if first > cursor:
            gaps.append((cursor, min(first, end)))
        cursor = max(cursor, last)
        if cursor >= end:
            break
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def _fetch_history(row: dict, start: str, stop: str, interval: int | None,
                   on_progress=None, should_stop=None) -> dict:
    """Fetch/cache each Dhan date window independently and resumably.

    Dhan allows at most 90 calendar days per intraday request. The original
    implementation downloaded a full year into memory and only wrote the
    cache after the *last* window, losing progress if request five failed.
    This implementation commits a SHA-256-verified CSV+manifest after EACH
    successful window. A resumed batch skips covered windows. Download
    retries and rate-limit backoff live in the shared Dhan V2 adapter.
    """
    target = _history_file(row, interval)
    manifest = target.with_suffix(".json")
    previous: dict = {"coverage": []}
    existing: pd.DataFrame | None = None
    if target.is_file() or manifest.is_file():
        if not target.is_file() or not manifest.is_file() or target.is_symlink() or manifest.is_symlink():
            raise ValueError("Cached candle data/manifest mismatch; manual evidence review required")
        previous = json.loads(manifest.read_text())
        if previous.get("sha256") != hashlib.sha256(target.read_bytes()).hexdigest():
            raise ValueError("Cached OHLCV SHA-256 mismatch")
        if previous.get("instrument_id") != row["id"] or previous.get("interval_minutes") != interval:
            raise ValueError("Cached OHLCV instrument identity or interval mismatch")
        existing = pd.read_csv(target, dtype={"security_id": str}, low_memory=False)
        if "datetime" not in existing.columns or existing["datetime"].duplicated().any():
            raise ValueError("Cached OHLCV structure invalid")
    initial_count = len(existing) if existing is not None else 0
    gaps = _uncovered(date.fromisoformat(start), date.fromisoformat(stop),
                      previous.get("coverage", []))
    window_days = 90 if interval is not None else 365
    windows = [window for left, right in gaps
               for window in date_windows(left, right, window_days)]
    total = len(windows)
    if not windows:
        if on_progress:
            on_progress(0, 0, initial_count)
        return {"status": "cached", "rows": initial_count, "rows_added": 0,
                "windows_completed": 0, "windows_total": 0}
    inst = Instrument(label="EQUITY_" + row["security_id"],
                      security_id=row["security_id"],
                      exchange_segment=row["exchange_segment"], instrument="EQUITY")
    covered = list(previous.get("coverage", []))
    added = 0
    attempted = 0

    def normalize(frame: pd.DataFrame) -> pd.DataFrame:
        copy = frame.copy()
        copy["datetime"] = (pd.to_datetime(copy["datetime"], utc=True, errors="raise")
                            .dt.tz_convert("Asia/Kolkata")
                            .dt.strftime("%Y-%m-%dT%H:%M:%S%z"))
        return copy

    for first, last in windows:
        if should_stop is not None and should_stop():
            # Preserve already cached windows and stop before the next call.
            raise InterruptedError("Batch pause requested after last completed date window")
        frame: pd.DataFrame | None = None
        try:
            frame = download_candles(inst, first.isoformat(), last.isoformat(),
                                     interval=interval, pause_seconds=0.4)
        except ValueError as exc:
            if not str(exc).startswith("No candles returned for "):
                raise
        attempted += 1
        if frame is None or frame.empty:
            # A no-data result is not evidence of complete historical coverage;
            # do not mark this span as cached or synthesize missing candles.
            if on_progress:
                on_progress(attempted, total, len(existing) if existing is not None else 0)
            continue
        incoming = normalize(frame)
        incoming = incoming.sort_values("datetime")
        if incoming["datetime"].duplicated().any():
            raise ValueError("Duplicate candle timestamps within Dhan date window")
        combined = (pd.concat([existing, incoming], ignore_index=True)
                    if existing is not None else incoming)
        combined = combined.sort_values("datetime").drop_duplicates("datetime", keep="last")
        if combined.empty or combined["datetime"].isna().any():
            raise ValueError("Empty or malformed downloaded OHLCV")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + "." + uuid.uuid4().hex[:8] + ".tmp")
        try:
            combined.to_csv(temp, index=False)
            digest = hashlib.sha256(temp.read_bytes()).hexdigest()
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        covered.append([first.isoformat(), last.isoformat()])
        _atomic_json(manifest, {
            "instrument_id": row["id"], "display_symbol": row["symbol"],
            "interval_minutes": interval, "coverage": covered,
            "rows": int(len(combined)), "sha256": digest,
            "updated_utc": _now(), "source": "DhanHQ historical OHLCV",
            "window_size_days": window_days,
            "warning": "Dhan historical OHLCV is not verified dividend-adjusted total returns.",
        })
        existing = combined
        added += len(incoming)
        if on_progress:
            on_progress(attempted, total, len(existing))
    return {
        "status": "complete" if existing is not None else "no_data",
        "rows": int(len(existing)) if existing is not None else 0,
        "rows_added": added, "windows_completed": attempted,
        "windows_total": total,
    }

def run_batch(batch_id: str, cancel_event: threading.Event | None = None) -> dict:
    data = _load_batch(batch_id)
    with ACTIVE_LOCK:
        if batch_id in ACTIVE_BATCHES:
            raise ValueError("Download batch is already active")
        ACTIVE_BATCHES.add(batch_id)
    data["status"] = "running"
    _save_batch(data)
    LOG.info("Dhan batch started: batch_id=%s instruments=%d interval=%s from=%s to=%s",
             batch_id, len(data["items"]), data["interval"], data["from_date"], data["to_date"])
    try:
        for item in data["items"]:
            if item["status"] in ("complete", "cached"):
                continue
            if cancel_event is not None and cancel_event.is_set():
                data["status"] = "cancelled"
                data["current_symbol"] = None
                _save_batch(data)
                return _summarize(data)
            item["status"] = "downloading"
            LOG.info("Dhan batch instrument started: batch_id=%s symbol=%s security_id=%s",
                     batch_id, item["symbol"], item["security_id"])
            data["current_symbol"] = item["symbol"]
            _save_batch(data)
            try:
                def window_progress(done: int, total: int, cached_rows: int):
                    item.update(windows_completed=done, windows_total=total,
                                rows=cached_rows)
                    LOG.info("Dhan batch progress: batch_id=%s symbol=%s windows=%d/%d cached_rows=%d",
                             batch_id, item["symbol"], done, total, cached_rows)
                    data["current_window"] = (f"{done}/{total}" if total else None)
                    _save_batch(data)
                result = _fetch_history(
                    item, data["from_date"], data["to_date"], data["interval"],
                    on_progress=window_progress,
                    should_stop=(cancel_event.is_set if cancel_event is not None else None),
                )
                item.update(**result, error=None)
                LOG.info("Dhan instrument completed: batch_id=%s symbol=%s status=%s rows=%s",
                         batch_id, item["symbol"], result.get("status"), result.get("rows"))
                data["current_window"] = None
            except InterruptedError:
                LOG.info("Dhan batch pause requested: batch_id=%s symbol=%s", batch_id, item["symbol"])
                item.update(status="pending", error=None)
                data["status"] = "paused"
                data["current_symbol"] = None
                data["current_window"] = None
                _save_batch(data)
                return _summarize(data)
            except Exception as exc:
                # The Dhan transport already hides vendor response content.
                error = str(exc)
                token = os.getenv("DHAN_ACCESS_TOKEN", "")
                if token:
                    error = error.replace(token, "[REDACTED]")
                LOG.error("Dhan instrument failed: batch_id=%s symbol=%s security_id=%s detail=%s",
                          batch_id, item["symbol"], item["security_id"], error[:220])
                item.update(status="failed", rows_added=0, error=error[:220])
                if "HTTP 401" in error or "HTTP 403" in error:
                    LOG.warning("Dhan batch paused due to authentication/entitlement error: batch_id=%s status=%s",
                                batch_id, "401" if "HTTP 401" in error else "403")
                    data["status"] = "paused"
                    _save_batch(data)
                    return _summarize(data)
            _save_batch(data)
        if data.get("index_spot") and (cancel_event is None or not cancel_event.is_set()):
            if data["index_spot"]["status"] != "complete":
                data["index_spot"] = index_spot.download(data)
                _save_batch(data)
        data["status"] = "completed"
        LOG.info("Dhan batch completed: batch_id=%s total=%d", batch_id, len(data["items"]))
        data["current_symbol"] = None
        _save_batch(data)
        return _summarize(data)
    finally:
        with ACTIVE_LOCK:
            ACTIVE_BATCHES.discard(batch_id)


def prepare_batch(batch_id: str) -> dict:
    data = _load_batch(batch_id)
    if data["interval"] is not None:
        raise ValueError("Monthly price matrices can only be prepared from daily OHLCV")
    eligible = [row for row in data["items"] if row["status"] in ("complete", "cached")]
    if not eligible:
        raise ValueError("No completed daily instruments to prepare")
    output = service.DATA / "dhan" / "monthly_research" / batch_id
    output.mkdir(parents=True, exist_ok=True)
    if (output / "prices.csv").exists():
        raise ValueError("Prepared dataset already exists; refusing to overwrite")
    streams, mappings = [], []
    used: set[str] = set()
    for row in eligible:
        source = _history_file(row, None)
        meta = json.loads(source.with_suffix(".json").read_text())
        if hashlib.sha256(source.read_bytes()).hexdigest() != meta.get("sha256"):
            raise ValueError("OHLCV cache changed after download; refusing to prepare")
        frame = pd.read_csv(source, usecols=["datetime", "close"])
        times = pd.to_datetime(frame["datetime"], utc=True, errors="raise").dt.tz_convert("Asia/Kolkata")
        values = pd.to_numeric(frame["close"], errors="raise")
        if values.isna().any() or (values <= 0).any():
            raise ValueError("Invalid recorded closing prices")
        # A shared cache can contain MORE history than this batch requested.
        # Preparing a batch must never leak observations outside its dates.
        within = ((times.dt.date >= date.fromisoformat(data["from_date"]))
                  & (times.dt.date < date.fromisoformat(data["to_date"])))
        if not within.any():
            continue
        # Anchor monthly data to actual observed sessions; never promote a
        # stale security close to a subsequent month-end trading date.
        selected_days = times.loc[within].dt.tz_localize(None).dt.normalize()
        if selected_days.duplicated().any():
            raise ValueError("Duplicate local OHLC daily sessions: " + row["symbol"])
        observed = pd.Series(values.loc[within].to_numpy(dtype=float),
                             index=pd.DatetimeIndex(selected_days)).sort_index()
        symbol = row.get("pit_symbol", row["symbol"])
        if data.get("historical_index"):
            if symbol in used or not SAFE_SYMBOL.fullmatch(symbol):
                raise ValueError("Historical index symbol is duplicated or unsafe: " + symbol)
        elif symbol in used or not SAFE_SYMBOL.fullmatch(symbol):
            symbol = row["exchange_segment"] + "_" + row["security_id"]
        used.add(symbol)
        observed.name = symbol
        streams.append(observed)
        mappings.append({"column": symbol, "security_id": row["security_id"],
                         "exchange_segment": row["exchange_segment"],
                         "source_sha256": meta["sha256"]})
    if not streams:
        raise ValueError("No observed trading closes within the selected batch dates")
    daily_panel = pd.concat(streams, axis=1).sort_index()
    if daily_panel.empty or daily_panel.index.has_duplicates:
        raise ValueError("No unique observed trading sessions in downloaded candles")
    # Use the last market session actually present in the batch per month.
    # A stock lacking that day's close remains NaN, never forward-filled.
    final_sessions = (
        pd.Series(daily_panel.index, index=daily_panel.index)
        .groupby(daily_panel.index.to_period("M")).max()
    )
    marks = pd.DatetimeIndex(final_sessions.to_list(), name="date")
    prices = daily_panel.reindex(marks)
    if prices.empty:
        raise ValueError("No monthly market sessions in downloaded candles")
    historical = data.get("historical_index")
    missing_symbols: list[str] = []
    missing_membership_prices = 0
    if historical:
        # The Dhan cache may contain only part of the requested first/last
        # calendar month. Reject partial-month marks for an index backtest.
        start = date.fromisoformat(data["from_date"])
        stop = date.fromisoformat(data["to_date"])
        full_months = [
            stamp for stamp in prices.index
            if start <= stamp.to_period("M").start_time.date()
            and stop > stamp.to_period("M").end_time.date()
        ]
        if not full_months:
            raise ValueError("Historical index preparation needs at least one fully "
                             "covered calendar month. Extend the date range.")
        prices = prices.loc[full_months]
        membership = pit_index.monthly_membership(data, prices.index, list(prices.columns))
        mask = membership.pivot(index="date", columns="ticker", values="eligible")
        mask.index = pd.to_datetime(mask.index)
        mask = mask.reindex(index=prices.index, columns=prices.columns).fillna(False)
        missing_membership_prices = int((mask & prices.isna()).to_numpy().sum())
        missing_symbols = sorted(set(historical["union_members"]) - set(prices.columns))
        membership.to_csv(output / "membership.csv", index=False)
        _atomic_json(output / "PIT_MEMBERSHIP_PROVENANCE.json", {
            **historical,
            "generated_utc": _now(),
            "membership_dates": [stamp.date().isoformat() for stamp in prices.index],
            "missing_historical_symbols": missing_symbols,
            "missing_eligible_price_observations": missing_membership_prices,
            "fully_covered_months_only": True,
            "month_marks": "last observed market session; no stale price carryforward",
            "session_calendar_basis": "observed Dhan cash equity sessions, not independently NSE-calendar certified",
            "index_spot": data.get("index_spot"),
            "warning": "Independently reconstructed interval history (not NSE-certified). "
                       "Dhan price candles lack a verified dividend-total-return adjustment."
        })
    prices.to_csv(output / "prices.csv", index_label="date")
    _atomic_json(output / "DHAN_BATCH_PROVENANCE.json", {
        "source_batch": batch_id, "generated_utc": _now(),
        "from_inclusive": data["from_date"], "to_exclusive": data["to_date"],
        "columns": mappings, "observations": len(prices),
        "month_marks": "last observed trading session; missing prices remain NaN",
        "warning": "UNADJUSTED MONTHLY PRICES ONLY. No benchmark, PIT constituents, "
                   "delisting coverage or dividend-reinvested total returns established.",
    })
    data["prepared_dataset_id"] = "dhan_" + batch_id
    _save_batch(data)
    return {"dataset_id": data["prepared_dataset_id"],
            "file": str(Path("data") / "dhan" / "monthly_research" / batch_id / "prices.csv"),
            "securities": len(mappings), "months": len(prices),
            "membership_generated": bool(historical),
            "membership_missing_symbols": missing_symbols,
            "missing_eligible_price_observations": missing_membership_prices,
            "ready_for_backtesting": False,
            "missing": ["benchmark.csv"] if historical else ["membership.csv", "benchmark.csv"],
            "warning": ("Point-in-time index membership generated from source-dated events. "
                        "Historical pricing may be incomplete; a compatible total-return "
                        "benchmark and independent source audit remain required."
                        if historical else
                        "This price matrix is incomplete for survivorship-free index research.")}


def preview_history(instrument_id: str, interval: int | None = None,
                    limit: int = 140) -> dict:
    match = KEY.fullmatch(instrument_id)
    if not match or not 1 <= limit <= 300:
        raise ValueError("Unknown instrument or invalid candle preview limit")
    if interval is not None and interval not in {1, 5, 15, 25, 60}:
        raise ValueError("Unknown candle resolution")
    row = {"exchange_segment": match.group(1), "security_id": match.group(2)}
    path = _history_file(row, interval)
    sidecar = path.with_suffix(".json")
    if not path.is_file() or not sidecar.is_file() or path.is_symlink() or sidecar.is_symlink():
        raise FileNotFoundError("No locally downloaded candles for this instrument and interval")
    metadata = json.loads(sidecar.read_text())
    if metadata.get("instrument_id") != instrument_id:
        raise ValueError("Cached instrument identity does not match")
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata.get("sha256"):
        raise ValueError("Cached candles failed SHA-256 integrity check")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not {"datetime", "open", "high", "low", "close", "volume"}.issubset(reader.fieldnames or []):
            raise ValueError("Cached OHLCV columns are incomplete")
        rows = list(deque(reader, maxlen=limit))
    return {
        "symbol": metadata.get("display_symbol", instrument_id),
        "instrument_id": instrument_id, "interval": interval,
        "total_rows": metadata.get("rows", 0),
        "rows": [{name: (float(value) if name in ("open", "high", "low", "close", "volume")
                          and value not in ("", None) else value)
                  for name, value in item.items() if name in
                  ("datetime", "open", "high", "low", "close", "volume", "open_interest")}
                 for item in rows],
        "warning": metadata.get("warning"),
    }
