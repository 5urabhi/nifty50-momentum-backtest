"""Source-aware GBM parameter fitting and strictly chronological diagnostics.

Fitted annual drift/volatility come from the pre-holdout return sequence.
Artificial future or holdout fan paths are always labeled *simulations*.
No Dhan calls, source fabrication, trading, or claims of predictive accuracy.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from index_research import math_models
from index_research.data import read_matrix, read_returns
from . import service

PER_YEAR = {"daily": 252, "monthly": 12}
MIN_RETURNS = 10
HOLDOUT_FRACTION = .20


def _series(dataset_id: str, target: str, ticker: str) -> tuple[pd.Series, pd.Series, dict]:
    if not dataset_id:
        raise ValueError("Choose a saved historical dataset before fitting GBM")
    folder, record = service.dataset_path(dataset_id)
    synthetic = record.get("kind") == "synthetic" or (folder / "DO_NOT_CITE.txt").exists()
    if target == "benchmark_tri":
        file = folder / "benchmark.csv"
        proof = folder / "BENCHMARK_SOURCE.json"
        if not file.is_file() or file.is_symlink() or not proof.is_file() or proof.is_symlink():
            raise ValueError("This dataset lacks source-linked NIFTY TRI returns. "
                             "Import original NIFTY Total Returns Index levels in Data Library first.")
        metadata = json.loads(proof.read_text(encoding="utf-8"))
        if metadata.get("return_convention") not in {"gross_total_return", "net_total_return"}:
            raise ValueError("Benchmark provenance must specify a total-return convention")
        simple = read_returns(file)
        if len(simple) < MIN_RETURNS:
            raise ValueError(f"GBM needs {MIN_RETURNS} observed TRI returns; found {len(simple)}. "
                             "Download older original TRI months.")
        if not simple.index.to_period("M").is_unique or len(
                pd.period_range(simple.index[0].to_period("M"),
                                simple.index[-1].to_period("M"), freq="M")) != len(simple):
            raise ValueError("Benchmark is missing entire calendar months; no gap is filled")
        values = simple.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= -1).any():
            raise ValueError("Invalid benchmark returns; prices cannot be inferred from them")
        # Original normalized TRI level is unknown here. A relative wealth
        # series can be reconstructed exactly from source monthly returns.
        levels = pd.Series(100 * np.cumprod(1 + values), index=simple.index, name="NIFTY TRI wealth")
        log_returns = pd.Series(np.log1p(values), index=simple.index, name="log_return")
        info = {
            "frequency": "monthly", "source_file": "benchmark.csv",
            "assets": [str(metadata.get("index_name") or "NIFTY TRI")],
            "benchmark_kind": metadata.get("return_convention"),
            "selection_rule": "Original archived total-return benchmark, chronological monthly levels",
            "dataset_basis": record.get("basis", ""),
            "source_evidence": "Issuer TRI import metadata supplied, independently unaudited",
            "simulated_paths_are_market_data": False,
            "is_synthetic_fixture": synthetic,
        }
    else:
        if not ticker:
            raise ValueError("Select an exact stock ticker from this dataset")
        source = "daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
        file = folder / source
        if not file.is_file() or file.is_symlink():
            raise ValueError("Selected dataset has no source stock prices")
        prices = read_matrix(file, positive=True)
        if ticker not in prices.columns:
            options = ", ".join(map(str, list(prices.columns)[:8]))
            raise ValueError("Stock ticker " + ticker + " is not present. Available examples: " + options)
        levels_raw = prices[ticker]
        # A canonical Dhan panel is the UNION of all securities' dates.
        # A stock may start later/end earlier than its peers. Trim ONLY its
        # entirely unobserved outer dates; internal holes are never filled.
        first, last = levels_raw.first_valid_index(), levels_raw.last_valid_index()
        if first is None or last is None:
            raise ValueError("Selected stock has no observed prices in this dataset")
        levels_raw = levels_raw.loc[first:last]
        if levels_raw.isna().any() or not np.isfinite(levels_raw.to_numpy(dtype=float)).all():
            raise ValueError("Selected stock has internal missing or invalid prices; no forward fill")
        if len(levels_raw) - 1 < MIN_RETURNS:
            raise ValueError(f"GBM needs {MIN_RETURNS} stock returns; found {len(levels_raw)-1}")
        frequency = "daily" if source == "daily_prices.csv" else "monthly"
        if frequency == "monthly" and (
                not levels_raw.index.to_period("M").is_unique or len(
                    pd.period_range(levels_raw.index[0].to_period("M"),
                                    levels_raw.index[-1].to_period("M"), freq="M")) != len(levels_raw)):
            raise ValueError("Selected stock monthly history has missing whole months")
        if frequency == "daily" and (
                pd.Series(levels_raw.index).diff().dt.days.dropna() > 10).any():
            raise ValueError("Selected stock has a gap exceeding 10 calendar days")
        levels = levels_raw.iloc[1:].copy()
        log_returns = pd.Series(np.diff(np.log(levels_raw.to_numpy(dtype=float))),
                                index=levels.index, name="log_return")
        info = {
            "frequency": frequency, "source_file": source, "assets": [ticker],
            "benchmark_kind": record.get("benchmark_kind", "not_required_for_single_stock_fit"),
            "selection_rule": "Exact chosen ticker only; no availability-driven security substitution",
            "dataset_basis": record.get("basis", ""),
            "source_evidence": "Dhan/user stock closes; dividends and delisting proceeds may be absent",
            "simulated_paths_are_market_data": False,
            "is_synthetic_fixture": synthetic,
        }
    if not log_returns.index.is_monotonic_increasing or log_returns.index.has_duplicates:
        raise ValueError("Observed source dates must be unique and ascending")
    if (not np.isfinite(log_returns.to_numpy(dtype=float)).all()
            or len(log_returns) < MIN_RETURNS):
        raise ValueError("Not enough finite, observed log returns to fit GBM")
    info.update({
        "dataset_id": dataset_id, "dataset_label": record.get("label", dataset_id),
        "dataset_kind": record.get("kind", "unverified"),
        "periods_per_year": PER_YEAR[info["frequency"]],
        "observations": len(log_returns),
        "from_date": log_returns.index[0].date().isoformat(),
        "to_date": log_returns.index[-1].date().isoformat(),
        "missing_prices_forward_filled": False,
    })
    return levels, log_returns, info


def inspect(dataset_id: str | None, target: str = "benchmark_tri",
            ticker: str = "") -> dict:
    if not dataset_id:
        return {"status": "select_dataset", "runnable": False,
                "message": "Choose a research dataset.", "can_download": False,
                "common_returns": 0, "assets_found": 0}
    try:
        _, returns, info = _series(dataset_id, target, ticker)
        n = len(returns)
        return {"status": "ready_with_buffer" if n >= 12 else "ready_minimum",
                "runnable": True, "common_returns": n, "assets_found": 1,
                "selected_assets": info["assets"],
                "message": ("Historical calibration available: " + str(n)
                            + " original returns. Train on the first 80%, "
                              "inspect the last 20% without fitting. "
                            + ("SHORT SAMPLE: estimates are unstable." if n < 24 else
                               "Estimates remain model-conditional.")),
                "can_download": False,
                "download_explanation": "Use Data Library to extend the original stock or TRI source.",
                "frequency": info["frequency"]}
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"status": "insufficient", "runnable": False, "common_returns": 0,
                "assets_found": 0, "message": str(e), "can_download": False,
                "download_explanation": str(e)}


def fit(dataset_id: str, params: dict) -> dict:
    """Method-of-moments GBM fit with one untouched (within the run) last-20% evaluation."""
    from .model_lab import fan, line, metric, xy
    levels, returns, source = _series(dataset_id, params["target"], params["ticker"])
    x = returns.to_numpy(dtype=float)
    n = len(x)
    n_test = max(2, math.ceil(n * HOLDOUT_FRACTION))
    n_train = n - n_test
    if n_train < 8:
        raise ValueError("Not enough independent training returns after a 20% test split")
    training = x[:n_train]
    heldout = x[n_train:]
    annual = source["periods_per_year"]
    mean_log = float(np.mean(training))
    sample_sigma = float(np.std(training, ddof=1))
    if not math.isfinite(sample_sigma) or sample_sigma <= 1e-10:
        raise ValueError("Training log returns have zero variance; GBM calibration is undefined")
    sigma = sample_sigma * math.sqrt(annual)
    mu = mean_log * annual + .5 * sigma ** 2
    if not all(math.isfinite(v) for v in (mu, sigma)):
        raise ValueError("Calibrated GBM parameters are not finite")
    last_train_level = float(levels.iloc[n_train-1])
    # Fitted ONLY on pre-holdout returns. Seeded fan does not train on test outcomes.
    hold_paths = math_models.simulate_gbm(
        last_train_level, mu, sigma, n_test / annual,
        n_test, int(params["paths"]), int(params["seed"]))
    if not np.isfinite(hold_paths).all():
        raise ValueError("Simulated holdout paths are nonfinite")
    qs = np.percentile(hold_paths, [5, 50, 95], axis=1)
    test_dates = [levels.index[n_train-1].date().isoformat()] + [
        d.date().isoformat() for d in levels.index[n_train:]]
    observed = [float(v) for v in levels.iloc[n_train-1:].to_numpy(dtype=float)]
    log_test_rmse = float(np.sqrt(np.mean((heldout-mean_log)**2)))
    baseline_rmse = float(np.sqrt(np.mean(heldout**2)))
    z = (heldout-mean_log)/sample_sigma
    hit_rate = float(np.mean(np.abs(z) <= 1.96))
    # Forecasts use exactly frozen train estimates; do not refit after test.
    projected = math_models.simulate_gbm(
        float(levels.iloc[-1]), mu, sigma,
        float(params["years"]), int(params["steps"]),
        int(params["paths"]), int(params["seed"]))
    if not np.isfinite(projected).all():
        raise ValueError("Simulated future paths are nonfinite")
    output_metrics = [
        metric("Training return observations", n_train, "periods"),
        metric("Chronological holdout returns", n_test, "periods"),
        metric("Annualized fitted drift μ", mu, "decimal/year · historical physical measure"),
        metric("Annualized fitted volatility σ", sigma, "decimal/sqrt(year)"),
        metric("Training mean log return", mean_log, "per observed period"),
        metric("Training log-return sample std", sample_sigma, "per observed period"),
        metric("Held-out one-step log-return RMSE", log_test_rmse, "log return"),
        metric("Zero-drift baseline held-out RMSE", baseline_rmse, "log return"),
        metric("Holdout one-step 95% Gaussian coverage", hit_rate, "fraction"),
        metric("Synthetic holdout fan paths", int(params["paths"]), "seeded paths"),
    ]
    result = {
        "source": {**source, "fit_end_date": levels.index[n_train-1].date().isoformat(),
                   "test_start_date": levels.index[n_train].date().isoformat(),
                   "train_returns": n_train, "test_returns": n_test,
                   "fitted_parameters_from_test_data": False,
                   "test_fraction": n_test/n},
        "metrics": output_metrics,
        "plots": [
            xy("Historically fitted GBM · HOLDOUT: actual vs simulated fan",
               test_dates, [
                   line("Observed holdout (not used in fit)", observed),
                   line("Seeded model median", qs[1])],
               "Actual observation date", "Index wealth / stock close (source unit)",
               kind="fan2d",
               band={"lower": qs[0].tolist(), "upper": qs[2].tolist()}),
            xy("Historical log-return fit · training and held-out periods",
               [d.date().isoformat() for d in returns.index], [
                   line("Observed log return", x),
                   line("Training fitted mean", np.full(n,mean_log))],
               "Actual observation date","Log return per period"),
            fan("ILLUSTRATIVE forward GBM simulation · not a prediction",
                projected, float(params["years"]), "Years after last observed close"),
        ],
        "table": [
            {"measure": "Training start", "value": returns.index[0].date().isoformat()},
            {"measure": "Training end", "value": returns.index[n_train-1].date().isoformat()},
            {"measure": "Holdout start", "value": returns.index[n_train].date().isoformat()},
            {"measure": "Holdout end", "value": returns.index[-1].date().isoformat()},
            {"measure": "Fitted annualized physical drift", "value": mu},
            {"measure": "Fitted annualized physical volatility", "value": sigma},
            {"measure": "Holdout observed 95% one-step coverage", "value": hit_rate},
            {"measure": "Holdout 1-step RMSE", "value": log_test_rmse},
            {"measure": "Zero-drift baseline 1-step RMSE", "value": baseline_rmse},
        ],
        "notes": [
            "Parameters estimated using only first 80% of chronologically ordered observed log returns.",
            "Daily return convention is 252 trading sessions/year; monthly is 12 periods/year.",
            "The model is NOT risk-neutral option calibration; fitted μ is a noisy physical-drift estimate.",
            "Both forecast fans are SEEDED ARTIFICIAL paths; the observed holdout is plotted separately.",
            "A short retrospective test is NOT a genuinely preregistered prospective test.",
        ],
        "limitations": [
            "Source and source claims require ordinary data-quality checks; vendor trust is not the same as missing-dividend correction.",
            "GBM assumes lognormal diffusion, constant physical drift and volatility, and independent Gaussian increments. Actual equity returns violate these assumptions.",
            "Historical drift estimates are extremely noisy. Do not use this model as a trading signal or expected-return guarantee.",
            "The final 20% is not used for fitting WITHIN this run, but prior human model selection may compromise true holdout independence.",
            "95% one-step coverage is descriptive and especially unreliable when only 2–5 periods are held out.",
        ],
        "evidence_type": "historical_parameter_estimation_with_seeded_scenarios",
        "calibration": {"method": "log_return_sample_moments", "mu": mu, "sigma": sigma,
                        "annualization": annual, "train_count": n_train,
                        "test_count": n_test, "test_used_in_fit": False},
    }
    if n < 24:
        result["limitations"].append(
            f"SHORT SAMPLE WARNING: {n} returns total. Treat estimates as exploratory; "
            "24+ monthly observations are recommended and longer horizons are substantially better.")
    if source["is_synthetic_fixture"]:
        result["limitations"].append(
            "SYNTHETIC FIXTURE: numerical data are generated, not observed market history. "
            "Do not report this as empirical GBM calibration.")
    if params["target"] == "stock":
        result["limitations"].append(
            "Dhan says daily bars are split/bonus adjusted. This does not establish "
            "dividend-reinvested stock returns or complete delisting proceeds.")
    else:
        result["limitations"].append(
            "The benchmark is a declared NIFTY TRI return series; issuer/source identity "
            "and redistribution rights remain external to statistical calibration.")
    return result
