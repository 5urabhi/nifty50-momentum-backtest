"""Model-aware sample audits and user-approved, read-only Dhan backfills."""
from __future__ import annotations

from datetime import date, timedelta
import math
import pandas as pd

from index_research.data import read_matrix
from . import (dhan_workspace, gbm_calibration, stochastic_calibration, option_market,
               model_registry, service, shared_market_data, single_series_completion)

EXTRA_FRACTION = 0.20
MAX_AUTO_ASSETS = 18
MAX_BACKFILL_YEARS = 15

def recommend_next_action(plan: dict) -> dict:
    """One evidence-safe next step from the model's real readiness result."""
    mode = str(plan.get("mode", ""))
    runnable = bool(plan.get("runnable"))
    remaining = plan.get("missing_to_target")
    if mode not in {"historical", "market"}:
        return {"kind": "run", "label": "Run mathematical model",
                "detail": "Uses explicitly assumed inputs; no observed prices are required."}
    if mode == "market":
        if runnable:
            return {"kind": "run", "label": "Run with selected original quote",
                    "detail": "Option valuation is calculated from a saved bid/ask snapshot."}
        return {"kind": "option_quotes", "label": "Fetch or import original option quotes",
                "detail": "Dhan option-chain capture is read-only; an authorized CSV import is also available. "
                          "A current snapshot is not historical option-chain data."}
    if plan.get("status") == "select_ticker":
        return {"kind": "select_stock", "label": "Choose a stock (including incomplete history)",
                "detail": "After choosing a named instrument, QuantLab checks its exact returns and +20% target."}
    if plan.get("status") == "select_dataset":
        return {"kind": "select_dataset", "label": "Choose an observed dataset",
                "detail": "Choose saved market observations before requesting an extension."}
    if plan.get("can_download") and isinstance(remaining, (int, float)) and remaining > 0:
        return {"kind": "download", "label": "Get missing Dhan history (+20%)",
                "detail": "Reuses SHA-checked local candles and requests only uncovered windows. "
                          "Insufficient vendor history remains incomplete."}
    if runnable:
        return {"kind": "run", "label": "Run model with available evidence",
                "detail": ("Minimum observations are met; a larger validation buffer is preferred."
                           if isinstance(remaining, (int, float)) and remaining > 0
                           else "Required observed inputs are available for this calculation.")}
    return {"kind": "data_library", "label": "Resolve missing source in Data Library",
            "detail": str(plan.get("download_explanation") or plan.get("message")
                          or "This requirement cannot be completed automatically.")}



def requirement(model_id: str, params: dict | None = None) -> dict:
    config=dict(params or {})
    # Inspect readiness before the user has selected a single stock. Runtime
    # execution still validates the actual ticker and never auto-chooses one.
    if model_id in {"ou_fit","merton_fit","heston_proxy"} and (
            config.get("target","stock")=="stock" and not config.get("ticker")):
        config["ticker"]="SELECTION_PENDING"
    settings = model_registry.validate_parameters(model_id, config)
    spec = model_registry.CATALOG[model_id]
    minimum = int(spec["min_observations"])
    if model_id == "rolling_vol":
        # Walk-forward needs training observations PLUS meaningful out-of-sample diagnostics.
        minimum = max(minimum, int(settings["train_window"]) + 30)
    target = math.ceil(minimum * (1 + EXTRA_FRACTION))
    return {"model_id": model_id, "mode": spec["mode"], "min_returns": minimum,
            "buffer_fraction": EXTRA_FRACTION, "buffer_returns": target - minimum,
            "target_returns": target, "assets_requested": int(settings.get("assets", 8)),
            "frequency": "observed returns"}


def _observed(dataset_id: str, assets: int, required: int) -> dict:
    folder, record = service.dataset_path(dataset_id)
    source = "daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
    if not record.get("has_prices"):
        return {"has_prices": False, "common_returns": 0,
                "frequency": None, "assets_found": 0, "selected_assets": []}
    prices = read_matrix(folder / source, positive=True)
    returns = prices.pct_change(fill_method=None).replace([float("inf"), float("-inf")], float("nan"))
    ordered = sorted(returns.columns, key=lambda x: (-int(returns[x].notna().sum()), x))
    # Select the requested number, without silently dropping illiquid members.
    selection = ordered[:assets]
    common = returns[selection].dropna() if selection else returns.iloc[0:0]
    return {"has_prices": True, "frequency": "daily" if source == "daily_prices.csv" else "monthly",
            "price_dates": len(prices), "assets_found": len(ordered),
            "assets_with_required_history": int((returns.notna().sum() >= required).sum()),
            "selected_assets": selection, "common_returns": len(common),
            "oldest_date": prices.index.min().date().isoformat(),
            "latest_date": prices.index.max().date().isoformat(),
            "source": source}


def _mapping(dataset_id: str, selected_assets: list[str]) -> tuple[list[dict], str | None]:
    folder, record = service.dataset_path(dataset_id)
    if record["kind"] != "dhan":
        return [], "Automatic extension requires a Dhan dataset with instrument mappings."
    if dataset_id == shared_market_data.SHARED_ID:
        meta_path = folder / "SHARED_MARKET_PROVENANCE.json"
        field = "columns"
    else:
        meta_path = folder / "DHAN_BATCH_PROVENANCE.json"
        field = "columns"
    if not meta_path.is_file() or meta_path.is_symlink():
        return [], "Instrument-to-Dhan identity provenance is not available."
    import json
    metadata = json.loads(meta_path.read_text())
    mappings = {row["column"]: row for row in metadata.get(field, [])}
    try:
        catalog = {row["id"]: row for row in dhan_workspace.catalog()}
    except (FileNotFoundError, ValueError):
        return [], "Refresh the Dhan instrument master before requesting more history."
    result = []
    unresolved = []
    for column in selected_assets:
        row = mappings.get(column)
        if not row:
            unresolved.append(column)
            continue
        key = f"{row['exchange_segment']}:{row['security_id']}"
        item = catalog.get(key)
        if item is None:
            unresolved.append(column)
        else:
            result.append(item)
    if unresolved:
        return [], "Current Dhan catalog cannot safely resolve: " + ", ".join(unresolved[:6])
    return result, None


def inspect(model_id: str, dataset_id: str | None, params: dict | None = None) -> dict:
    req = requirement(model_id, params)
    if req["mode"] == "market":
        available=option_market.inspect(
            dataset_id, str((params or {}).get("quote","")))
        return {**req, **available, "assets_requested":1,
                "missing_minimum":0,"missing_to_target":0}
    if req["mode"] != "historical":
        return {**req, "status": "not_applicable", "runnable": True,
                "message": "This model does not require observed market data.",
                "can_download": False}
    if model_id in single_series_completion.SINGLE:
        return single_series_completion.inspect(model_id, dataset_id, params or {}, req)
    if not dataset_id:
        return {**req, "status": "select_dataset", "runnable": False,
                "message": "Select a historical dataset to inspect its coverage.",
                "can_download": False}
    observed = _observed(dataset_id, req["assets_requested"], req["min_returns"])
    found = observed["common_returns"]
    missing_min = max(0, req["min_returns"] - found)
    missing_target = max(0, req["target_returns"] - found)
    has_assets = observed["assets_found"] >= req["assets_requested"]
    runnable = observed["has_prices"] and has_assets and missing_min == 0
    status = "ready_with_buffer" if runnable and missing_target == 0 else (
        "ready_minimum" if runnable else "insufficient")
    mapped, reason = _mapping(dataset_id, observed["selected_assets"]) if observed["has_prices"] else ([], "Price data unavailable.")
    if len(mapped) != req["assets_requested"] and reason is None:
        reason = "The selected dataset lacks the requested number of mapped Dhan stocks."
    # Estimate a date window conservatively; the broker and NSE calendar decide
    # actual sessions. Never claim estimated sessions as observed returns.
    end = date.today() + timedelta(days=1)
    latest = observed.get("latest_date")
    if latest:
        end = max(end, date.fromisoformat(latest) + timedelta(days=1))
    desired_sessions = req["target_returns"] + 1
    lookback_days = math.ceil(desired_sessions * 7 / 5 * 1.20) + 18
    oldest = observed.get("oldest_date")
    start = end - timedelta(days=lookback_days)
    if oldest:
        # Expand backwards when the existing window is shorter than required.
        start = min(start, date.fromisoformat(oldest) - timedelta(
            days=math.ceil(missing_target * 7 / 5 * 1.25) + 15))
    floor = date.today() - timedelta(days=365 * MAX_BACKFILL_YEARS)
    start = max(start, floor)
    can_download = bool(mapped) and missing_target > 0 and req["assets_requested"] <= MAX_AUTO_ASSETS
    if observed.get("frequency") == "monthly":
        can_download = False
        reason = "Select a daily Dhan dataset for automatic historical extension; monthly-only inputs need a separately audited reconstruction."
    if req["assets_requested"] > MAX_AUTO_ASSETS:
        reason = f"Automatic extension is limited to {MAX_AUTO_ASSETS} mapped securities."
    if not reason and can_download:
        reason = "Only absent Dhan date windows are requested; cache is reused first."
    # Conservative scale preview, NOT a vendor billing quote or proof of
    # exchange sessions. The uncovered-span planner remains the authority.
    potential_weekdays = int(len(pd.bdate_range(start, end - timedelta(days=1)))) if start<end else 0
    count_upper_bound = potential_weekdays * len(mapped)
    cached_days = 0
    missing_windows = 0
    estimated_vendor_daily_windows = 0
    missing_calendar_days = 0
    try:
        for instrument in mapped:
            spans = [(a.isoformat(), b.isoformat()) for _,a,b
                     in shared_market_data.cached_spans(instrument)]
            gaps = dhan_workspace._uncovered(start, end, spans)
            days = sum((b-a).days for a,b in gaps)
            cached_days += max(0,(end-start).days-days)
            missing_calendar_days += days
            missing_windows += len(gaps)
            estimated_vendor_daily_windows += sum(math.ceil((b-a).days/365) for a,b in gaps)
    except (ValueError,OSError) as exc:
        # A corrupt SHA manifest is a blocker, not permission to redownload
        # the whole history or silently erase conflicting cached records.
        can_download = False
        reason = "Cached market history failed provenance verification: " + str(exc)[:100]
    return {**req, **observed, "dataset_id": dataset_id, "status": status,
            "estimated_calendar_weekdays": potential_weekdays,
            "estimated_max_instrument_day_requests": count_upper_bound,
            "cached_instrument_calendar_days": cached_days,
            "missing_instrument_calendar_days": missing_calendar_days,
            "missing_uncovered_windows": missing_windows,
            "estimated_vendor_daily_requests": estimated_vendor_daily_windows,
            "request_scope_note": "Estimated vendor daily requests use SHA-verified cached "
                                  "instrument/date coverage and Dhan's 365-calendar-day chunks. "
                                  "Actual exchange-session observations, NSE holidays and "
                                  "provider limits may differ; no covered window is refetched.",
            "runnable": runnable, "missing_minimum": missing_min,
            "missing_to_target": missing_target, "assets_available": len(mapped),
            "assets_missing": max(0, req["assets_requested"] - observed["assets_found"]),
            "can_download": can_download, "download_explanation": reason,
            "suggested_start": start.isoformat(), "suggested_end_exclusive": end.isoformat(),
            "message": (
                f"{found} aligned observed returns; {req['min_returns']} minimum, "
                f"{req['target_returns']} preferred (+20%)."
            )}


def execute(model_id: str, dataset_id: str, params: dict | None = None,
            *, progress=None) -> dict:
    """Run only after a distinct UI-confirmed POST; append to existing master.

    Cached OHLCV is imported even if no network call is necessary. Dhan's
    existing SHA manifests and uncovered-window planner prevent refetching
    dates previously downloaded for NIFTY, BANK NIFTY or any other universe.
    """
    if model_id in single_series_completion.SINGLE:
        return single_series_completion.execute(
            model_id, dataset_id, params or {}, progress=progress)
    if progress:
        progress(2, "Checking verified mappings and existing Dhan market history")
    plan = inspect(model_id, dataset_id, params)
    if plan["mode"] != "historical":
        raise ValueError("Selected model has no empirical price-data requirement")
    if not plan.get("can_download"):
        raise ValueError(plan.get("download_explanation") or "No additional Dhan download is available")
    from . import dhan_auth
    rows, reason = _mapping(dataset_id, plan["selected_assets"])
    if reason:
        raise ValueError(reason)
    events = []
    # Explicitly prefer the canonical shared set; existing batch-specific
    # datasets remain immutable snapshots and PIT members remain separate.
    for i, row in enumerate(rows):
        if progress:
            progress(5 + 25 * i / max(1, len(rows)),
                     "Reusing cached candles for instrument " + str(i + 1) + "/" + str(len(rows)))
        reused = shared_market_data.reuse_cached(row)
        events.append({"instrument_id": row["id"], "cache_rows_added": reused["rows_appended"]})
    try:
        before = inspect(model_id, shared_market_data.SHARED_ID, params)
    except ValueError:
        before = {"status": "insufficient", "runnable": False}
    if before["status"] == "ready_with_buffer":
        if progress:
            progress(100, "Existing cached observations already satisfy the preferred buffer")
        return {"status": "ready", "dataset_id": shared_market_data.SHARED_ID,
                "message": "Shared dataset already has sufficient observations.",
                "before": plan, "after": before, "instruments": events}
    # Consider covered dates at ALL cached resolutions (daily and intraday).
    # That is what makes a 1-minute NIFTY download reusable for a daily
    # BANK NIFTY research model without another vendor request.
    start, stop = date.fromisoformat(plan["suggested_start"]), date.fromisoformat(plan["suggested_end_exclusive"])
    uncovered = {}
    for row in rows:
        spans = [(a.isoformat(), b.isoformat()) for _, a, b in shared_market_data.cached_spans(row)]
        uncovered[row["id"]] = dhan_workspace._uncovered(start, stop, spans)
    if any(uncovered.values()):
        state = dhan_auth.check_profile()
        if not state["ok"]:
            raise ValueError(state["message"])
    total_windows = sum(len(windows) for windows in uncovered.values())
    finished_windows = 0
    for row, event in zip(rows, events):
        if progress:
            progress(30 + 58 * finished_windows / max(1, total_windows),
                     "Checking uncovered windows for " + row["id"])
        event["missing_windows"] = len(uncovered[row["id"]])
        event["rows_added"] = 0
        for first, last in uncovered[row["id"]]:
            if progress:
                progress(30 + 58 * finished_windows / max(1, total_windows),
                         "Requesting missing Dhan window " + str(finished_windows + 1) + "/" + str(total_windows))
            downloaded = dhan_workspace._fetch_history(
                row, first.isoformat(), last.isoformat(), None)
            event["rows_added"] += downloaded["rows_added"]
            finished_windows += 1
        if progress:
            progress(30 + 58 * finished_windows / max(1, total_windows),
                     "Appending verified observations into the shared store")
        imported = shared_market_data.reuse_cached(row)
        event["shared_rows_appended"] = imported["rows_appended"]
    if progress:
        progress(93, "Rechecking actual common returns and the preferred buffer")
    after = inspect(model_id, shared_market_data.SHARED_ID, params)
    if progress:
        progress(99, "Saving source-bound readiness after incremental download")
    return {"status": "ready" if after["runnable"] else "incomplete",
            "dataset_id": shared_market_data.SHARED_ID, "before": plan,
            "after": after, "instruments": events,
            "message": ("Shared dataset updated; model minimum satisfied." if after["runnable"]
                        else "History updated, but available observed sessions are still insufficient. "
                             "No missing observations were fabricated."),
            "warning": "An adequate sample length does not imply total-return or PIT investability."}
