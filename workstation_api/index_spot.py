"""Optional Dhan IDX_I historical spot-index candles.

The index quote is a *price index*, never passed off as an adjusted total-return
benchmark. Resolve the underlying ID against the current official scrip master,
not a hardcoded security ID or an equity instrument.
"""
from __future__ import annotations

from pathlib import Path
import os
import re

import pandas as pd

from index_research.dhan_data import Instrument, download_candles, save_download
from . import pit_index, service


def resolve(mode: str) -> Instrument | None:
    if mode not in pit_index.MODES:
        return None
    path = service.DATA / "dhan" / "instrument_master.csv"
    if not path.is_file() or path.is_symlink():
        return None
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    aliases = {str(k).upper().strip(): k for k in frame.columns}
    def col(*names):
        return next((aliases[n] for n in names if n in aliases), None)
    segment = col("SEGMENT", "SEM_SEGMENT")
    instrument = col("INSTRUMENT", "SEM_INSTRUMENT_NAME")
    identifier = col("SECURITY_ID", "SEM_SMST_SECURITY_ID")
    labels = [col(n) for n in ("SEM_TRADING_SYMBOL", "TRADING_SYMBOL", "SEM_CUSTOM_SYMBOL",
                               "DISPLAY_NAME", "SM_SYMBOL_NAME", "SYMBOL_NAME")]
    labels = [name for name in labels if name]
    if not segment or not instrument or not identifier or not labels:
        return None
    expected = ({"NIFTY", "NIFTY50"} if mode == "nifty50_pit"
                else {"BANKNIFTY", "NIFTYBANK"})
    matches = set()
    for _, row in frame.iterrows():
        if str(row[instrument]).upper().strip() != "INDEX":
            continue
        if str(row[segment]).upper().strip() not in {"I", "IDX_I"}:
            continue
        names = {re.sub(r"[^A-Z0-9]", "", str(row[name]).upper()) for name in labels}
        if not names.intersection(expected):
            continue
        code = str(row[identifier]).strip()
        if code.isdigit() and 1 <= len(code) <= 12:
            matches.add(code)
    if len(matches) != 1:
        return None
    return Instrument(
        label="NIFTY50_INDEX" if mode == "nifty50_pit" else "BANKNIFTY_INDEX",
        security_id=next(iter(matches)), exchange_segment="IDX_I", instrument="INDEX",
    )


def download(data: dict) -> dict:
    instrument = resolve(data["selection"])
    if instrument is None:
        return {"status": "unavailable", "rows": 0,
                "error": "No unique INDEX/IDX_I mapping in the Dhan master",
                "warning": "Index spot OHLCV remains unavailable; constituent downloads are unaffected."}
    try:
        frame = download_candles(
            instrument, data["from_date"], data["to_date"],
            interval=data["interval"], pause_seconds=.4)
        folder = service.DATA / "dhan" / "index_spot" / data["id"]
        file, manifest = save_download(frame, instrument, folder,
                                       data["from_date"], data["to_date"], data["interval"])
        return {
            "status": "complete", "rows": len(frame), "security_id": instrument.security_id,
            "file": str(file.relative_to(service.DATA)),
            "manifest": str(manifest.relative_to(service.DATA)),
            "warning": "Dhan index SPOT OHLCV is not a dividend-reinvested TRI benchmark.",
        }
    except Exception as exc:
        token = os.getenv("DHAN_ACCESS_TOKEN", "")
        message = str(exc).replace(token, "[REDACTED]") if token else str(exc)
        return {"status": "failed", "rows": 0, "error": message[:180],
                "warning": "Index-level download failed; constituent downloads remain saved."}
