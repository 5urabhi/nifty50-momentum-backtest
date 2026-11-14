"""One-click completion of observed stock history for single-series research.

This module NEVER fabricates past candles. It preserves batch snapshots,
reuses the canonical identity-keyed Dhan cache, downloads uncovered windows
only after the user confirms, and returns the correct destination ticker
for the shared research dataset. Dhan API access and exchange availability
determine whether the preferred +20% observation buffer can be reached.
"""
from __future__ import annotations

from datetime import date, timedelta
import math

import pandas as pd

from index_research.data import read_matrix
from . import dhan_workspace, model_input_selector, service, shared_market_data

SINGLE = frozenset({"gbm_fit", "ou_fit", "merton_fit", "heston_proxy"})
MAX_BACKFILL_YEARS = 15


def inspect(model_id: str, dataset_id: str | None,
            params: dict, req: dict) -> dict:
    if model_id not in SINGLE:
        raise ValueError("Single-series completion is unavailable for this model")
    result = {**req, "assets_requested": 1, "can_download": False,
              "dataset_id": dataset_id, "selected_assets": []}
    if not dataset_id:
        return {**result, "status": "select_dataset", "runnable": False,
                "common_returns": None, "missing_minimum": None,
                "missing_to_target": None,
                "message": "Choose a saved observed-data source to see exact requirements."}
    folder, record = service.dataset_path(dataset_id)
    target = str(params.get("target") or
                 ("benchmark_tri" if model_id == "gbm_fit" else "stock"))
    ticker = str(params.get("ticker") or "").strip()
    if target == "benchmark_tri":
        # NIFTY spot/index prices from Dhan are NOT an original TRI series.
        from . import gbm_calibration, stochastic_calibration
        status = (gbm_calibration.inspect(dataset_id, target, "") if
                  model_id == "gbm_fit" else
                  stochastic_calibration.inspect(dataset_id, model_id,
                                                  {**params, "target": target, "ticker": ""}))
        count = status.get("common_returns", 0)
        return {**result, **status, "assets_requested": 1,
                "missing_minimum": max(0,req["min_returns"]-count),
                "missing_to_target": max(0,req["target_returns"]-count),
                "can_download": False,
                "download_explanation": ("Dhan spot candles cannot create an original "
                    "dividend-inclusive NIFTY TRI. Add authorized TRI levels in Data Library.")}

    source = "daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
    frequency = "daily" if source == "daily_prices.csv" else "monthly"
    has_prices = bool(record.get("has_prices")) and (folder/source).is_file()
    if not has_prices:
        return {**result, "status": "missing_prices", "runnable": False,
                "common_returns": None, "missing_minimum": None,
                "missing_to_target": None,
                "download_explanation": "Choose or prepare an observed Dhan price dataset.",
                "message": "This dataset has no prepared stock prices."}
    prices = read_matrix(folder / source, positive=True)
    if model_id in model_input_selector.DAILY_ONLY and frequency != "daily":
        return {**result, "status": "needs_daily", "runnable": False,
                "common_returns": None, "missing_minimum": None,
                "missing_to_target": None,
                "download_explanation": "Select a Dhan dataset with original daily prices.",
                "message": "This volatility model needs daily stock closes, not monthly prices."}
    if not ticker:
        candidates = model_input_selector.rank_stocks(
            prices, frequency, req["min_returns"],
            daily_only=model_id in model_input_selector.DAILY_ONLY)
        suggested = next((item for item in candidates if item.get("extendable")), None)
        return {**result, "status": "select_ticker", "runnable": False,
                "common_returns": None, "missing_minimum": None,
                "missing_to_target": None, "available_price_dates": len(prices),
                "suggested_ticker": suggested["ticker"] if suggested else None,
                "assets_found": len(prices.columns),
                "download_explanation": "Choose a stock below, then click Get missing data (+20%).",
                "message": (f"{len(prices)} source price dates across "
                            f"{len(prices.columns)} stocks. No stock is selected yet; "
                            "0 returns would be misleading. Pick a stock below "
                            "to see its exact shortfall and one-click completion.")}
    if ticker not in prices.columns:
        return {**result, "status": "missing_ticker", "runnable": False,
                "common_returns": None, "missing_minimum": None,
                "missing_to_target": None,
                "message": "Selected stock is not present in this dataset; choose a listed ticker."}

    evidence = model_input_selector.inspect_stock(
        prices[ticker], frequency, req["min_returns"])
    count = evidence["returns"]
    minimum_missing = evidence["missing_minimum"]
    target_missing = evidence["missing_to_target"]
    runnable = bool(evidence["runnable"])
    status = ("ready_with_buffer" if runnable and target_missing == 0
              else "ready_minimum" if runnable else "insufficient")
    details = {
        **result, "status": status, "runnable": runnable,
        "selected_assets": [ticker], "common_returns": count,
        "available_price_dates": len(prices),
        "source_file": source, "frequency": frequency,
        "missing_minimum": minimum_missing, "missing_to_target": target_missing,
        "assets_found": 1, "selected_ticker": ticker,
        "observed_from": evidence["from_date"],
        "observed_through": evidence["to_date"],
        "message": (f"{ticker}: {count} real {frequency} returns; "
                    f"{req['min_returns']} minimum ({minimum_missing} missing), "
                    f"{req['target_returns']} preferred with +20% "
                    f"({target_missing} missing). "
                    + ("" if runnable or evidence.get("extendable") else
                       "Data quality: " + evidence["reason"] + ". ")),
    }
    if target_missing == 0 and runnable:
        return {**details, "download_explanation": "Preferred +20% target already satisfied."}
    if record.get("kind") != "dhan":
        return {**details, "download_explanation":
                "Automatic Dhan append requires an original Dhan dataset and a verified instrument ID. "
                "Upload a longer original source or use Data Library."}
    if frequency != "daily":
        return {**details, "download_explanation":
                "Automatic extension uses Dhan daily candles. Select a daily Dhan dataset."}
    if not evidence.get("extendable", False):
        return {**details, "download_explanation":
                "This stock has missing/invalid internal observations. "
                "New earlier/later history does not repair a broken source window. "
                "Inspect the source in Data Library."}
    # Delayed import prevents circular imports: model_data_manager calls us.
    from . import model_data_manager
    mapped, reason = model_data_manager._mapping(dataset_id, [ticker])
    if reason or len(mapped) != 1:
        return {**details, "download_explanation": reason or
                "No uniquely mapped Dhan instrument for this source ticker."}
    row = mapped[0]
    shared_ticker = row["exchange_segment"] + "_" + row["security_id"]
    today = date.today()
    # Account for weekends and holidays conservatively; only sessions
    # actually returned by the provider count. Append before earliest date.
    # Do NOT attempt to download future sessions.
    end = today + timedelta(days=1)
    desired_days = math.ceil((req["target_returns"] + 1) * 7 / 5 * 1.28) + 18
    start = end - timedelta(days=desired_days)
    if evidence["from_date"]:
        oldest = date.fromisoformat(evidence["from_date"])
        backward_days = math.ceil(target_missing * 7 / 5 * 1.40) + 20
        start = min(start, oldest - timedelta(days=backward_days))
    start = max(start, today - timedelta(days=365 * MAX_BACKFILL_YEARS))
    if start >= end:
        return {**details, "download_explanation": "Requested history is outside allowed dates."}

    cached_days, uncovered, requests = 0, 0, 0
    try:
        spans = [(a.isoformat(), b.isoformat()) for _,a,b
                 in shared_market_data.cached_spans(row)]
        gaps = dhan_workspace._uncovered(start, end, spans)
        uncovered = len(gaps)
        gaps_days = sum((last-first).days for first,last in gaps)
        cached_days = max(0, (end-start).days-gaps_days)
        requests = sum(math.ceil((last-first).days/365) for first,last in gaps)
    except (ValueError,OSError) as exc:
        return {**details, "download_explanation":
                "Cached history integrity check failed: "+str(exc)[:120]}

    return {**details, "can_download": True, "shared_ticker": shared_ticker,
            "suggested_start": start.isoformat(),
            "suggested_end_exclusive": end.isoformat(),
            "cached_instrument_calendar_days": cached_days,
            "missing_uncovered_windows": uncovered,
            "estimated_vendor_daily_requests": requests,
            "estimated_calendar_weekdays": len(pd.bdate_range(start,end-timedelta(days=1))),
            "estimated_max_instrument_day_requests": len(pd.bdate_range(start,end-timedelta(days=1))),
            "request_scope_note": "Reuse all SHA-verified Dhan cache first; request only uncovered "
                "windows. Calendar dates are estimated, not promised trading sessions. "
                "Original batch stays unchanged; new observations are appended into the shared dataset.",
            "download_explanation": (
                f"Get {target_missing} more valid returns toward the +20% target for {ticker}. "
                f"Reuse cached history, then make at most approximately {requests} "
                "new Dhan daily API requests. Actual availability is provider-dependent."),
    }


def execute(model_id: str, dataset_id: str, params: dict, *, progress=None) -> dict:
    from . import model_data_manager, dhan_auth
    plan = model_data_manager.inspect(model_id, dataset_id, params)
    if not plan.get("can_download") or model_id not in SINGLE:
        raise ValueError(plan.get("download_explanation") or
                         "Historical single-series download is unavailable.")
    selected = plan["selected_ticker"]
    rows, reason = model_data_manager._mapping(dataset_id, [selected])
    if reason or len(rows) != 1:
        raise ValueError(reason or "Unable to map original ticker to Dhan instrument")
    row = rows[0]
    expected = row["exchange_segment"]+"_"+row["security_id"]
    if plan["shared_ticker"] != expected:
        raise ValueError("Source instrument mapping changed after planning. Recheck the plan.")
    shared_params = {**params, "target": "stock", "ticker": expected}
    def stage(value, message):
        if progress: progress(value, message)
    stage(3, "Reusing SHA-verified historical candles before any network requests")
    cache = shared_market_data.reuse_cached(row)
    after = model_data_manager.inspect(model_id, shared_market_data.SHARED_ID, shared_params)
    events = {"instrument_id": row["id"],
              "cache_rows_added": cache["rows_appended"],
              "downloaded_rows": 0, "windows_downloaded": 0}
    if after["runnable"] and after.get("missing_to_target",1) == 0:
        stage(100, "Preferred +20% target already present in the shared cache")
        return _receipt(model_id, plan, after, selected, expected, events)

    start = date.fromisoformat(plan["suggested_start"])
    end = date.fromisoformat(plan["suggested_end_exclusive"])
    spans = [(a.isoformat(),b.isoformat()) for _,a,b
             in shared_market_data.cached_spans(row)]
    windows = dhan_workspace._uncovered(start, end, spans)
    if windows:
        # Verify only on the local backend, never send credentials to browser.
        state = dhan_auth.check_profile()
        if not state["ok"]:
            raise ValueError(state["message"])
    stage(15, f"{len(windows)} uncovered date windows for {selected}")
    for i,(first,last) in enumerate(windows):
        downloaded = dhan_workspace._fetch_history(
            row, first.isoformat(), last.isoformat(), None)
        events["downloaded_rows"] += downloaded["rows_added"]
        events["windows_downloaded"] += 1
        stage(15+70*(i+1)/max(1,len(windows)),
              f"Saved original {selected} Dhan history, window {i+1}/{len(windows)}")
    stage(90, "Appending new observations to identity-keyed shared research data")
    imported = shared_market_data.reuse_cached(row)
    events["shared_rows_added"] = imported["rows_appended"]
    after = model_data_manager.inspect(model_id, shared_market_data.SHARED_ID, shared_params)
    stage(99, "Rechecking actual model input requirements and +20% target")
    return _receipt(model_id, plan, after, selected, expected, events)


def _receipt(model_id: str, before: dict, after: dict,
             original: str, shared: str, events: dict) -> dict:
    buffer_complete = bool(after.get("runnable") and
                           after.get("missing_to_target") == 0)
    runnable = bool(after.get("runnable"))
    return {
        "status": "ready" if buffer_complete else "minimum_ready" if runnable else "incomplete",
        "model_id": model_id,
        "dataset_id": shared_market_data.SHARED_ID,
        "selected_ticker": shared,
        "original_ticker": original,
        "buffer_complete": buffer_complete,
        "actual_returns": after.get("common_returns"),
        "target_returns": before["target_returns"],
        "missing_to_target": after.get("missing_to_target"),
        "before": before, "after": after,
        "instruments": [events],
        "message": (
            f"{original}: preferred +20% research-history target met; "
            "shared dataset is ready and the selected stock was preserved."
            if buffer_complete else
            f"{original}: model minimum met, but only {after.get('common_returns',0)} of "
            f"{before['target_returns']} preferred returns are available. "
            "More sessions may be unavailable from Dhan; do not invent them."
            if runnable else
            f"{original}: downloaded and prepared available source candles, but "
            "the model still needs additional valid observations. "
            "Inspect the source gaps and provider availability."),
        "warning": "Historical candles are not automatically dividend-reinvested returns, "
                   "nor a guarantee of predictive validity.",
    }
