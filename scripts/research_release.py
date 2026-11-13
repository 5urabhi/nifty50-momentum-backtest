#!/usr/bin/env python3
"""Prepare a source-accurate QuantLab research release; never auto-certify data.

Run as a local, immutable report workflow. No market-data download, order
submission, secrets export, or automatic independent data approval.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from index_research.data_audit import audit_dataset
from index_research.empirical_validation import evidence_gate
from index_research.experiment import ExperimentConfig
from scripts.complete_research_studies import research_preflight, run_studies, sha

REQUIREMENTS = {
    "prices.csv": ("Corporate-action adjusted wealth levels, including verified dividends and delisting proceeds.", "https://www.nseindia.com/companies-listing/corporate-filings-actions"),
    "membership.csv": ("Effective-dated NSE constituent changes, all historical symbols and original notices.", "https://www.niftyindices.com/Press_Release"),
    "benchmark.csv": ("Official NIFTY 50 TRI closes with a previous-month close and compatible return basis.", "https://www.niftyindices.com/reports/historical-data"),
    "fundamentals.csv": ("As-published NSE financial statements and historical market caps, never future revisions.", "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"),
    "sectors.csv": ("Effective-dated sector identifiers across eligible historical constituents.", "https://www.nseindia.com/static/products-services/indices-nifty50-index"),
    "corporate_actions.csv": ("Original sourced ex-dates, dividends, splits, bonuses and terminal recoveries.", "https://www.nseindia.com/companies-listing/corporate-filings-actions"),
    "benchmark_weights.csv": ("Complete dated benchmark weights, explicitly including zero-weight modeled names.", "https://www.niftyindices.com/reports/historical-data"),
    "factor_returns.csv": ("Independently sourced monthly factor proxy returns for conditional risk attribution.", "https://www.nseindia.com/static/products-services/indices-nifty50-index"),
    "liquidity.csv": ("Dated average daily traded notional and observed half-spreads in portfolio currency.", "https://www.nseindia.com/all-reports"),
    "BENCHMARK_SOURCE.json": ("Official TRI origin, source hash, gross/net return convention and first-level rule.", "https://www.niftyindices.com/reports/historical-data"),
    "RETURN_METHODOLOGY.json": ("Vendor split/bonus policy, dividend adjustments, event and delisting treatment.", "https://www.nseindia.com/static/products-services/indices-faqs"),
    "PIT_MEMBERSHIP_PROVENANCE.json": ("Immutable reconstructed membership feed plus original NSE notice review.", "https://www.niftyindices.com/Press_Release"),
    "EVIDENCE_REVIEW.json": ("Named reviewer, source evidence, data rights, chronology and frozen-holdout review.", "https://www.nseindia.com/static/products-services/indices-faqs"),
}
ALWAYS_REQUIRED = {
    "prices.csv", "membership.csv", "benchmark.csv", "corporate_actions.csv",
    "BENCHMARK_SOURCE.json", "RETURN_METHODOLOGY.json",
    "PIT_MEMBERSHIP_PROVENANCE.json", "EVIDENCE_REVIEW.json",
}


def inspect(data_dir: str | Path, config_path: str | Path) -> dict:
    root = Path(data_dir)
    config = ExperimentConfig(**json.loads(Path(config_path).read_text()))
    pre = research_preflight(root, config)
    required = set(ALWAYS_REQUIRED)
    factors = config.factor_weights or {}
    if any(factors.get(name, 0) > 0 for name in ("value", "quality", "size", "yield")):
        required.add("fundamentals.csv")
    if config.sector_cap is not None:
        required.add("sectors.csv")
    if config.weighting == "benchmark_relative":
        required.add("benchmark_weights.csv")
    if config.liquidity_aum is not None:
        required.add("liquidity.csv")
    rows = []
    for name in sorted(required):
        explanation, official_url = REQUIREMENTS[name]
        present = pre["available_files"].get(name)
        rows.append({
            "file": name, "source_present": bool(present),
            "sha256": present.get("sha256") if present else None,
            "independent_source_verified": False,
            "next_action": explanation, "official_source_start": official_url,
        })
    audit = {"status": "not_run", "reason": "Missing or invalid research inputs"}
    if pre["software_ready"]:
        try:
            measured = audit_dataset(root)
            measured.pop("data_directory", None)
            audit = {"status": "internal_consistency_only", **measured}
        except (ValueError, OSError, KeyError) as exc:
            audit = {"status": "failed", "reason": str(exc)}
    declaration = {"status": "not_submitted"}
    evidence_file = root / "EVIDENCE_REVIEW.json"
    if evidence_file.is_file() and not evidence_file.is_symlink():
        try:
            declaration = evidence_gate(root, evidence_file)
        except (OSError, ValueError, TypeError) as exc:
            declaration = {"status": "invalid", "reason": str(exc)}
    classification = (
        "SYNTHETIC_DEMONSTRATION" if pre["classification"] == "SYNTHETIC_DEMONSTRATION"
        else "BLOCKED" if not pre["software_ready"]
        else "OBSERVED_NOT_INDEPENDENTLY_AUDITED"
    )
    return {
        "format": "quantlab-research-release-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": classification,
        "software_ready": bool(pre["software_ready"]),
        "publication_certified": False,
        "independent_reviewer_certified": False,
        "config": asdict(config),
        "required_sources": rows,
        "missing_sources": [r["file"] for r in rows if not r["source_present"]],
        "preflight": {
            "software_blockers": pre["configuration_blockers"] + pre["missing_core_files"],
            "external_evidence_blockers": pre["external_evidence_blockers"],
            "first_date": pre["first_date"], "last_date": pre["last_date"],
        },
        "data_audit": audit,
        "evidence_declaration_status": declaration.get("status"),
        "evidence_missing_flags": declaration.get("unchecked_review_flags", []),
        "source_sha256": {
            name: info["sha256"] for name, info in pre["available_files"].items()
        },
        "disclosure": "A synthetic pass, file hash, submitted declaration, or "
                      "CI success is NOT independent verification of market data, "
                      "published alpha, benchmark comparability or real fills.",
    }


def _chart(monthly: Path) -> str:
    if not monthly.is_file() or monthly.is_symlink():
        return ""
    frame = pd.read_csv(monthly)
    if not {"strategy_net", "benchmark"}.issubset(frame.columns) or len(frame) < 2:
        return ""
    a = pd.to_numeric(frame["strategy_net"], errors="coerce")
    b = pd.to_numeric(frame["benchmark"], errors="coerce")
    if (a.isna().any() or b.isna().any() or (a <= -1).any() or (b <= -1).any()
            or not np.isfinite(a).all() or not np.isfinite(b).all()):
        return ""
    a, b = (1 + a).cumprod(), (1 + b).cumprod()
    low = min(1.0, a.min(), b.min())
    span = max(1e-9, max(1.0, a.max(), b.max()) - low)
    def points(row):
        return " ".join("%.1f,%.1f" % (
            30 + i * 660 / (len(row) - 1), 220 - 180 * (value - low) / span
        ) for i, value in enumerate(row))
    return (
        '<figure><svg viewBox="0 0 720 250" role="img" '
        'aria-label="Simulated index net wealth and benchmark">'
        '<rect width="720" height="250" fill="#071a2a"/>'
        '<polyline fill="none" stroke="#70deb7" stroke-width="2.5" points="' +
        points(a) + '"/><polyline fill="none" stroke="#ffce80" '
        'stroke-width="2.5" points="' + points(b) + '"/></svg>'
        '<figcaption>Green: simulated index net wealth; gold: benchmark. '
        'Descriptive research, NOT independently certified NIFTY performance.</figcaption></figure>'
    )



def _research_paper(status: dict, findings: dict | None) -> str:
    """Render a source-safe draft using the real computed metrics, if any."""
    cfg = status["config"]
    sections = [
        "# QuantLab: Multi-Factor Equity Index Construction, Active Risk and Data Integrity",
        "**UNREVIEWED RESEARCH PAPER DRAFT — no independent market-data certification.**",
        "## Abstract",
        "We describe a source-aware factor-index methodology, benchmark-relative "
        "risk decomposition and bias/robustness experiments. Software results "
        "alone do not validate historical NIFTY performance.",
        "Empirical outcome availability: " +
        ("descriptive calculations, NOT externally certified" if findings else
         "no empirical findings in this release") + ".",
        "## Research question",
        "Can predeclared factor index rules improve a comparable benchmark "
        "after risk, sector, turnover, capacity and timing assumptions?",
        "## Research protocol (archived JSON)",
        json.dumps(cfg, sort_keys=True, indent=2),
        "This source configuration does not itself prove that the model was "
        "registered before any prior exploration of the final test period.",
        "## Source material, historical time and evidence",
        "| Input | SHA-256 (identity, NOT accuracy) |",
        "| --- | --- |",
    ]
    for name, digest in sorted(status["source_sha256"].items()):
        sections.append("| " + name + " | " + digest + " |")
    sections.extend([
        "Missing source or methodology files: " +
        ", ".join(status["missing_sources"]) + ".",
        "## Index methodology and execution",
        "Cross-sectional as-of factors rank eligible securities; the optimizer "
        "uses specified long-only, maximum-weight, historical sector and "
        "risk/turnover constraints. Factor scores are NOT guaranteed forecasts "
        "of alpha. The delayed execution simulator includes turnover costs "
        "and optional scenario-only spread/impact from genuinely dated liquidity.",
        "## Statistical protocol and limitations",
        "Development, validation and final test are chronologically separated. "
        "Exploratory HAC/bootstrap estimates and Holm adjustments cover only "
        "listed tests, not unknown prior researcher degrees of freedom.",
        "## Study A — Multi-factor index versus documented benchmark",
    ])
    def fmt(x):
        return "%.6g" % x if isinstance(x, (int, float)) else (
            "Unavailable" if x is None else str(x))
    if findings:
        a = findings["studies"].get("study_A_multi_factor_index", {})
        sections.extend([
            "| Split | Months | Index CAGR | Benchmark CAGR | Tracking error | Annual turnover |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for name, values in a.get("metrics_by_split", {}).items():
            sections.append("| " + name + " | " + " | ".join(fmt(values.get(k)) for k in (
                "observations", "strategy_cagr", "benchmark_cagr",
                "tracking_error", "annualized_turnover")) + " |")
        sections.append("Final test inference status: " +
                        str(a.get("holdout_inference", {}).get("status", "not calculated")))
        sections.append("Explicit multiple-testing status: " +
                        str(a.get("exploratory_validation_multiple_testing", {})
                            .get("status", "not calculated")))
        b = findings["studies"].get("study_B_factor_active_risk", {})
        sections.extend([
            "## Study B — Ex-ante factor and specific active-risk estimation",
            "Availability: " + str(b.get("status", "unavailable")),
            "Predicted annualized tracking error: " +
            fmt(b.get("annualized_tracking_error_estimate")),
            "Historical ex-ante risk estimates: " +
            fmt(b.get("historical_ex_ante_estimates")),
            "These are OLS proxy-factor estimates, NOT commercial "
            "risk-model outputs or causal performance attributions.",
        ])
        c = findings["studies"].get("study_C_robustness_and_data_integrity", {})
        sections.extend([
            "## Study C — Research robustness",
            "Historical membership mismatches versus the final universe: " +
            fmt(c.get("static_universe_pit_disagreement_security_months")),
            "Static-universe counterfactual: " +
            str(c.get("static_universe_counterfactual", {}).get("status", "unavailable")),
            "The static-final-constituent experiment intentionally includes "
            "future information and is NOT an investable or causal estimate.",
        ])
    else:
        sections.extend([
            "No authenticated statistical result was available. "
            "Do not populate this section using synthetic market returns.",
            "## Study B — Active risk",
            "Unavailable pending factor and benchmark source records.",
            "## Study C — Robustness",
            "Unavailable pending valid historical inputs.",
        ])
    sections.extend([
        "## Independent review and conflicts",
        "No NSE source notice, dividend-adjustment completeness, historical "
        "filing availability, delisting payoff, research license or actual "
        "execution fill has been independently certified by this pipeline.",
        "The manifest can establish reproducibility of bytes and calculations "
        "only, not the underlying truth of those observations.",
        "## Reproduction",
        "Access identical permitted original data and preserved source "
        "SHA-256s, rerun the same frozen config into a NEW folder, compare "
        "numerical output and secure a separate independent methodological review.",
        "## Conclusions",
        "The platform implements a repeatable index and risk research workflow. "
        "This release does NOT establish independently validated NIFTY alpha "
        "or achievable investment returns.",
    ])
    return "\n\n".join(sections) + "\n"

def generate(data_dir: str | Path, config_path: str | Path,
             output_dir: str | Path, *, execute: bool = False) -> dict:
    """Write immutable status and source-safe HTML/ZIP, optionally run studies."""
    out = Path(output_dir).expanduser()
    if out.exists():
        raise FileExistsError("Output already exists. Research artifacts must be immutable.")
    status = inspect(data_dir, config_path)
    out.mkdir(parents=True)
    run = None
    if execute and status["software_ready"]:
        run = run_studies(data_dir, out / "studies", config_path)
    results_file = out / "studies" / "THREE_STUDIES_RESULTS.json"
    findings = json.loads(results_file.read_text()) if results_file.is_file() else None
    changed = []
    for name, previous in status["source_sha256"].items():
        path = Path(data_dir) / name
        if not path.is_file() or path.is_symlink() or sha(path) != previous:
            changed.append(name)
    status["source_unchanged_after_execution"] = not changed
    status["changed_sources"] = changed
    status["study_execution"] = {
        "requested": bool(execute),
        "status": "source_changed" if changed else
                  run["status"] if run else "blocked" if execute else "not_requested",
        "independent_certification": False,
        "study_statuses": (
            {name: value["status"] for name, value in findings["studies"].items()}
            if findings is not None and not changed else {}
        ),
    }
    if changed:
        findings = None
    (out / "RESEARCH_RELEASE_STATUS.json").write_text(
        json.dumps(status, indent=2, allow_nan=False) + "\n"
    )
    memo = [
        "# QuantLab — Evidence-Gated Research Release",
        "Evidence class: " + status["classification"],
        "Independent historical performance certified: NO",
        "## Source requirements",
    ]
    for row in status["required_sources"]:
        memo.append(
            "- " + row["file"] + ": " +
            ("SOURCE PRESENT, UNVERIFIED" if row["source_present"] else "MISSING") +
            ". " + row["next_action"] + " Source: " + row["official_source_start"]
        )
    memo.extend([
        "## Research-software execution",
        "Readiness: " + str(status["software_ready"]),
        "Data consistency: " + status["data_audit"]["status"],
        "Research execution: " + status["study_execution"]["status"],
        "## Three studies",
    ])
    if findings:
        for name, value in findings["studies"].items():
            memo.append("- " + name + ": " + value["status"] + " (not certified)")
    else:
        memo.append("No empirical study output available in this release.")
    memo.extend([
        "## Independent review required",
        "Check primary NSE membership notices, dividend wealth and TRI equivalence, "
        "first-published fundamentals, delistings, costs, licensing, "
        "pre-registered holdout and unchanged source hashes before public research claims.",
        "Reproduce with the existing scripts/complete_research_studies.py command "
        "and a NEW output folder containing the unchanged original input data.",
    ])
    (out / "RESEARCH_RELEASE_MEMO.md").write_text("\n\n".join(memo) + "\n")
    (out / "RESEARCH_PAPER_DRAFT.md").write_text(_research_paper(status, findings))
    requirements = "".join(
        "<tr><td>" + escape(row["file"]) + "</td><td>" +
        ("Present, unverified" if row["source_present"] else "Missing") + "</td><td>" +
        escape(row["next_action"]) + "</td></tr>" for row in status["required_sources"]
    )
    study_rows = "".join(
        "<tr><td>" + escape(name) + "</td><td>" +
        escape(val["status"]) + "</td></tr>"
        for name, val in findings["studies"].items()
    ) if findings else ""
    chart = _chart(out / "studies" / "study_A_index" / "monthly_results.csv") if findings else ""
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>QuantLab Research Evidence</title>"
        "<style>body{background:#0b1526;color:#f0f6ff;max-width:940px;"
        "margin:auto;padding:36px;font:16px/1.6 system-ui}h1,h2{color:#8adac7}"
        "table{width:100%;border-collapse:collapse}td,th{padding:10px;"
        "border-bottom:1px solid #34465b;text-align:left}svg{width:100%}"
        "aside{padding:20px;background:#5e302d;border-radius:12px}"
        "figcaption{color:#acbed1;font-size:13px}</style></head><body>"
        "<h1>QuantLab · Research Evidence</h1><aside><strong>"
        "Independent financial research certification: NO</strong><br>" +
        escape(status["classification"]) + "</aside>"
        "<h2>Research source audit</h2><table><thead><tr><th>Source</th>"
        "<th>State</th><th>Requirement</th></tr></thead><tbody>" +
        requirements + "</tbody></table><h2>Study results</h2>" +
        ("<table>" + study_rows + "</table>" + chart if findings else
         "<p>Study inputs missing or experiment not requested; no returns asserted.</p>") +
        "<p>See the accompanying RESEARCH_PAPER_DRAFT.md for methodology "
        "and research caveats.</p><p>All outputs require independent review of original sources, "
        "licenses, and a genuinely frozen test period.</p></body></html>"
    )
    (out / "RESEARCH_RELEASE.html").write_text(html)
    with ZipFile(out / "RESEARCH_RELEASE_SAFE.zip", "w", ZIP_DEFLATED) as archive:
        for name in ("RESEARCH_RELEASE_STATUS.json", "RESEARCH_RELEASE_MEMO.md",
                     "RESEARCH_RELEASE.html", "RESEARCH_PAPER_DRAFT.md"):
            archive.write(out / name, arcname=name)
        if findings:
            archive.write(results_file, arcname="THREE_STUDIES_RESULTS.json")
    return {
        "status": "release_report_written_not_certified",
        "software_ready": status["software_ready"],
        "studies_executed": bool(findings),
        "source_unchanged": not changed,
        "publication_certified": False,
        "output": str(out),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default="data/research_v1")
    p.add_argument("--config", default="config/research_multifactor.json")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--execute", action="store_true",
                   help="Run the three source-gated studies when the data permit")
    args = p.parse_args(argv)
    try:
        result = generate(args.data_dir, args.config, args.output_dir, execute=args.execute)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result["software_ready"] and result["source_unchanged"] else 2
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print("Release blocked:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
