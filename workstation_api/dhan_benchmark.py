"""Create an explicitly PRICE-ONLY NIFTY benchmark from local Dhan index spot.

This never contacts Dhan, substitutes constituents for index values, or
claims that a price-index return includes reinvested dividends.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os

import numpy as np
import pandas as pd

from . import service


def prepare_price_benchmark(batch_id: str) -> dict:
    from . import dhan_workspace as dw
    if not dw.BATCH_ID.fullmatch(batch_id):
        raise ValueError("Unknown Dhan batch ID")
    batch = dw._load_batch(batch_id)
    historical = batch.get("historical_index")
    if not historical or batch["selection"] not in ("nifty50_pit", "banknifty_pit"):
        raise ValueError("A verified historical index batch is required")
    spot = batch.get("index_spot") or {}
    if spot.get("status") != "complete":
        raise ValueError("Index spot candles were not downloaded successfully for this batch")
    output = service.DATA / "dhan" / "monthly_research" / batch_id
    prices_file = output / "prices.csv"
    if not prices_file.is_file() or prices_file.is_symlink():
        raise ValueError("Prepare the stock dataset first")
    if (output / "benchmark.csv").exists():
        raise ValueError("benchmark.csv already exists; refusing to replace benchmark evidence")

    # Only a path under the known per-batch index spot directory is allowed.
    source_dir = (service.DATA / "dhan" / "index_spot" / batch_id).resolve()
    source = (service.DATA / str(spot.get("file", ""))).resolve()
    manifest = (service.DATA / str(spot.get("manifest", ""))).resolve()
    if source.parent != source_dir or manifest.parent != source_dir:
        raise ValueError("Index spot source path does not belong to this batch")
    if not source.is_file() or not manifest.is_file() or source.is_symlink() or manifest.is_symlink():
        raise ValueError("Saved index spot and manifest are required")
    meta = json.loads(manifest.read_text())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != meta.get("sha256"):
        raise ValueError("Index spot cache failed SHA-256 verification")
    identity = meta.get("instrument") or {}
    expected_id = "NIFTY50_INDEX" if batch["selection"] == "nifty50_pit" else "BANKNIFTY_INDEX"
    if identity.get("label") != expected_id or identity.get("exchange_segment") != "IDX_I":
        raise ValueError("Index spot instrument identity mismatch")
    if str(identity.get("security_id")) != str(spot.get("security_id")):
        raise ValueError("Index spot Security ID does not match batch metadata")

    frame = pd.read_csv(source, usecols=["datetime", "close"])
    if frame.empty:
        raise ValueError("Saved index spot is empty")
    times = pd.to_datetime(frame["datetime"], utc=True, errors="raise").dt.tz_convert("Asia/Kolkata")
    values = pd.to_numeric(frame["close"], errors="raise")
    if times.duplicated().any() or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Index spot contains duplicate timestamps or invalid closes")
    closes = pd.DataFrame({"stamp":times, "close":values}).sort_values("stamp")
    closes["date"] = closes["stamp"].dt.tz_localize(None).dt.normalize()
    daily = closes.groupby("date",sort=True)["close"].last()
    matrix = pd.read_csv(prices_file, usecols=["date"])
    marks = pd.DatetimeIndex(pd.to_datetime(matrix["date"], errors="raise"))
    if len(marks) < 2 or marks.has_duplicates or not marks.is_monotonic_increasing:
        raise ValueError("Prepared price marks are malformed or too short")
    monthly_returns = []
    evidence = []
    for mark in marks:
        # Benchmark must have an observed close ON the exact decision session,
        # plus a previous-month close. Never forward fill gaps or use future data.
        if mark not in daily.index:
            raise ValueError(f"Index spot missing decision-date close: {mark.date()}")
        prior = daily.loc[daily.index < mark.to_period("M").start_time]
        if prior.empty:
            raise ValueError("Index spot lacks a previous-month baseline for " + str(mark.date()))
        baseline_day = prior.index[-1]
        if baseline_day.to_period("M") != (mark.to_period("M") - 1):
            raise ValueError("Index spot missing immediately previous month for " + str(mark.date()))
        base = float(prior.iloc[-1])
        observed = float(daily.loc[mark])
        rate = observed / base - 1.0
        if not np.isfinite(rate) or rate <= -1:
            raise ValueError("Invalid index price return")
        monthly_returns.append({"date":mark.date().isoformat(), "return":rate})
        evidence.append({"mark":mark.date().isoformat(),
                         "previous_month_close_date":baseline_day.date().isoformat(),
                         "previous_month_close":base, "current_close":observed})
    target = output / "benchmark.csv"
    temp = output / ("benchmark.csv." + os.urandom(6).hex() + ".tmp")
    try:
        pd.DataFrame(monthly_returns).to_csv(temp, index=False)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    benchmark_digest = hashlib.sha256(target.read_bytes()).hexdigest()
    dw._atomic_json(output / "BENCHMARK_PROVENANCE.json", {
        "index": historical.get("index_name"),
        "basis": "price_index_spot_only",
        "is_total_return_index": False,
        "is_dividend_reinvested": False,
        "is_independently_verified": False,
        "source": "DhanHQ V2 IDX_I spot OHLCV from the original downloaded batch",
        "source_file_sha256": digest,
        "benchmark_file_sha256": benchmark_digest,
        "index_spot_identity_source": spot.get("identity_source"),
        "source_interval_minutes": meta.get("interval_minutes"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "month_marks": evidence,
        "warning": "PRICE INDEX ONLY. No dividend reinvestment, TRI benchmarking, "
                   "or corporate-action-correct total-return parity is claimed.",
    })
    return {"dataset_id": "dhan_" + batch_id,
            "benchmark_kind": "price_index_spot_only",
            "months": len(monthly_returns),
            "source_interval_minutes": meta.get("interval_minutes"),
            "source_sha256": digest,
            "warning": "Price-index comparison only. For total-return performance, "
                       "replace with independently sourced NIFTY TRI and audit the "
                       "stock corporate-action adjustments."}
