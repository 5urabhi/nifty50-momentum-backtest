"""Source-bound research evidence for completed QuantLab runs.

Read-only. No Dhan requests, portfolio actions, fabricated returns, or automatic
publication certification. Statistics are exploratory unless a genuinely frozen,
independently verified prospective protocol supplies stronger evidence.
"""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd

from index_research.inference import newey_west_mean_test
from . import frozen_study, model_lab, service

Kind = Literal["model_run", "research_run"]
PER_YEAR = 12
MAX_MONTHS = 2400
DEFAULT_REPLICATIONS = 1000


def _number(v):
    try:
        value = float(v)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _item(name: str, value, unit: str = "", detail: str = "") -> dict:
    return {"name": name, "value": _number(value) if isinstance(
        value, (int, float, np.number)) else value, "unit": unit, "detail": detail}


def _check(name: str, status: str, detail: str, action: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail, "next_action": action}


def _classify(kind: str, source: dict | None, mode: str = "") -> str:
    if (source or {}).get("dataset_kind") == "synthetic" or kind == "synthetic" or mode == "synthetic":
        return "synthetic_demo"
    if mode == "theoretical":
        return "theoretical"
    if kind in {"dhan", "uploaded", "local", "historical"} or mode == "historical":
        return "observed_unverified"
    return "unknown"


def _monthly(run_id: str) -> tuple[dict, pd.DataFrame, int]:
    """Read the complete bounded saved CSV; service.run_details truncates tables."""
    detail = service.run_details(run_id)
    folder = service._run_path(run_id)  # existing safe-id and completed-manifest guard
    target = folder / "monthly_results.csv"
    if not target.is_file() or target.is_symlink() or target.stat().st_size > 8_000_000:
        raise ValueError("Saved monthly return artifact is missing or exceeds the research limit")
    data = pd.read_csv(target, nrows=MAX_MONTHS + 1)
    if len(data) > MAX_MONTHS:
        raise ValueError(f"More than {MAX_MONTHS} saved months: narrow the study before inference")
    if not {"date", "strategy_net", "benchmark"}.issubset(data.columns):
        raise ValueError("Saved return artifact lacks date, strategy_net or benchmark")
    dates = pd.to_datetime(data["date"], errors="coerce")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Saved return dates are invalid, duplicated or not chronological")
    data["date"] = dates.dt.strftime("%Y-%m-%d")
    for col in ("strategy_net", "benchmark"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    values = data[["strategy_net", "benchmark"]].to_numpy(dtype=float)
    valid = np.isfinite(values).all(axis=1) & (values > -1).all(axis=1)
    invalid = int((~valid).sum())
    frame = data.loc[valid, ["date", "strategy_net", "benchmark"]].copy()
    return detail, frame, invalid


def _bootstrap(x: np.ndarray, *, confidence: float = .95, seed: int = 2026,
               replications: int = DEFAULT_REPLICATIONS) -> dict | None:
    """Circular moving-block percentile CI for annualized arithmetic mean.

    This conditional interval does not correct for selected strategies or
    changing regimes; zero inclusion is not a publication gate by itself.
    """
    n = len(x)
    if n < 24:
        return None
    block = min(6, max(2, int(round(n ** (1/3)))))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(replications, math.ceil(n / block)))
    indices = ((starts[:, :, None] + np.arange(block)) % n).reshape(replications, -1)[:, :n]
    estimates = x[indices].mean(axis=1) * PER_YEAR * 100
    q = (1 - confidence) / 2
    lo, hi = np.quantile(estimates, [q, 1 - q])
    return {"estimate_pp_per_year": float(x.mean() * PER_YEAR * 100),
            "lower_pp_per_year": float(lo), "upper_pp_per_year": float(hi),
            "confidence": confidence, "method": "circular_moving_block_percentile",
            "replications": replications, "block_months": block, "seed": seed,
            "interval_includes_zero": bool(lo <= 0 <= hi)}


def _risk(r: np.ndarray, b: np.ndarray) -> list[dict]:
    n = len(r)
    if n < 2:
        return []
    active = r - b
    s = float(np.std(r, ddof=1))
    ts = float(np.std(active, ddof=1))
    down = float(np.sqrt(np.mean(np.minimum(r, 0) ** 2)))
    wealth = np.r_[1., np.cumprod(1 + r)]
    peaks = np.maximum.accumulate(wealth)
    dd = float(np.min(wealth / peaks - 1))
    bvar = float(np.var(b, ddof=1))
    q = float(np.quantile(-r, .95))
    losses = -r
    es = float(np.mean(losses[losses >= q]))
    return [
        _item("Strategy CAGR", math.expm1(float(np.log1p(r).sum()) * PER_YEAR / n),
              "fraction per year", "Geometrically compounded monthly net returns"),
        _item("Benchmark CAGR", math.expm1(float(np.log1p(b).sum()) * PER_YEAR / n),
              "fraction per year", "Source-reported benchmark; convention may differ"),
        _item("Annualized volatility", s * math.sqrt(PER_YEAR),
              "fraction per year", "Sample standard deviation times sqrt(12)"),
        _item("Zero-rate Sharpe", float(np.mean(r) * math.sqrt(PER_YEAR) / s) if s > 1e-12 else None,
              "ratio", "Zero risk-free rate is an explicit assumption"),
        _item("Zero-threshold Sortino", float(np.mean(r) * math.sqrt(PER_YEAR) / down) if down > 1e-12 else None,
              "ratio", "Threshold 0; uses population downside semideviation"),
        _item("Max drawdown", dd, "fraction", "Includes the initial wealth value 1.0"),
        _item("Tracking error", ts * math.sqrt(PER_YEAR), "fraction per year",
              "Std. dev. of paired net strategy minus benchmark"),
        _item("Information ratio", float(np.mean(active) * math.sqrt(PER_YEAR) / ts) if ts > 1e-12 else None,
              "ratio", "Annualized arithmetic active mean / tracking error"),
        _item("Beta versus benchmark", float(np.cov(r, b, ddof=1)[0, 1] / bvar) if bvar > 1e-12 else None,
              "ratio", "Sample covariance / sample benchmark variance"),
        _item("Historical VaR 95%", q, "decimal loss", "95th percentile of negative monthly return"),
        _item("Historical expected shortfall 95%", es, "decimal loss",
              "Mean observed loss at or beyond the 95th loss percentile"),
    ]


def _figures(data: pd.DataFrame, ci: dict | None) -> list[dict]:
    if len(data) < 2:
        return []
    x = data["date"].tolist()
    r = data["strategy_net"].to_numpy(dtype=float)
    b = data["benchmark"].to_numpy(dtype=float)
    active = (r - b) * 100
    charts = [
        {"kind": "bar2d", "title": "Monthly net active return",
         "x": x, "x_label": "Saved month", "y_label": "Percentage points",
         "traces": [{"name": "Strategy minus benchmark", "y": active.tolist()}]},
    ]
    if len(data) >= 8:
        bins = min(20, max(6, int(math.sqrt(len(data)))))
        counts, edges = np.histogram(active, bins=bins)
        centers = ((edges[:-1] + edges[1:]) / 2).tolist()
        charts.append({"kind": "histogram2d", "title": "Distribution of observed monthly active returns",
                       "x": centers, "x_label": "Active return (percentage points)",
                       "y_label": "Number of saved months",
                       "traces": [{"name": "Observed frequency", "y": counts.astype(int).tolist()}]})
    if len(data) >= 12:
        rvol = [None] * 11
        tracking = [None] * 11
        for i in range(11, len(r)):
            rvol.append(float(np.std(r[i-11:i+1], ddof=1) * math.sqrt(12) * 100))
            tracking.append(float(np.std((r - b)[i-11:i+1], ddof=1) * math.sqrt(12) * 100))
        charts.append({"kind": "line2d", "title": "Rolling 12-month risk decomposition",
                       "x": x, "x_label": "Saved month", "y_label": "Annualized volatility (%)",
                       "traces": [{"name": "Strategy volatility", "y": rvol},
                                  {"name": "Active tracking error", "y": tracking}]})
    if ci:
        charts.append({"kind": "bar2d", "title": "Block-bootstrap interval of mean active return",
                       "x": ["Lower 95%", "Estimated mean", "Upper 95%"],
                       "x_label": "Conditional interval boundary",
                       "y_label": "Annualized mean difference (percentage points)",
                       "traces": [{"name": "Estimate", "y": [
                           ci["lower_pp_per_year"], ci["estimate_pp_per_year"],
                           ci["upper_pp_per_year"]]}]})
    return charts


def _split(detail: dict, data: pd.DataFrame) -> dict:
    config = detail.get("meta", {}).get("config", {})
    cutoff = config.get("final_test_start")
    if not cutoff:
        return {"label": "full_history_exploratory", "declared_final_test": False,
                "final_test_months": 0,
                "note": "No declared final_test_start; model search and selection can overfit the full sample."}
    try:
        start = pd.Timestamp(cutoff)
    except (TypeError, ValueError):
        return {"label": "invalid_declared_test_date", "declared_final_test": False,
                "final_test_months": 0, "note": "Saved final test date is invalid"}
    dates = pd.to_datetime(data["date"])
    count = int((dates >= start).sum())
    return {"label": "declared_chronological_final_test", "declared_final_test": True,
            "final_test_start": str(start.date()), "final_test_months": count,
            "note": "Chronological split is declared, but independence and pre-registration "
                    "of the final test have not been externally verified."}


def summarize(kind: Kind, run_id: str) -> dict:
    """An evidence report that never upgrades observed data into audited truth."""
    if kind == "model_run":
        saved = model_lab.read_saved_model(run_id)
        source = saved.get("source") or {}
        classification = _classify(source.get("dataset_kind", ""), source, saved.get("mode", ""))
        check = [
            _check("Model execution", "pass", "Saved registered Python model output is available."),
            _check("Source classification", "blocked" if classification == "synthetic_demo" else
                   "warning" if classification == "observed_unverified" else "not_applicable",
                   classification, "Attach independent source and vintage documentation where applicable."),
            _check("Unseen evaluation", "blocked", "Model results may be theoretical or in-sample; "
                   "this saved record is not a frozen prospective forecast."),
            _check("Publication-level evidence", "blocked",
                   "Return figures and source checksums are not independent accuracy verification.",
                   "Validate corporate actions, PIT membership, benchmark and untouched holdout."),
        ]
        return {"id": run_id, "kind": kind, "model": saved.get("title"),
                "evidence_class": classification, "readiness": "research_diagnostic_only",
                "observations": source.get("observations"), "rejected_rows": None,
                "metrics": [_item(m.get("label", ""), m.get("value"), m.get("unit", ""))
                            for m in saved.get("metrics", [])],
                "checks": check, "uncertainty": None, "hac": None,
                "split": {"label": "model_specific_in_sample_or_theoretical"},
                "plots": saved.get("plots", []),
                "source": {"dataset_id": source.get("dataset_id"),
                           "dataset_kind": source.get("dataset_kind"),
                           "source_sha256": saved.get("source_sha256"),
                           "frequency": source.get("frequency")},
                "limitations": list(saved.get("limitations", [])),
                "method": "Archived numerical output inspection only",
                "warning": "No automatic prospective significance inference for arbitrary simulated or fitted models."}
    if kind != "research_run":
        raise ValueError("Only model_run and research_run are supported")
    detail, df, rejected = _monthly(run_id)
    original_count = len(df) + rejected
    source = detail.get("source", {})
    classification = _classify(source.get("dataset_kind", ""), source)
    n = len(df)
    r = df["strategy_net"].to_numpy(dtype=float)
    b = df["benchmark"].to_numpy(dtype=float)
    active = r - b
    ci = _bootstrap(active)
    hac = None
    if n >= 24:
        result = newey_west_mean_test(pd.Series(active))
        hac = {key: _number(value) if isinstance(value, (int, float, np.number)) else value
               for key, value in result.items()}
        hac["null_hypothesis"] = "Mean monthly net active return is zero"
        hac["interpretation"] = "Asymptotic HAC normal approximation; not multiple-testing adjusted."
    periods = _split(detail, df)
    receipt = frozen_study.run_receipt(run_id)
    frozen_status = receipt["state"]
    periods["frozen_protocol_status"] = frozen_status
    checks = [
        _check("Valid paired monthly returns", "pass" if n >= 24 and rejected == 0 else "warning",
               f"{n} paired valid observations out of {original_count}; {rejected} rejected.",
               "Resolve missing, infinite, or <= -100% returns at their source."),
        _check("Uncertainty sample length", "pass" if n >= 24 else "blocked",
               f"{n} complete months; >=24 required for a moving-block confidence interval.",
               "Collect >=24 eligible paired return months without filling absent observations."),
        _check("Source type", "blocked" if classification == "synthetic_demo" else "warning",
               classification, "Use independently sourced, audited historical data."),
        _check("Chronological final-test split", "warning" if periods["declared_final_test"] else "blocked",
               periods["note"], "Freeze research selection and a later final test before evaluating."),
        _check("Independent PIT and return audit", "blocked",
               "Daily or monthly close prices alone do not certify historical constituents, "
               "adjusted total returns, benchmark TRI or publication-dated fundamentals.",
               "Supply and independently audit point-in-time source declarations."),
        _check("Publication / live-trading certification", "blocked",
               "No source review, multiple-search correction or prospective fills are certified.",
               "Conduct an external source audit and freeze a prospective evaluation protocol."),
    ]
    checks.append(_check(
        "Single-use source-bound final-test lock",
        "pass" if frozen_status == "software_frozen_exploratory" else "blocked",
        "Frozen dataset hashes, configuration and post-execution receipts match"
        if frozen_status == "software_frozen_exploratory" else
        "No valid single-use frozen protocol receipt: " + frozen_status,
        "Create the frozen protocol BEFORE running an untouched final test. "
        "Local timestamps still cannot prove it was never inspected."))
    return {"id": run_id, "kind": kind, "model": detail.get("meta", {}).get(
        "config", {}).get("name", run_id), "evidence_class": classification,
        "readiness": "research_diagnostic_only", "observations": n,
        "rejected_rows": rejected, "metrics": _risk(r, b),
        "uncertainty": ci, "hac": hac, "checks": checks,
        "split": periods, "frozen_receipt": receipt, "plots": _figures(df, ci), "limitations": [
            "Full-history uncertainty is exploratory; strategy search and repeated testing create selection bias.",
            "Block-bootstrap intervals assume approximately stationary, short-range dependent monthly returns.",
            "The price-index / total-return benchmark convention must match strategy returns.",
            "This audit is read-only. It does not reconstruct missing source observations."],
        "source": {"dataset_id": source.get("dataset_id"),
                   "dataset_kind": source.get("dataset_kind"),
                   "source_hashes": detail.get("meta", {}).get("input_sha256", {})},
        "method": "Circular moving-block bootstrap (1000 reps, fixed seed 2026) and "
                  "Newey-West asymptotic HAC, conditional on saved paired monthly returns",
        "warning": "Not an independent audit, publication certification, or investment recommendation."}


def paired_comparison(baseline: str, challengers: list[str]) -> dict:
    """Paired controlled comparison on same source, benchmark and calendar.

    Uses Holm adjustment on asymptotic HAC p-values. This controls a declared
    family of comparisons, not undisclosed searches over many prior strategies.
    """
    if not 1 <= len(challengers) <= 7 or len(set([baseline, *challengers])) != len(challengers) + 1:
        raise ValueError("Choose one baseline and 1–7 distinct challenger research runs")
    runs = [baseline, *challengers]
    loaded = [_monthly(run_id) for run_id in runs]
    kinds = {str(d.get("source", {}).get("dataset_kind")) for d, _, _ in loaded}
    ids = {str(d.get("source", {}).get("dataset_id")) for d, _, _ in loaded}
    hashes = [d.get("meta", {}).get("input_sha256", {}) for d, _, _ in loaded]
    if len(kinds) != 1 or len(ids) != 1 or not next(iter(ids), None) or next(iter(ids)) == "None":
        raise ValueError("Compared runs must reference the same dataset ID and evidence class")
    if not hashes[0] or any(h != hashes[0] for h in hashes[1:]):
        raise ValueError("Input file checksums must match across the paired research runs")
    indexed = [frame.set_index("date") for _, frame, _ in loaded]
    dates = sorted(set.intersection(*(set(frame.index) for frame in indexed)))
    if len(dates) < 24:
        raise ValueError("Paired comparison needs >=24 common complete months, without filling gaps")
    matrices = [frame.loc[dates] for frame in indexed]
    reference = matrices[0]["benchmark"].to_numpy(dtype=float)
    if any(not np.allclose(frame["benchmark"].to_numpy(dtype=float),
                           reference, rtol=0, atol=1e-10) for frame in matrices[1:]):
        raise ValueError("Different benchmark returns on matched dates; cannot compute paired ranking")
    base = matrices[0]["strategy_net"].to_numpy(dtype=float)
    summary = []
    for run_id, frame in zip(challengers, matrices[1:]):
        delta = frame["strategy_net"].to_numpy(dtype=float) - base
        ci = _bootstrap(delta)
        hac = newey_west_mean_test(pd.Series(delta))
        p = _number(hac["two_sided_normal_p_value"])
        summary.append({"run_id": run_id,
            "annualized_arithmetic_difference_pp": float(np.mean(delta) * PER_YEAR * 100),
            "ci95_low_pp": ci["lower_pp_per_year"] if ci else None,
            "ci95_high_pp": ci["upper_pp_per_year"] if ci else None,
            "hac_p_nominal": p,
            "hac_lags": int(hac["lags"]),
            "holm_adjusted_p": None,
            "reject_hac_at_5pct": False})
    valid = sorted((i, row["hac_p_nominal"]) for i, row in enumerate(summary)
                   if row["hac_p_nominal"] is not None)
    valid.sort(key=lambda pair: pair[1])
    # Holm step-down adjustment with monotonic running maximum.
    previous = 0.
    m = len(valid)
    for rank, (i, p) in enumerate(valid):
        adjusted = min(1., max(previous, (m - rank) * p))
        summary[i]["holm_adjusted_p"] = adjusted
        summary[i]["reject_hac_at_5pct"] = adjusted < .05
        previous = adjusted
    paths = []
    for run_id, frame in zip(runs, matrices):
        values = frame["strategy_net"].to_numpy(dtype=float)
        paths.append({"name": run_id, "y": (100 * np.cumprod(1 + values)).tolist()})
    return {"baseline": baseline, "challengers": challengers,
            "evidence_class": _classify(next(iter(kinds)), {"dataset_kind": next(iter(kinds))}),
            "dataset_id": next(iter(ids)), "source_hashes": hashes[0],
            "paired_months": len(dates), "start": dates[0], "end": dates[-1],
            "rows": summary, "plot": {"kind": "line2d",
                "title": "Paired common-calendar strategy wealth (base 100)",
                "x": dates, "x_label": "Matched saved month",
                "y_label": "Net cumulative wealth index", "traces": paths},
            "method": "Paired differences of monthly net strategy returns; Newey-West HAC "
                      "z-p-values and Holm familywise adjustment; circular moving-block "
                      "95% percentile intervals (fixed seed).",
            "warning": "Exploratory unless all research decisions were frozen independently. "
                       "Holm addresses only the selected comparison family, not undisclosed "
                       "parameter searches or historical data biases."}
