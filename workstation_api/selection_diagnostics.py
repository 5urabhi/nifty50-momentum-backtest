"""Auditable, retrospective model-selection diagnostics for saved index runs.

PBO uses symmetric combinatorial, contiguous-block splits (CSCV style). These
folds are NOT a prospective walk-forward test: in-sample folds can occur after
out-of-sample folds in calendar time. Without label event-end times we do not
pretend CPCV purging has occurred. All runs must use matched archived source,
hashes, benchmark and return dates; no missing values are fabricated.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
from scipy import stats

from . import result_evidence

MIN_MONTHS_PER_BLOCK = 12
MAX_MONTHS = result_evidence.MAX_MONTHS
GAMMA = 0.5772156649015329
MAX_TRIALS = 10000


def _series(ids: list[str]) -> tuple[list[str], np.ndarray, np.ndarray, list[str], dict]:
    """Reuse the paired-comparison evidence gate before statistical selection."""
    if not 2 <= len(ids) <= 8 or len(set(ids)) != len(ids):
        raise ValueError("Select 2–8 distinct archived index research runs")
    # Do not bypass the existing source ID, hash, benchmark and >=24 aligned
    # month checks by grabbing files independently.
    checked = result_evidence.paired_comparison(ids[0], ids[1:])
    loaded = [result_evidence._monthly(run_id) for run_id in ids]
    indexed = [frame.set_index("date") for _, frame, _ in loaded]
    common = sorted(set.intersection(*(set(frame.index) for frame in indexed)))
    if len(common) > MAX_MONTHS:
        raise ValueError("Matched sample exceeds the bounded archived evidence limit")
    matrix = np.column_stack([
        frame.loc[common, "strategy_net"].to_numpy(dtype=float) for frame in indexed])
    benchmark = indexed[0].loc[common, "benchmark"].to_numpy(dtype=float)
    if not np.isfinite(matrix).all() or not np.isfinite(benchmark).all():
        raise ValueError("Non-finite matched return is not eligible for model selection")
    return common, matrix, benchmark, ids, checked


def _sharpe(x: np.ndarray) -> np.ndarray:
    """Per-month Sharpe, risk-free rate 0, undefined for flat or tiny samples."""
    if x.ndim != 2 or x.shape[0] < 3:
        raise ValueError("Sharpe ranking requires >=3 matched monthly returns")
    dev = np.std(x, axis=0, ddof=1)
    avg = np.mean(x, axis=0)
    # Do not call constant excess returns infinite skill.
    return np.divide(avg, dev, out=np.zeros_like(avg), where=dev > 1e-12)


def _rank(x: np.ndarray, value: float) -> float:
    """Midrank / candidate count, worst 0.5/M, best 1-0.5/M."""
    ranks = stats.rankdata(x, method="average")
    matches = np.flatnonzero(np.isclose(x, value, rtol=0, atol=1e-12))
    if not len(matches):
        raise ValueError("Selected Sharpe missing from archived rank vector")
    return float((ranks[matches[0]] - .5) / len(x))


def cscv(returns: np.ndarray, *, folds: int = 4) -> dict:
    """Combinatorial symmetric cross-validation, with honest statistical scope."""
    if folds not in (4, 6, 8):
        raise ValueError("Use 4, 6 or 8 contiguous CSCV blocks")
    if returns.ndim != 2 or returns.shape[1] < 2 or returns.shape[1] > 8:
        raise ValueError("CSCV needs 2–8 matched candidate return series")
    n, m = returns.shape
    if n < folds * MIN_MONTHS_PER_BLOCK:
        raise ValueError(
            f"CSCV needs {folds * MIN_MONTHS_PER_BLOCK} common monthly returns "
            f"for {folds} blocks (12 per block); currently {n}")
    blocks = np.array_split(np.arange(n, dtype=int), folds)
    observations = []
    for selected in itertools.combinations(range(folds), folds // 2):
        train = np.concatenate([blocks[i] for i in range(folds) if i in selected])
        test = np.concatenate([blocks[i] for i in range(folds) if i not in selected])
        is_sharpe = _sharpe(returns[train])
        os_sharpe = _sharpe(returns[test])
        winner = int(np.argmax(is_sharpe))
        percentile = _rank(os_sharpe, float(os_sharpe[winner]))
        odds = float(math.log(percentile / (1 - percentile)))
        observations.append({
            "train_blocks": [int(i + 1) for i in selected],
            "test_blocks": [int(i + 1) for i in range(folds) if i not in selected],
            "chosen_candidate_index": winner,
            "is_monthly_sharpe": float(is_sharpe[winner]),
            "oos_monthly_sharpe": float(os_sharpe[winner]),
            "oos_rank_percentile": percentile,
            "logit_oos_rank": odds,
        })
    logits = np.asarray([x["logit_oos_rank"] for x in observations])
    wins = np.asarray([x["chosen_candidate_index"] for x in observations])
    return {
        "folds": folds,
        "minimum_observations": folds * MIN_MONTHS_PER_BLOCK,
        "combinations": len(observations),
        "pbo_fraction": float(np.mean(logits < 0)),
        "median_oos_rank_percentile": float(np.median([x["oos_rank_percentile"]
                                                      for x in observations])),
        "winner_counts": [int(np.sum(wins == i)) for i in range(m)],
        "blocks": [{"block": i + 1, "first_index": int(b[0]),
                    "last_index": int(b[-1]), "observations": int(len(b))}
                   for i, b in enumerate(blocks)],
        "rows": observations,
        "interpretation": "Fraction of retrospective symmetric splits where the "
                          "best in-split strategy ranks below the median in other folds.",
        "limitation": "CSCV is NOT an untouched chronological final test. "
                      "These folds are not purged because overlapping event label "
                      "end-times are not available. PBO is a descriptive selection-risk "
                      "diagnostic, not the probability of losing money.",
    }


def deflated_sharpe(returns: np.ndarray, *, trials: int) -> dict:
    """Approximate Bailey/Lopez-de-Prado deflated Sharpe statistic.

    Uses raw per-month returns, zero risk-free rate, the observed full-sample
    winner (optimistically selected), and a documented trial count. We require
    all actual strategy-search trials to be declared; comparing two saved runs
    alone cannot recover an undocumented search history.
    """
    if returns.ndim != 2 or returns.shape[0] < 30 or returns.shape[1] < 2:
        raise ValueError("Deflated Sharpe requires >=30 common months and >=2 candidates")
    n, m = returns.shape
    if not m <= trials <= MAX_TRIALS:
        raise ValueError(f"Declared tested configurations must be {m}–{MAX_TRIALS}")
    ratios = _sharpe(returns)
    selected = int(np.argmax(ratios))
    r = returns[:, selected]
    per_month = float(ratios[selected])
    skewness = float(stats.skew(r, bias=False))
    kurtosis = float(stats.kurtosis(r, fisher=False, bias=False))
    if not math.isfinite(skewness) or not math.isfinite(kurtosis):
        raise ValueError("Deflated Sharpe needs finite observed skew and kurtosis")
    # Standard deviation of a Sharpe estimate under weakly dependent iid-like
    # returns; conditional and unreliable under pronounced serial dependence.
    variance = max(0., 1 - skewness * per_month
                   + ((kurtosis - 1) / 4.) * per_month**2)
    se = math.sqrt(variance / (n - 1))
    if se <= 1e-12:
        raise ValueError("Near-zero Sharpe uncertainty: deflated statistic undefined")
    sigma_sharpe = 1 / math.sqrt(n - 1)
    if trials == 1:
        threshold = 0.
    else:
        threshold = sigma_sharpe * (
            (1 - GAMMA) * stats.norm.ppf(1 - 1 / trials)
            + GAMMA * stats.norm.ppf(1 - 1 / (trials * math.e))
        )
    z = (per_month - threshold) / se
    probability = float(stats.norm.cdf(z))
    return {
        "selected_candidate_index": selected,
        "selected_monthly_sharpe": per_month,
        "selected_annualized_zero_rate_sharpe": per_month * math.sqrt(12),
        "threshold_monthly_sharpe": float(threshold),
        "threshold_annualized_zero_rate_sharpe": float(threshold * math.sqrt(12)),
        "deflated_sharpe_probability": probability,
        "declared_number_of_trials": trials,
        "candidate_count": m,
        "selected_monthly_skew": skewness,
        "selected_monthly_kurtosis": kurtosis,
        "sharpe_estimation_se": se,
        "assumptions": "Approximate iid-like per-month Sharpe sampling variance, "
                       "zero risk-free rate, sample skew/kurtosis, independent-trial "
                       "maxima approximation; all prior tested configurations must "
                       "be counted, not only the shortlisted survivors.",
        "limitation": "This is a full-sample retrospective selection diagnostic, "
                      "NOT prospective significance or a certificate of real alpha.",
    }


def regimes(returns: np.ndarray, benchmark: np.ndarray, *,
            trail: int = 6) -> dict:
    """Retrospective relative-volatility buckets using lagged benchmark history.

    Regime *thresholds* are calculated over the observed history and are not
    ex-ante tradable forecasts. Individual monthly classifications use trailing
    benchmark returns only (exclude the target month).
    """
    n, m = returns.shape
    if n < 48 or len(benchmark) != n or trail < 3:
        raise ValueError("Regime diagnostics need >=48 paired months and trailing history")
    past_vol = np.full(n, np.nan)
    for t in range(trail, n):
        past_vol[t] = float(np.std(benchmark[t - trail:t], ddof=1) * math.sqrt(12))
    measured = past_vol[np.isfinite(past_vol)]
    if len(measured) < 24:
        raise ValueError("Too few measured trailing benchmark volatilities")
    low, high = (float(x) for x in np.quantile(measured, [1/3, 2/3]))
    labels = ["Low trailing volatility", "Middle trailing volatility",
              "High trailing volatility"]
    summary = []
    rows = []
    for t in range(trail, n):
        group = int(past_vol[t] > low) + int(past_vol[t] > high)
        rows.append({"index": t, "trailing_benchmark_vol_annualized": float(past_vol[t]),
                     "regime": labels[group]})
    for j in range(m):
        for k, name in enumerate(labels):
            idx = [r["index"] for r in rows if r["regime"] == name]
            x = returns[idx, j]
            b = benchmark[idx]
            summary.append({
                "candidate_index": j, "regime": name,
                "observations": len(idx),
                "strategy_mean_monthly_fraction": float(np.mean(x)) if len(idx) else None,
                "active_mean_monthly_fraction": float(np.mean(x - b)) if len(idx) else None,
                "down_month_fraction": float(np.mean(x < 0)) if len(idx) else None,
            })
    return {
        "trail_months": trail, "low_threshold_annual_vol": low,
        "high_threshold_annual_vol": high, "summary": summary,
        "regime_by_month": rows,
        "limitation": "Monthly labels use prior six benchmark months, but "
                      "the quantile regime thresholds are fitted over the sample "
                      "(retrospective). No source establishes causal regime skill "
                      "or out-of-sample predictability.",
    }


def audit(run_ids: list[str], *, folds: int = 4, declared_trials: int | None = None,
          benchmark_trail: int = 6) -> dict:
    """One evidence-linked model-selection report from matched saved runs."""
    dates, returns, benchmark, ids, check = _series(run_ids)
    n, m = returns.shape
    if n < 48:
        raise ValueError(f"Advanced selection audit needs >=48 common complete months "
                         f"(preferred >=58 with +20%); found {n}")
    trials = m if declared_trials is None else declared_trials
    if not isinstance(trials, int) or isinstance(trials, bool) or not m <= trials <= MAX_TRIALS:
        raise ValueError(f"Declared trial count must be an integer from {m} to {MAX_TRIALS}")
    if benchmark_trail not in (3, 6, 12):
        raise ValueError("Trailing regime window must be 3, 6 or 12 months")
    selection = cscv(returns, folds=folds)
    d = deflated_sharpe(returns, trials=trials)
    regime = regimes(returns, benchmark, trail=benchmark_trail)
    for row in selection["rows"]:
        row["selected_run_id"] = ids[row.pop("chosen_candidate_index")]
    selection["winner_counts"] = [
        {"run_id": run_id, "selections": count}
        for run_id, count in zip(ids, selection["winner_counts"])]
    d["selected_run_id"] = ids[d.pop("selected_candidate_index")]
    for item in regime["summary"]:
        item["run_id"] = ids[item.pop("candidate_index")]
    return {
        "run_ids": ids, "dataset_id": check["dataset_id"],
        "source_hashes": check["source_hashes"],
        "evidence_class": check["evidence_class"],
        "common_months": n, "preferred_common_months": math.ceil(1.2 * 48),
        "start": dates[0], "end": dates[-1],
        "pbo": selection, "deflated_sharpe": d, "regimes": regime,
        "paired_comparison_warning": check["warning"],
        "interpretation": "Exploratory retrospective selection-risk diagnostics "
                          "on aligned, archived, net-of-cost monthly returns. "
                          "Preserves original source classifications and checksums.",
        "never_certified": [
            "No hidden strategy-search log is independently verified.",
            "CSCV does not replace chronological walk-forward or untouched final holdout.",
            "No event-end-time data is available for CPCV purging / embargo.",
            "Original PIT membership, adjusted total returns, licensed benchmark TRI "
            "and execution costs still need independent source review.",
        ],
    }
