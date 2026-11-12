"""One canonical, append-only Dhan equity-price store for QuantLab.

SQLite is the instrument/session source of truth; shared daily/monthly CSVs are
derived model views. Per-batch PIT membership and benchmark files remain separate
because NIFTY 50 and BANK NIFTY have different historical universes.
"""
from __future__ import annotations

from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from threading import RLock
import hashlib
import json
import math
import os
import re
import sqlite3
import uuid

import pandas as pd

from . import service

SHARED_ID = "dhan_shared"
SAFE_COLUMN = re.compile(r"^[A-Za-z0-9&_.-]{1,80}$")
SAFE_IDENTITY = re.compile(r"^(NSE_EQ|BSE_EQ):[0-9]{1,12}$")
LOCK = RLock()


def shared_folder() -> Path:
    return service.DATA / "dhan" / "monthly_research" / "shared"


def database_path() -> Path:
    return service.DATA / "dhan" / "shared_market.sqlite3"


def _connect():
    target = database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=30)
    connection.execute("PRAGMA busy_timeout=30000")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS instruments (
            identity TEXT PRIMARY KEY,
            exchange_segment TEXT NOT NULL,
            security_id TEXT NOT NULL,
            display_symbol TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_closes (
            identity TEXT NOT NULL REFERENCES instruments(identity),
            session_date TEXT NOT NULL,
            close REAL NOT NULL CHECK(close > 0),
            source_sha256 TEXT NOT NULL,
            PRIMARY KEY(identity, session_date)
        );
        CREATE TABLE IF NOT EXISTS ingestions (
            origin TEXT NOT NULL,
            identity TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            observed_rows INTEGER NOT NULL,
            ingested_utc TEXT NOT NULL,
            PRIMARY KEY(origin, identity, source_sha256)
        );
        CREATE INDEX IF NOT EXISTS closes_by_session ON daily_closes(session_date);
    """)
    return connection


def _identity(mapping: dict) -> str:
    key = f"{mapping['exchange_segment']}:{mapping['security_id']}"
    if not SAFE_IDENTITY.fullmatch(key):
        raise ValueError("Invalid Dhan security identity in source provenance")
    return key


def _frame_rows(frame: pd.DataFrame):
    if "close" not in frame.columns:
        raise ValueError("Source daily OHLCV has no close field")
    dates = pd.to_datetime(frame.index, errors="raise")
    if dates.isna().any() or dates.has_duplicates:
        raise ValueError("Source daily OHLCV contains invalid or repeated sessions")
    values = pd.to_numeric(frame["close"], errors="raise")
    if values.isna().any() or not all(math.isfinite(float(v)) and float(v) > 0 for v in values):
        raise ValueError("Source daily OHLCV contains invalid close values")
    return [(stamp.date().isoformat(), float(value)) for stamp, value in zip(dates, values)]


def _atomic_csv(frame: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.with_name(path.name + "." + uuid.uuid4().hex[:8] + ".tmp")
    try:
        frame.to_csv(target, index_label="date", float_format="%.12g")
        os.replace(target, path)
    finally:
        target.unlink(missing_ok=True)


def _atomic_json(value: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.with_name(path.name + "." + uuid.uuid4().hex[:8] + ".tmp")
    try:
        target.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))
        os.replace(target, path)
    finally:
        target.unlink(missing_ok=True)


def publish_views() -> dict:
    """Materialize one shared daily/monthly model view from canonical SQLite."""
    with LOCK:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT identity,session_date,close FROM daily_closes ORDER BY session_date,identity"
            ).fetchall()
            mappings = conn.execute(
                "SELECT identity,exchange_segment,security_id,display_symbol FROM instruments ORDER BY identity"
            ).fetchall()
            origins = [r[0] for r in conn.execute("SELECT DISTINCT origin FROM ingestions ORDER BY origin")]
        if not rows:
            return {"dataset_id": SHARED_ID, "securities": 0, "daily_sessions": 0}
        columns = {m[0]: m[0].replace(":", "_") for m in mappings}
        observed = pd.DataFrame(rows, columns=["identity", "date", "close"])
        observed["date"] = pd.to_datetime(observed["date"], errors="raise")
        wide = observed.pivot(index="date", columns="identity", values="close")
        wide = wide.rename(columns=columns).sort_index().sort_index(axis=1)
        wide.index.name = "date"
        # Month-end mark is the last session actually observed in the union.
        # Never ffill a missing price for a particular stock.
        marks = wide.groupby(wide.index.to_period("M")).tail(1)
        folder = shared_folder()
        _atomic_csv(wide, folder / "daily_prices.csv")
        _atomic_csv(marks, folder / "prices.csv")
        metadata = {
            "dataset_id": SHARED_ID,
            "version": 1,
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "storage": "data/dhan/shared_market.sqlite3",
            "identity_rule": "exchange_segment + Dhan Security ID; no alias-based deduplication",
            "daily_sessions": len(wide),
            "monthly_marks": len(marks),
            "securities": len(mappings),
            "source_origins": origins,
            "columns": [
                {"column": columns[k], "exchange_segment": segment,
                 "security_id": sid, "display_symbol": symbol, "identity": k}
                for k, segment, sid, symbol in mappings
            ],
            "daily_sha256": hashlib.sha256((folder / "daily_prices.csv").read_bytes()).hexdigest(),
            "monthly_sha256": hashlib.sha256((folder / "prices.csv").read_bytes()).hexdigest(),
            "no_forward_fill": True,
            "warning": "Unadjusted Dhan closes are not verified total returns. "
                       "Missing sessions, delistings and historical membership are not manufactured. "
                       "PIT membership remains attached to its source index dataset.",
        }
        _atomic_json(metadata, folder / "SHARED_MARKET_PROVENANCE.json")
        return {"dataset_id": SHARED_ID, "securities": len(mappings),
                "daily_sessions": len(wide), "monthly_marks": len(marks),
                "source_origins": origins}


def ingest(entries: list[tuple[dict, pd.DataFrame]], *, origin: str) -> dict:
    """Insert only new instrument/date closes; reject conflicting observations.

    Duplicates are reused, never overwritten or replaced by a new data set.
    Atomic SQLite transaction prevents half-imported batches. Models receive a
    newly published view only after all sources have passed validation.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,90}", origin):
        raise ValueError("Unsafe market-data provenance origin")
    inserted = 0
    reused = 0
    with LOCK:
        with _connect() as conn:
            for mapping, frame in entries:
                key = _identity(mapping)
                symbol = str(mapping.get("display_symbol") or mapping.get("column") or key)
                digest = str(mapping.get("source_sha256") or "")
                if not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise ValueError("Cached source checksum unavailable: " + key)
                observations = _frame_rows(frame)
                if not observations:
                    continue
                conn.execute("""
                    INSERT INTO instruments(identity,exchange_segment,security_id,display_symbol)
                    VALUES(?,?,?,?)
                    ON CONFLICT(identity) DO UPDATE SET display_symbol=excluded.display_symbol
                """, (key, mapping["exchange_segment"], str(mapping["security_id"]), symbol))
                for stamp, close in observations:
                    current = conn.execute(
                        "SELECT close FROM daily_closes WHERE identity=? AND session_date=?",
                        (key, stamp)).fetchone()
                    if current is not None:
                        if not math.isclose(current[0], close, rel_tol=1e-7, abs_tol=1e-5):
                            raise ValueError("Conflicting Dhan closes require an explicit audit: "
                                             + key + " " + stamp)
                        reused += 1
                        continue
                    conn.execute("INSERT INTO daily_closes VALUES(?,?,?,?)",
                                 (key, stamp, close, digest))
                    inserted += 1
                conn.execute("INSERT OR IGNORE INTO ingestions VALUES(?,?,?,?,?)",
                             (origin, key, digest, len(observations),
                              datetime.now(timezone.utc).isoformat()))
        result = publish_views()
    return {**result, "rows_appended": inserted, "rows_reused": reused}


def ingest_prepared(dataset_id: str) -> dict:
    """Import an existing prepared Dhan batch without requesting any Dhan data."""
    folder, record = service.dataset_path(dataset_id)
    if record["kind"] != "dhan" or dataset_id == SHARED_ID:
        raise ValueError("Only local Dhan prepared batches can be imported")
    source = folder / "DHAN_BATCH_PROVENANCE.json"
    if not source.is_file() or source.is_symlink():
        raise ValueError("No verified Dhan batch mapping is available")
    info = json.loads(source.read_text())
    entries = []
    for column in info.get("columns", []):
        name = str(column.get("column", ""))
        if not SAFE_COLUMN.fullmatch(name):
            raise ValueError("Unsafe Dhan prepared OHLCV column")
        file = folder / "daily_ohlcv" / (name + ".csv")
        if not file.is_file() or file.is_symlink():
            raise ValueError("Missing prepared daily OHLCV: " + name)
        bars = pd.read_csv(file, parse_dates=["date"]).set_index("date")
        entries.append(({**column, "display_symbol": name}, bars))
    if not entries:
        raise ValueError("No prepared Dhan instruments to reuse")
    return ingest(entries, origin=dataset_id)


def ingest_cached(row: dict, interval: int | None, start: date, stop: date) -> dict:
    """Import an already downloaded, SHA-verified Dhan candle cache."""
    from . import dhan_workspace
    bars, mapping = dhan_workspace._batch_daily_ohlcv(row, interval, start, stop)
    mapping["display_symbol"] = row.get("pit_symbol", row["symbol"])
    return ingest([(mapping, bars)], origin="cache_" + row["exchange_segment"]
                  + "_" + row["security_id"] + "_" + ("daily" if interval is None else str(interval) + "m"))


def cached_spans(row: dict) -> list[tuple[int | None, date, date]]:
    """Return exact manifest-covered windows, independently for each interval."""
    from . import dhan_workspace
    spans = []
    for interval in (None, 1, 5, 15, 25, 60):
        source = dhan_workspace._history_file(row, interval)
        sidecar = source.with_suffix(".json")
        if not source.is_file() or not sidecar.is_file() or source.is_symlink() or sidecar.is_symlink():
            continue
        data = json.loads(sidecar.read_text())
        if (data.get("instrument_id") != row["id"] or
                data.get("interval_minutes") != interval or
                hashlib.sha256(source.read_bytes()).hexdigest() != data.get("sha256")):
            raise ValueError("Cached candle provenance or identity mismatch: " + row["id"])
        for first, last in data.get("coverage", []):
            begin, end = date.fromisoformat(first), date.fromisoformat(last)
            if begin < end:
                spans.append((interval, begin, end))
    return spans


def reuse_cached(row: dict) -> dict:
    """Rebuild shared prices from existing daily/intraday cache before any API call."""
    entries = []
    # Prefer 1m cache where present; identical overlaps are validated by ingest().
    for interval, begin, end in cached_spans(row):
        try:
            from . import dhan_workspace
            bars, mapping = dhan_workspace._batch_daily_ohlcv(row, interval, begin, end)
        except ValueError as exc:
            if str(exc).startswith("No cached candles inside"):
                continue
            raise
        mapping["display_symbol"] = row.get("pit_symbol", row["symbol"])
        entries.append((mapping, bars))
    if not entries:
        return {"dataset_id": SHARED_ID, "rows_appended": 0, "rows_reused": 0}
    return ingest(entries, origin="cached_" + row["exchange_segment"] + "_" + row["security_id"])
