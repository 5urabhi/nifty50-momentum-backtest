"""Point-in-time NIFTY 50 / NIFTY BANK membership, with explicit provenance.

The historical intervals are reconstructed by an independent CC0 dataset from
public NSE Indices announcements. Dhan supplies *prices*, not past membership.
Never project today's constituent universe backwards. Interval boundaries are
inclusive valid_from, exclusive valid_to. No unknown-source extrapolation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import json
import os
import re
import uuid

import pandas as pd

from . import service

MODES = {"nifty50_pit": "Nifty 50", "banknifty_pit": "Nifty Bank"}
SOURCE_REPOSITORY = "aditya-jha/nse-historical-membership"
SOURCE_LICENSE = "CC0-1.0 (data), independent reconstruction; NSE trademarks not licensed"
SOURCE_PREFIX = "https://raw.githubusercontent.com/" + SOURCE_REPOSITORY + "/"
SOURCE_API = "https://api.github.com/repos/" + SOURCE_REPOSITORY + "/commits/main"
MEMBERS_FILE = "index_history/data/index_membership_history.csv"
COVERAGE_FILE = "COVERAGE.md"
OFFICIAL_BANK_NOTICE = "https://www.niftyindices.com/Press_Release/ind_prs01122025.pdf"
CORRECTION_EFFECTIVE = "2025-12-31"
SAFE_ID = re.compile(r"^[A-Za-z0-9&_.-]{1,80}$")
REQUIRED = {"index_name", "symbol", "valid_from", "valid_to", "source", "source_url"}
MAX_BYTES = 12 * 1024 * 1024


def _root() -> Path:
    return service.DATA / "index_membership"


def _csv_path() -> Path:
    return _root() / "nse_reconstructed_pit.csv"


def _metadata_path() -> Path:
    return _root() / "source_manifest.json"


def _fetch(url: str, size: int = MAX_BYTES) -> bytes:
    request = Request(url, headers={
        "User-Agent": "LocalQuantWorkstation/1.0 (+offline PIT research)",
        "Accept": "text/plain, application/json, text/csv",
    })
    with urlopen(request, timeout=50) as response:
        body = response.read(size + 1)
    if not body or len(body) > size:
        raise ValueError("Index-history source is empty or larger than allowed")
    return body


def _load_frame(body: bytes) -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(body), dtype=str, keep_default_na=False,
                        low_memory=False)
    if not REQUIRED.issubset(frame.columns):
        raise ValueError("Index-history CSV is missing required PIT interval fields")
    frame = frame.loc[frame["index_name"].isin(MODES.values())].copy()
    if frame.empty:
        raise ValueError("Nifty 50 and Nifty Bank membership are absent from the source")
    if (frame["symbol"].str.strip() == "").any():
        raise ValueError("Empty constituent symbol in historical index data")
    if not all(SAFE_ID.fullmatch(str(x)) for x in frame["symbol"]):
        raise ValueError("Unsafe constituent identifiers in index-history file")
    for col in ("valid_from", "valid_to"):
        active = frame[col] != ""
        try:
            frame.loc[active, col] = pd.to_datetime(frame.loc[active, col], errors="raise").dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid historical index effective dates") from exc
    if (frame["valid_from"] == "").any():
        raise ValueError("Missing valid_from dates in index history")
    if (frame["valid_to"].ne("") & (frame["valid_to"] <= frame["valid_from"])).any():
        raise ValueError("Invalid half-open effective interval")
    # An identical security cannot have two overlapping membership intervals
    # in the same index. We do not resolve disagreements by arbitrary priority.
    for (_, _), group in frame.groupby(["index_name", "symbol"]):
        ordered = group.sort_values("valid_from")
        previous_end: str | None = None
        for _, item in ordered.iterrows():
            if previous_end is not None and item["valid_from"] < previous_end:
                raise ValueError("Overlapping historical membership intervals")
            previous_end = item["valid_to"] or "9999-12-31"
    return frame


def _official_bank_correction(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Correct two late inferred additions using NSE's dated 2025-12-01 PR.

    This is a documented source reconciliation, *not* a heuristic ticker alias.
    Only apply when the upstream record exactly matches the known discrepancy.
    A future upstream fix passes through; any new disagreement blocks sync.
    """
    corrected = frame.copy()
    evidence = []
    for symbol in ("UNIONBANK", "YESBANK"):
        mask = ((corrected["index_name"] == "Nifty Bank")
                & (corrected["symbol"] == symbol)
                & (corrected["valid_to"] == "")
                & (corrected["valid_from"] >= CORRECTION_EFFECTIVE))
        matches = corrected.index[mask].to_list()
        if len(matches) != 1:
            raise ValueError("Official Bank Nifty event cannot be reconciled: " + symbol)
        index = matches[0]
        original = corrected.at[index, "valid_from"]
        if original != CORRECTION_EFFECTIVE:
            if original != "2026-09-30" or not str(corrected.at[index, "notes"]).startswith("inferred-include"):
                raise ValueError("Unexpected Bank Nifty membership history for " + symbol)
            corrected.at[index, "valid_from"] = CORRECTION_EFFECTIVE
            corrected.at[index, "source"] = "official_NSE_press_release_correction"
            corrected.at[index, "source_url"] = OFFICIAL_BANK_NOTICE
            corrected.at[index, "notes"] = "NSE notice dated 2025-12-01, effective 2025-12-31; original inferred source date 2026-09-30"
            evidence.append({"symbol": symbol, "old_date": original,
                             "corrected_effective": CORRECTION_EFFECTIVE,
                             "official_source": OFFICIAL_BANK_NOTICE})
    return corrected, evidence


def _checked_history(body: bytes) -> tuple[pd.DataFrame, list[dict]]:
    frame = _load_frame(body)
    corrected, changes = _official_bank_correction(frame)
    # The correction itself must not create overlaps.
    checked = _load_frame(corrected.to_csv(index=False).encode("utf-8"))
    for name in MODES.values():
        if len(checked.loc[checked["index_name"] == name]) < 15:
            raise ValueError("Index source is unexpectedly sparse: " + name)
    # Validate the ENTIRE event timeline rather than a handful of snapshots.
    # Membership is piecewise constant between effective-date boundaries, so
    # testing all boundaries catches mid-period missing transitions.
    for name in MODES.values():
        sub = checked.loc[checked["index_name"] == name]
        boundaries = sorted(set(sub["valid_from"]) | set(sub.loc[sub["valid_to"] != "", "valid_to"]))
        for day in boundaries:
            actual = len(_asof(checked, name, day))
            if name == "Nifty 50" and actual != 50:
                raise ValueError(
                    f"Nifty 50 index membership cardinality mismatch on {day}: {actual}, expected 50")
            # Nifty Bank was a 12-security index after the March 2020 change,
            # becoming 14 on the source-dated 2025-12-31 effective date.
            # Older snapshots are tagged best-effort and never treated as
            # externally audited by this structural gate.
            if name == "Nifty Bank":
                expected = (14 if day >= CORRECTION_EFFECTIVE else
                            12 if day >= "2020-03-27" else None)
                if expected is not None and actual != expected:
                    raise ValueError(
                        f"Nifty Bank membership cardinality mismatch on {day}: "
                        f"{actual}, expected {expected}")
    if not {"UNIONBANK", "YESBANK"}.issubset(_asof(checked, "Nifty Bank", CORRECTION_EFFECTIVE)):
        raise ValueError("Official bank index inclusion correction failed")
    return checked, changes


def _asof(frame: pd.DataFrame, index_name: str, day: str) -> set[str]:
    subset = frame.loc[(frame["index_name"] == index_name)
                       & (frame["valid_from"] <= day)
                       & ((frame["valid_to"] == "") | (frame["valid_to"] > day))]
    return set(subset["symbol"])


def sync() -> dict:
    """Download fixed, allowlisted CC0 interval source at a pinned Git commit.

    No application secrets are sent to GitHub. Raw/source and normalized/official
    patch checksums remain in ignored local data, never assumed authoritative.
    """
    sha = json.loads(_fetch(SOURCE_API, 200_000).decode("utf-8")).get("sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Unable to pin historical membership source commit")
    csv_url = SOURCE_PREFIX + sha + "/" + MEMBERS_FILE
    coverage_url = SOURCE_PREFIX + sha + "/" + COVERAGE_FILE
    body, info = _fetch(csv_url), _fetch(coverage_url, 100_000).decode("utf-8")
    match = re.search(r"Index membership\s*\|[^\n]*?(20\d{2}-\d{2}-\d{2})", info)
    if not match:
        raise ValueError("Source lacks a machine-readable validated coverage through date")
    coverage_through = match.group(1)
    source_frame, corrections = _checked_history(body)
    last_effective = max(source_frame["valid_from"])
    if coverage_through < last_effective:
        raise ValueError("Source claims coverage ending before a recorded effective change")
    first = min(source_frame["valid_from"])
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(body).hexdigest()
    output = source_frame.to_csv(index=False).encode("utf-8")
    processed_hash = hashlib.sha256(output).hexdigest()
    meta = {
        "kind": "independent_pit_reconstruction", "indexes": list(MODES.values()),
        "first_date": first, "covered_through": coverage_through,
        "synced_utc": datetime.now(timezone.utc).isoformat(),
        "source_repository": SOURCE_REPOSITORY, "source_commit": sha,
        "source_csv": csv_url, "source_sha256": source_hash,
        "normalized_sha256": processed_hash,
        "license": SOURCE_LICENSE,
        "official_source_corrections": corrections,
        "limitations": [
            "Independent reconstruction of NSE notices, not NSE-certified membership.",
            "Pre-2018 coverage can contain reconstruction errors; inspect official monthly snapshots.",
            "Ticker renames/delistings may not resolve in today's Dhan instrument catalog.",
            "Source verification ends at covered_through: no unverified future membership is assumed.",
        ],
    }
    tmp_csv = root / (".history_" + uuid.uuid4().hex[:10] + ".tmp")
    tmp_meta = root / (".manifest_" + uuid.uuid4().hex[:10] + ".tmp")
    try:
        tmp_csv.write_bytes(output)
        tmp_meta.write_text(json.dumps(meta, indent=2, allow_nan=False))
        os.replace(tmp_csv, _csv_path())
        os.replace(tmp_meta, _metadata_path())
    finally:
        tmp_csv.unlink(missing_ok=True)
        tmp_meta.unlink(missing_ok=True)
    return status()


def status() -> dict:
    if not _csv_path().is_file() or not _metadata_path().is_file():
        return {"available": False, "indices": [
            {"id": key, "name": value} for key, value in MODES.items()],
            "source": SOURCE_REPOSITORY,
            "message": "Sync reconstructed historical index membership before selecting a dated universe."}
    meta = json.loads(_metadata_path().read_text())
    if hashlib.sha256(_csv_path().read_bytes()).hexdigest() != meta.get("normalized_sha256"):
        raise ValueError("Stored index-history checksum mismatch; sync again")
    return {
        "available": True, "indices": [
            {"id": key, "name": value} for key, value in MODES.items()],
        "first_date": meta["first_date"], "covered_through": meta["covered_through"],
        "synced_utc": meta["synced_utc"], "source": meta["source_repository"],
        "source_commit": meta["source_commit"], "source_csv": meta["source_csv"],
        "corrections": meta["official_source_corrections"],
        "limitations": meta["limitations"],
    }


def _load_local() -> tuple[pd.DataFrame, dict]:
    details = status()
    if not details["available"]:
        raise ValueError("Historical index membership has not been synced")
    meta = json.loads(_metadata_path().read_text())
    return _load_frame(_csv_path().read_bytes()), meta


def _window(start: str, stop: str, meta: dict) -> tuple[date, date]:
    try:
        from_date, to_date = date.fromisoformat(start), date.fromisoformat(stop)
    except ValueError as exc:
        raise ValueError("Use ISO date YYYY-MM-DD for a historical index window") from exc
    if from_date >= to_date:
        raise ValueError("End date must be after start date (exclusive)")
    if from_date < date.fromisoformat(meta["first_date"]):
        raise ValueError("Historical index history begins at " + meta["first_date"])
    if to_date > date.fromisoformat(meta["covered_through"]) + timedelta(days=1):
        raise ValueError("Membership source documents coverage only through " + meta["covered_through"]
                         + ". Shorten the end date or sync a newer historical source.")
    return from_date, to_date


def query(mode: str, start: str, stop: str, instruments: list[dict] | None = None,
          as_of: str | None = None) -> dict:
    if mode not in MODES:
        raise ValueError("Unknown historical index")
    frame, meta = _load_local()
    first, last = _window(start, stop, meta)
    index_name = MODES[mode]
    subset = frame.loc[(frame["index_name"] == index_name)
                       & (frame["valid_from"] < stop)
                       & ((frame["valid_to"] == "") | (frame["valid_to"] > start))]
    if subset.empty:
        raise ValueError("No documented index membership for this historical interval")
    start_set = _asof(frame, index_name, start)
    end_set = _asof(frame, index_name, (last - timedelta(days=1)).isoformat())
    selected_day = date.fromisoformat(as_of) if as_of else first
    if selected_day < first or selected_day >= last:
        raise ValueError("As-of date must be within the selected historical window")
    asof_set = _asof(frame, index_name, selected_day.isoformat())
    if not start_set or not end_set:
        raise ValueError("Membership missing at one or both requested boundary dates")
    symbols = sorted(set(subset["symbol"]))
    selected_frame = subset.sort_values(["valid_from", "symbol"])
    events: list[dict] = []
    for _, row in selected_frame.iterrows():
        if start < row["valid_from"] < stop:
            events.append({"effective_date": row["valid_from"], "symbol": row["symbol"],
                           "action": "added", "source": row["source"],
                           "source_url": row.get("source_url", "")})
        if row["valid_to"] and start < row["valid_to"] < stop:
            events.append({"effective_date": row["valid_to"], "symbol": row["symbol"],
                           "action": "removed", "source": row["source"],
                           "source_url": row.get("source_url", "")})
    events.sort(key=lambda e: (e["effective_date"], e["symbol"], e["action"]))
    # Dhan has a CURRENT cash-equity master, not a delisted-instrument archive.
    # Resolve only exact unambiguous security identifiers. Never guess renames.
    by_name: dict[str, list[dict]] = {}
    for row in instruments or []:
        if row.get("exchange_segment") == "NSE_EQ" and row.get("regular_eq"):
            by_name.setdefault(str(row["symbol"]).casefold(), []).append(row)
    resolved, missing = [], []
    for symbol in symbols:
        candidates = by_name.get(symbol.casefold(), [])
        if len(candidates) != 1:
            missing.append({"symbol": symbol, "reason":
                            "missing_current_dhan_id" if not candidates else "ambiguous_current_dhan_id"})
            continue
        row = dict(candidates[0])
        row["pit_symbol"] = symbol
        windows = selected_frame.loc[selected_frame["symbol"] == symbol]
        row["pit_fetch_from"] = max(first, date.fromisoformat(windows["valid_from"].min())).isoformat()
        ends = [date.fromisoformat(x) for x in windows["valid_to"] if x]
        row["pit_fetch_to"] = min(last, last if any(x == "" for x in windows["valid_to"]) else max(ends)).isoformat()
        resolved.append(row)
    warning = [
        "Membership is a third-party reconstruction of public NSE circulars, not exchange certification.",
        "Only exact Dhan IDs can be downloaded. Historical delisted/renamed stocks remain unresolved.",
    ]
    if first.year < 2018:
        warning.append("Pre-2018 memberships have documented reconstruction gaps.")
    if missing:
        warning.append("The current Dhan master lacks " + str(len(missing)) +
                       " historical symbols. A full survivorship-free price panel cannot be built.")
    return {
        "index_id": mode, "index_name": index_name,
        "from_date": start, "to_date": stop,
        "start_members": sorted(start_set), "end_members": sorted(end_set),
        "asof_date": selected_day.isoformat(), "asof_members": sorted(asof_set),
        "union_members": symbols, "union_count": len(symbols),
        "start_count": len(start_set), "end_count": len(end_set),
        "changes": events, "change_count": len(events),
        "resolved": resolved, "resolved_count": len(resolved),
        "unresolved": missing, "unresolved_count": len(missing),
        "source_commit": meta["source_commit"], "source_sha256": meta["normalized_sha256"],
        "covered_through": meta["covered_through"], "first_date": meta["first_date"],
        "source_url": meta["source_csv"], "official_corrections": meta["official_source_corrections"],
        "warnings": warning,
        "raw_intervals": json.loads(selected_frame[
            ["index_name", "symbol", "valid_from", "valid_to", "source", "source_url"]
        ].to_json(orient="records")),
    }


def monthly_membership(batch: dict, price_dates: pd.DatetimeIndex,
                       downloaded: list[str]) -> pd.DataFrame:
    """Build a complete date × ticker eligibility matrix from PINNED intervals.

    Every downloaded security receives explicit True/False observations at every
    decision month-end. True cannot be inferred from a current stock symbol.
    """
    info = batch.get("historical_index")
    if not info:
        raise ValueError("Batch has no historical membership snapshot")
    intervals = info.get("intervals", [])
    payload = json.dumps(intervals, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(payload).hexdigest() != info.get("intervals_sha256"):
        raise ValueError("Historical membership snapshot was modified")
    if not price_dates.is_monotonic_increasing or price_dates.has_duplicates:
        raise ValueError("Prepared price dates must be ordered and unique")
    known = set(downloaded)
    by_symbol: dict[str, list[dict]] = {}
    for row in intervals:
        by_symbol.setdefault(row["symbol"], []).append(row)
    result = []
    for tick in sorted(known):
        windows = by_symbol.get(tick)
        if not windows:
            raise ValueError("A price ticker is absent from the original index membership record: " + tick)
        for dt in price_dates:
            mark = dt.date().isoformat()
            eligible = any(r["valid_from"] <= mark and (not r["valid_to"] or r["valid_to"] > mark)
                           for r in windows)
            result.append({"date": mark, "ticker": tick, "eligible": bool(eligible)})
    return pd.DataFrame(result, columns=["date", "ticker", "eligible"])


def pin_selection(plan: dict) -> dict:
    intervals = plan["raw_intervals"]
    payload = json.dumps(intervals, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "index_id": plan["index_id"], "index_name": plan["index_name"],
        "source_commit": plan["source_commit"], "source_sha256": plan["source_sha256"],
        "covered_through": plan["covered_through"], "source_url": plan["source_url"],
        "unresolved": plan["unresolved"], "union_members": plan["union_members"],
        "intervals": intervals, "intervals_sha256": hashlib.sha256(payload).hexdigest(),
        "official_corrections": plan["official_corrections"],
        "warnings": plan["warnings"],
    }
