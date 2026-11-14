"""Model-specific, read-only input suggestions for QuantLab.

This module recommends *which observed series could be selected*, but never
chooses a security on the user's behalf and never submits a model run.
It checks the same non-imputation, continuity and minimum-observation
requirements as the historical stochastic fitters. Preflight is not a
guarantee of numerical convergence, stationarity or forecast validity.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from index_research.data import read_matrix, read_returns
from . import service

MINIMUM = {"gbm_fit": 10, "ou_fit": 90, "merton_fit": 120,
           "heston_proxy": 252}
DAILY_ONLY = frozenset({"ou_fit", "heston_proxy"})


def inspect_stock(series: pd.Series, frequency: str, minimum: int) -> dict:
    """Measure one stock's contiguous observed history without imputation.

    Wide historical panels have different first and last trading dates per
    stock. Leading/trailing unavailable dates are not a data quality error,
    but internal holes cannot be silently filled or skipped.
    """
    first, last = series.first_valid_index(), series.last_valid_index()
    if first is None or last is None:
        return {"returns": 0, "runnable": False, "extendable": True,
                "reason": "No original closes for this stock",
                "missing_minimum": minimum,
                "missing_to_target": math.ceil(minimum*1.2),
                "from_date": None, "to_date": None}
    observed = series.loc[first:last]
    n = max(0, len(observed)-1)
    target = math.ceil(minimum * 1.2)
    result = {"returns": n, "runnable": False, "extendable": False,
              "reason": "", "missing_minimum": max(0, minimum-n),
              "missing_to_target": max(0, target-n),
              "from_date": str(pd.Timestamp(first).date()),
              "to_date": str(pd.Timestamp(last).date()),
              "available_closes": int(observed.notna().sum()),
              "raw_panel_dates": len(series)}
    if observed.isna().any():
        result["reason"] = "Missing price observations inside the stock's available date range; no forward fill"
        return result
    values = observed.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        result["reason"] = "Nonfinite or nonpositive historical closes"
        return result
    dates = observed.index
    if dates.has_duplicates or not dates.is_monotonic_increasing:
        result["reason"] = "Dates must be unique and chronologically ordered"
        return result
    if frequency == "monthly":
        months = dates.to_period("M")
        if not months.is_unique or len(pd.period_range(months[0], months[-1])) != len(dates):
            result["reason"] = "One or more calendar months are absent or repeated"
            return result
    elif frequency == "daily":
        if (pd.Series(dates).diff().dt.days.dropna() > 10).any():
            result["reason"] = "Trading history has a gap exceeding 10 calendar days"
            return result
    else:
        result["reason"] = "Unsupported historical price frequency"
        return result
    result["extendable"] = True
    if n < minimum:
        result["reason"] = (
            f"{n} actual returns; needs {minimum-n} for minimum and "
            f"{target-n} to meet preferred +20% target")
        return result
    if n < 2:
        result["reason"] = "At least two nonconstant observed returns are required"
        return result
    log_returns = np.diff(np.log(values))
    if not np.isfinite(log_returns).all() or np.std(log_returns, ddof=1) <= 1e-10:
        result["reason"] = "Constant/invalid log returns cannot calibrate volatility"
        result["extendable"] = False
        return result
    result.update(runnable=True, reason=f"{n} complete {frequency} returns, no imputation")
    return result


def rank_stocks(prices: pd.DataFrame | None, frequency: str,
                minimum: int, *, daily_only: bool = False) -> list[dict]:
    """Rank original named securities by exact fit eligibility and sample depth.

    No substitution takes place: the selected ticker remains an explicit user
    input. Limit the recommendation display to 300 entries, with eligible
    stocks always first.
    """
    if prices is None or prices.empty:
        return []
    if daily_only and frequency != "daily":
        return [{"ticker": str(col), "returns": max(0, len(prices)-1),
                 "runnable": False, "reason": "Daily stock prices required"}
                for col in list(prices.columns)[:300]]
    rows = []
    for name in prices.columns:
        status = inspect_stock(prices[name], frequency, minimum)
        rows.append({"ticker": str(name), **status})
    rows.sort(key=lambda row: (not row["runnable"], not row.get("extendable", False),
                               -row["returns"], row["ticker"]))
    return rows[:300]


def tri_source_info(folder, minimum: int) -> dict:
    """Validate original index total-return metadata and monthly chronology."""
    benchmark = folder / "benchmark.csv"
    proof = folder / "BENCHMARK_SOURCE.json"
    if (not benchmark.is_file() or not proof.is_file()
            or benchmark.is_symlink() or proof.is_symlink()):
        return {"runnable": False, "returns": 0,
                "reason": "Original source-linked NIFTY TRI is not imported"}
    try:
        meta = json.loads(proof.read_text(encoding="utf-8"))
        if meta.get("return_convention") not in {"gross_total_return", "net_total_return"}:
            return {"runnable": False, "returns": 0,
                    "reason": "Benchmark is not declared dividend-inclusive TRI"}
        series = read_returns(benchmark)
        n = len(series)
        if n < minimum:
            return {"runnable": False, "returns": n,
                    "reason": f"Needs {minimum} TRI months; found {n}"}
        months = series.index.to_period("M")
        if (not months.is_unique or not series.index.is_monotonic_increasing
                or len(pd.period_range(months[0], months[-1])) != n
                or not np.isfinite(series.to_numpy(dtype=float)).all()
                or (series <= -1).any()):
            return {"runnable": False, "returns": n,
                    "reason": "TRI is missing months or has invalid returns"}
        return {"runnable": True, "returns": n,
                "reason": f"{n} monthly source-linked NIFTY TRI returns",
                "index_name": str(meta.get("index_name") or "NIFTY TRI")}
    except (ValueError, OSError, KeyError, TypeError):
        return {"runnable": False, "returns": 0,
                "reason": "Source-linked TRI file cannot be read or validated"}


def inspect(dataset_id: str, model_id: str) -> dict:
    if model_id not in MINIMUM:
        raise ValueError("Stock recommendations apply only to historical single-series models")
    folder, record = service.dataset_path(dataset_id)
    file = "daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
    frequency = "daily" if file == "daily_prices.csv" else "monthly"
    prices = None
    if record.get("has_prices") and (folder / file).is_file():
        prices = read_matrix(folder / file, positive=True)
    candidates = rank_stocks(prices, frequency, MINIMUM[model_id],
                             daily_only=model_id in DAILY_ONLY)
    # Canonical shared Dhan columns use exchange segment + security ID.
    # Preserve exact identifiers for execution but show readable display
    # symbols in the picker; do not alias different instruments together.
    label_path = (folder / "SHARED_MARKET_PROVENANCE.json" if
                  dataset_id == "dhan_shared" else
                  folder / "DHAN_BATCH_PROVENANCE.json")
    if label_path.is_file() and not label_path.is_symlink():
        try:
            info = json.loads(label_path.read_text(encoding="utf-8"))
            labels = {str(row["column"]): str(row.get("display_symbol") or
                      row["column"]) for row in info.get("columns", [])}
            for candidate in candidates:
                candidate["display_name"] = labels.get(
                    candidate["ticker"], candidate["ticker"])
        except (ValueError, OSError, KeyError, TypeError):
            for candidate in candidates:
                candidate["display_name"] = candidate["ticker"]
    else:
        for candidate in candidates:
            candidate["display_name"] = candidate["ticker"]
    valid = [item for item in candidates if item["runnable"]]
    suggested = next((item for item in candidates if item.get("extendable")), None)
    tri = tri_source_info(folder, MINIMUM[model_id]) if model_id in {
        "gbm_fit", "merton_fit"} else {
        "runnable": False, "returns": 0,
        "reason": "This model requires daily stock volatility observations"}
    synthetic = record.get("kind") == "synthetic" or (folder / "DO_NOT_CITE.txt").exists()
    return {
        "dataset_id": dataset_id, "dataset_label": record.get("label", dataset_id),
        "model_id": model_id, "frequency": frequency, "minimum": MINIMUM[model_id],
        "preferred_with_buffer": math.ceil(MINIMUM[model_id] * 1.20),
        "synthetic_fixture": bool(synthetic),
        "source_file": file if prices is not None else None,
        "eligible_count": len(valid), "candidates": candidates, "tri": tri,
        "candidate_count": len(candidates),
        "auto_download_supported": record.get("kind") == "dhan"
                                   and record.get("has_daily_prices", False),
        "recommended_ticker": suggested["ticker"] if suggested else None,
        "extendable_count": sum(bool(item.get("extendable")) for item in candidates),
        "selection_is_explicit": True, "no_missing_prices_imputed": True,
        "help": ("Select an eligible or incomplete named ticker. If it lacks data, "
                 "use Get missing data (+20%) to reuse local Dhan candles and download "
                 "uncovered windows. No ticker is chosen silently; no prices are fabricated."),
    }
