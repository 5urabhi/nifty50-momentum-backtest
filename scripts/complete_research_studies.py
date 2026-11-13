#!/usr/bin/env python3
"""Run QuantLab's three reproducible, evidence-labeled index research studies.

A: frozen multi-factor construction and chronological holdout.
B: historical active risk and optional factor/specific decomposition.
C: survivorship, benchmark convention, and cost sensitivity diagnostics.

All inputs are LOCAL and supplied by the researcher. No NSE/Dhan downloads,
broker orders, invented data, or automatic independent certification occur.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from index_research.data import load_research_inputs, read_returns
from index_research.empirical_validation import evidence_gate
from index_research.experiment import ExperimentConfig, run_from_directory
from index_research.statistical_inference import (
    moving_block_bootstrap_mean, newey_west_ols,
)

CORE = ("prices.csv", "membership.csv", "benchmark.csv")
SOURCE = ("BENCHMARK_SOURCE.json", "RETURN_METHODOLOGY.json",
          "PIT_MEMBERSHIP_PROVENANCE.json", "EVIDENCE_REVIEW.json")
RESEARCH = ("fundamentals.csv", "sectors.csv", "corporate_actions.csv",
            "factor_returns.csv", "benchmark_weights.csv")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def research_preflight(data_dir: str | Path, config: ExperimentConfig) -> dict:
    """Check structural prerequisites and expose external evidence blockers.

    source_file_present is not source_file_verified. A passing software gate
    is neither independently audited performance nor scientific replication.
    """
    root = Path(data_dir)
    missing = []
    present = {}
    for name in (*CORE, *SOURCE, *RESEARCH):
        path = root / name
        if path.is_symlink():
            missing.append(name + " (symlink not allowed)")
        elif path.is_file():
            present[name] = {"sha256": sha(path), "bytes": path.stat().st_size}
        elif name in CORE:
            missing.append(name)
    config_blockers = []
    if not config.validation_start or not config.final_test_start:
        config_blockers.append(
            "Explicit validation_start and final_test_start are required; "
            "do not choose dates after inspecting holdout outcomes.")
    elif pd.Timestamp(config.validation_start) >= pd.Timestamp(config.final_test_start):
        config_blockers.append("Validation must strictly precede final holdout.")
    if config.execution_lag == 0:
        config_blockers.append("Same-close execution is optimistic; choose a delayed assumption.")
    test_months = None
    first_date = last_date = None
    if not missing and not config_blockers:
        try:
            prices, membership, benchmark, fundamentals = load_research_inputs(root)
            first_date, last_date = (prices.index[0].date().isoformat(),
                                     prices.index[-1].date().isoformat())
            test_months = int((prices.index >= pd.Timestamp(config.final_test_start)).sum()) - 1
            if test_months < 12:
                config_blockers.append("Require at least 12 complete final-holdout monthly return periods.")
            if int((prices.index < pd.Timestamp(config.validation_start)).sum()) < 36:
                config_blockers.append("Require at least 36 pre-validation price observations.")
            if (membership & prices.isna()).any().any():
                config_blockers.append("Missing prices for historically eligible securities.")
            requested = config.factor_weights or {"momentum": 1}
            if set(requested) & {"value", "quality", "size"} and fundamentals is None:
                config_blockers.append("Value/Quality/Size need first-published fundamentals.csv.")
            if len(prices.columns) < config.top_n:
                config_blockers.append("The historical price panel has fewer names than top_n.")
        except (ValueError, OSError, KeyError) as exc:
            config_blockers.append("Research input validation failed: " + str(exc))
    annotations = [
        "No local software test establishes exchange-certified corporate actions, "
        "official historical constituents, benchmark comparability, or filing vintages.",
        "No final-test conclusion can be called confirmatory without a genuinely "
        "predeclared hypothesis and independent source/methodology review.",
    ]
    absent_sources = [name for name in SOURCE if name not in present]
    if absent_sources:
        annotations.append("Original-source metadata/reviewer records missing: " +
                           ", ".join(absent_sources))
    benchmark_note = "metadata_missing"
    path = root / "BENCHMARK_SOURCE.json"
    if path.is_file() and not path.is_symlink():
        try:
            metadata = json.loads(path.read_text())
            benchmark_note = str(metadata.get("return_convention", "convention_not_declared"))
            if benchmark_note not in {"gross_total_return", "net_total_return"}:
                annotations.append("Benchmark is not documented as a total-return index.")
            if metadata.get("initial_level_policy") is None:
                annotations.append("Benchmark source predates explicit no-fabricated-initial-return rule.")
        except (ValueError, OSError) as exc:
            config_blockers.append("Unreadable benchmark provenance: " + str(exc))
    declared = {"status": "not_submitted"}
    if (root / "EVIDENCE_REVIEW.json").is_file():
        try:
            declared = evidence_gate(root, root / "EVIDENCE_REVIEW.json")
        except (ValueError, OSError, TypeError) as exc:
            config_blockers.append("Invalid human evidence declaration: " + str(exc))
    synthetic = (root / "DO_NOT_CITE.txt").exists() or (
        "prices.csv" in present and
        next((name for name in pd.read_csv(root / "prices.csv", nrows=0).columns[1:]), "")
        .startswith("SYNTH_"))
    if synthetic:
        annotations.append("SYNTHETIC FIXTURE: findings must never be labeled actual NIFTY data.")
    external_blockers = absent_sources[:]
    if declared.get("status") == "BLOCKED":
        external_blockers.append("External evidence review incomplete")
    if benchmark_note not in {"gross_total_return", "net_total_return"}:
        external_blockers.append("Appropriate TRI provenance not established")
    if synthetic:
        external_blockers.append("Dataset is synthetic, not observed historical NIFTY")
    return {
        "software_ready": not missing and not config_blockers,
        "publication_ready": False,
        "external_certification": False,
        "classification": "SYNTHETIC_DEMONSTRATION" if synthetic else "OBSERVED_NOT_AUDITED",
        "missing_core_files": missing,
        "configuration_blockers": config_blockers,
        "external_evidence_blockers": sorted(set(external_blockers)),
        "available_files": present,
        "source_evidence_declaration": declared.get("status"),
        "benchmark_return_convention": benchmark_note,
        "first_date": first_date, "last_date": last_date,
        "final_holdout_periods_upper_bound": test_months,
        "disclosures": annotations,
    }


def _safe_float(number) -> float | None:
    v = float(number)
    return v if np.isfinite(v) else None


def study_b(data_dir: Path, run_dir: Path, lookback: int = 36) -> dict:
    """Estimate ex-ante BFBt+D risk using strictly earlier factor samples.

    The archived strategy weights are period-ending labels for holdings
    established at the PREVIOUS observed month-end. Use that earlier date for
    historical factor and benchmark as-of checks, not the return end date.
    """
    fac_file = data_dir / "factor_returns.csv"
    ben_file = data_dir / "benchmark_weights.csv"
    if not fac_file.is_file() or not ben_file.is_file():
        return {"status": "unavailable", "missing_inputs": [
            x for x in ("factor_returns.csv", "benchmark_weights.csv")
            if not (data_dir / x).is_file()]}
    prices, _, _, _ = load_research_inputs(data_dir)
    weights = pd.read_csv(run_dir / "post_rebalance_weights.csv", index_col=0, parse_dates=True)
    if weights.empty or set(weights.columns) != set(prices.columns):
        raise ValueError("Saved weights do not cover the original price universe")
    end_day = pd.Timestamp(weights.index[-1])
    end_ix = prices.index.get_indexer([end_day])[0]
    if end_ix <= 0:
        raise ValueError("Risk as-of date requires preceding price month")
    start_day = prices.index[end_ix-1]
    portfolio = weights.iloc[-1].reindex(prices.columns).astype(float).to_numpy()
    if not np.isfinite(portfolio).all() or abs(portfolio.sum()-1) > .01:
        return {"status": "unavailable", "reason": "Fully-invested period holdings required"}
    rows = pd.read_csv(ben_file)
    if not {"date", "ticker", "weight"}.issubset(rows.columns):
        raise ValueError("Dated benchmark weights require date,ticker,weight")
    rows["date"] = pd.to_datetime(rows["date"], errors="raise")
    rows["weight"] = pd.to_numeric(rows["weight"], errors="raise")
    if rows["date"].isna().any() or rows[["date", "ticker"]].duplicated().any():
        raise ValueError("Invalid or duplicated dated benchmark weights")
    eligible = rows.loc[rows["date"] <= start_day]
    if eligible.empty:
        return {"status": "unavailable", "reason": "No benchmark weights observable before risk formation"}
    snapshot_day = eligible["date"].max()
    subset = eligible[eligible["date"] == snapshot_day]
    if set(subset.ticker) != set(prices.columns):
        return {"status": "unavailable", "reason": "Benchmark snapshot must cover every name (including zeros)"}
    benchmark = subset.set_index("ticker").weight.reindex(prices.columns).to_numpy(dtype=float)
    if not np.isfinite(benchmark).all() or (benchmark < 0).any() or abs(benchmark.sum()-1) > 1e-6:
        raise ValueError("Benchmark weights invalid or not normalized")
    if (start_day - snapshot_day).days > 93:
        return {"status": "unavailable", "reason": "Benchmark snapshot older than 93 days"}
    factors = pd.read_csv(fac_file)
    if len(factors.columns) < 2 or factors.columns[0] != "date" or len(factors.columns) > 13:
        raise ValueError("Factor returns require date plus 1-12 named factors")
    factors["date"] = pd.to_datetime(factors["date"], errors="raise")
    if factors["date"].isna().any() or factors["date"].duplicated().any():
        raise ValueError("Factor-return dates invalid or duplicated")
    factors = factors.set_index("date").sort_index().apply(pd.to_numeric, errors="raise")
    returns = prices.pct_change(fill_method=None)
    # Strictly earlier than the decision month; no holdout observations fit risk.
    dates = returns.index[(returns.index < start_day) & returns.index.isin(factors.index)][-lookback:]
    k = factors.shape[1]
    minimum = max(18, 5*k)
    if len(dates) < minimum:
        return {"status": "unavailable", "reason": "Insufficient prior factor/price overlap",
                "required_months": minimum, "available_months": len(dates)}
    X = factors.loc[dates].to_numpy(dtype=float)
    Y = returns.loc[dates].to_numpy(dtype=float)
    if not np.isfinite(X).all() or not np.isfinite(Y).all():
        return {"status": "unavailable", "reason": "Missing historical factor/security returns"}
    if np.linalg.matrix_rank(X - X.mean(axis=0)) < k:
        return {"status": "unavailable", "reason": "Factor returns are collinear"}
    Xr = np.column_stack((np.ones(len(X)), X))
    params = np.linalg.lstsq(Xr, Y, rcond=None)[0]
    betas = params[1:].T
    residual = Y-Xr@params
    factor_cov = np.atleast_2d(np.cov(X, rowvar=False, ddof=1))*12
    specific = np.sum(residual**2, axis=0) / (len(X)-k-1)*12
    active = portfolio-benchmark
    active_exposure = active @ betas
    marginal = factor_cov @ active_exposure
    systematic = float(active_exposure @ marginal)
    idiosyncratic = float((active**2) @ specific)
    total = systematic+idiosyncratic
    if total < -1e-9:
        raise ValueError("Factor risk covariance is not positive semidefinite")
    contributions = [
        {"factor": name, "active_exposure": _safe_float(active_exposure[i]),
         "annualized_variance_contribution": _safe_float(active_exposure[i]*marginal[i])}
        for i, name in enumerate(factors.columns)]
    return {
        "status": "estimated_not_independently_certified",
        "formation_date": start_day.date().isoformat(),
        "benchmark_snapshot_date": snapshot_day.date().isoformat(),
        "holdings_period_end": end_day.date().isoformat(),
        "fitted_months": len(dates), "factor_names": list(factors.columns),
        "annualized_systematic_variance": _safe_float(systematic),
        "annualized_specific_variance": _safe_float(idiosyncratic),
        "annualized_tracking_error_estimate": _safe_float(np.sqrt(max(0., total))),
        "factor_contributions": contributions,
        "warning": "OLS proxy-factor risk, not a licensed Barra/MSCI model; portfolio holdings "
                   "are period-start exposures indexed by return end; independent input audit pending.",
    }


def study_c(data_dir: Path, results_dir: Path, config: ExperimentConfig) -> dict:
    """Quantify static-universe contamination and optional benchmark mismatch."""
    prices, membership, benchmark, _ = load_research_inputs(data_dir)
    final = membership.iloc[-1]
    intersection = membership.astype(bool).mul(final.astype(bool), axis=1).sum(axis=1)
    union = membership.astype(bool).add(final.astype(bool), axis=1).astype(bool).sum(axis=1)
    overlap = intersection / union.where(union > 0, np.nan)
    substituted = membership.ne(final, axis=1).sum(axis=1)
    out = {
        "status": "diagnostic_not_causal",
        "static_universe_pit_disagreement_security_months": int(substituted.sum()),
        "mean_membership_jaccard_to_final_universe": _safe_float(overlap.mean()),
        "max_names_with_incorrect_static_eligibility": int(substituted.max()),
        "first_vs_final_membership_disagreement": int(substituted.iloc[0]),
        "warning": "Counts demonstrate exposure to survivorship/eligibility contamination; "
                   "they do not quantify performance bias without a separately valid counterfactual.",
    }
    alternate = data_dir / "benchmark_price_only.csv"
    if alternate.is_file():
        price_reference = read_returns(alternate)
        if not benchmark.index.equals(price_reference.index):
            out["price_only_benchmark"] = {"status": "unavailable", "reason": "Calendar mismatch"}
        else:
            delta = benchmark - price_reference
            out["price_only_benchmark"] = {
                "status": "observed_convention_sensitivity_unverified",
                "mean_monthly_return_difference": _safe_float(delta.mean()),
                "max_absolute_monthly_return_difference": _safe_float(delta.abs().max()),
                "note": "Difference between user-supplied TRI and price-index references, not strategy alpha.",
            }
    else:
        out["price_only_benchmark"] = {
            "status": "unavailable", "missing_input": "benchmark_price_only.csv"}
    month = pd.read_csv(results_dir / "monthly_results.csv")
    net, gross = pd.to_numeric(month.strategy_net), pd.to_numeric(month.strategy_gross)
    out["cost_sensitivity"] = {
        "mean_model_cost_drag_per_month": _safe_float((gross-net).mean()),
        "model_cost_bps": config.cost_bps,
        "note": "Modeled internal transaction cost, not observed broker fills.",
    }
    return out


def inference_for_final_holdout(run_dir: Path, config: ExperimentConfig) -> dict:
    monthly = pd.read_csv(run_dir / "monthly_results.csv", parse_dates=["date"])
    if not config.final_test_start:
        return {"status": "unavailable", "reason": "No frozen final test start"}
    final = monthly[monthly.date >= pd.Timestamp(config.final_test_start)]
    active = (final.strategy_net-final.benchmark).reset_index(drop=True)
    if len(active) < 12:
        return {"status": "unavailable", "reason": "Fewer than 12 final holdout months"}
    try:
        hac = newey_west_ols(active)
        bootstrap = moving_block_bootstrap_mean(active, block_length=min(6, len(active)),
                                                 resamples=500, seed=2026)
        return {
            "status": "exploratory_not_selection_corrected",
            "final_holdout_months": len(active),
            "annualized_arithmetic_active_return": _safe_float(active.mean()*12),
            "hac_alpha_monthly": _safe_float(hac.coefficients["alpha"]),
            "hac_alpha_normal_approx_p": _safe_float(hac.p_values_normal_approx["alpha"]),
            "bootstrap_mean_monthly_confidence_interval": [
                _safe_float(bootstrap["ci_lower"]), _safe_float(bootstrap["ci_upper"])],
            "warning": "No preregistration timestamp or independent audit was verified; "
                       "p-values do not correct prior model selection.",
        }
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}


def run_studies(data_dir: str | Path, output_dir: str | Path,
                config_path: str | Path) -> dict:
    source = Path(data_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    config = ExperimentConfig(**json.loads(Path(config_path).read_text()))
    readiness = research_preflight(source, config)
    if output.exists():
        raise FileExistsError("Select a new research output folder; existing results are immutable")
    output.mkdir(parents=True)
    (output / "PREFLIGHT.json").write_text(json.dumps(readiness, indent=2, allow_nan=False))
    if not readiness["software_ready"]:
        return {"status": "blocked", "preflight": readiness, "output": str(output)}
    run_dir = output / "study_A_index"
    _, meta = run_from_directory(source, run_dir, config)
    findings = {
        "study_A_multi_factor_index": {
            "status": "descriptive_not_independently_audited",
            "metrics_by_split": meta["metrics_by_split"],
            "factor_weights": meta["factor_weights_used"],
            "holdout_inference": inference_for_final_holdout(run_dir, config),
            "limitations": meta["limitations"],
        },
        "study_B_factor_active_risk": study_b(source, run_dir),
        "study_C_robustness_and_data_integrity": study_c(source, run_dir, config),
    }
    manifest = {
        "format": "quantlab-three-studies-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": readiness["classification"],
        "publication_ready": False,
        "external_research_certified": False,
        "preflight": readiness,
        "experiment_config": asdict(config),
        "studies": findings,
        "not_observed_trading_returns": True,
        "warning": "Synthetic/observational research software output; do not claim validated "
                   "NIFTY alpha, excess performance, execution or independent certification.",
    }
    payload = json.dumps(manifest, indent=2, allow_nan=False)
    (output / "THREE_STUDIES_RESULTS.json").write_text(payload + "\n")
    lines = [
        "# QuantLab: three research studies",
        "Evidence class: " + readiness["classification"],
        "External audit: NOT COMPLETED; this package is not certification.",
        "## Study A: Multi-factor index construction",
        "Predeclared split dates from configuration: validation=" +
        str(config.validation_start) + ", final=" + str(config.final_test_start),
        "Numeric results: THREE_STUDIES_RESULTS.json; full detailed run: study_A_index.",
        "## Study B: Ex-ante common-factor and security-specific active risk",
        "Status: " + findings["study_B_factor_active_risk"]["status"],
        "Requires factor_returns.csv and complete dated benchmark_weights.csv.",
        "## Study C: robustness and research data integrity",
        "Status: " + findings["study_C_robustness_and_data_integrity"]["status"],
        "Universe mismatch is diagnostic, NOT quantified survivorship alpha.",
        "## Reproduction",
        "Run using the SAME local input data, exact configuration, and checksums.",
        "No licensed source observations are included in this publication ZIP.",
        "## Publication and hiring claims",
        "Do not describe returns as independently validated until source licensing, "
        "official PIT notices, dividend/TRI reconciliation, final holdout review and "
        "an independent review record are attached.",
    ]
    (output / "RESEARCH_MEMO.md").write_text("\n\n".join(lines) + "\n")
    bundle = output / "PUBLICATION_SAFE_EVIDENCE.zip"
    with ZipFile(bundle, "w", ZIP_DEFLATED) as z:
        for name in ("PREFLIGHT.json", "THREE_STUDIES_RESULTS.json", "RESEARCH_MEMO.md"):
            z.write(output / name, arcname=name)
    return {"status": "exploratory_complete_not_certified",
            "studies": {name: v["status"] for name, v in findings.items()},
            "preflight": readiness, "output": str(output), "bundle": str(bundle)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--config", default="config/research_multifactor.json")
    p.add_argument("--output-dir", default="results/three_studies")
    p.add_argument("--execute", action="store_true",
                   help="Run studies on local inputs; otherwise inspect prerequisites only")
    args = p.parse_args(argv)
    try:
        config = ExperimentConfig(**json.loads(Path(args.config).read_text()))
        report = (run_studies(args.data_dir, args.output_dir, args.config)
                  if args.execute else research_preflight(args.data_dir, config))
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if (report.get("status") != "blocked" and
                     (report.get("software_ready", True))) else 2
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("Research run blocked: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
