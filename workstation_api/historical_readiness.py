"""Fail-closed local historical research readiness and source compatibility.

This is structural validation of user's original files, not third-party market
data authentication, NSE approval, or legal/licensing review. Independent
review is always a separate human task. No missing observation is imputed.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import hashlib
import json
import math
import re

import numpy as np
import pandas as pd

from index_research.data import read_matrix, read_membership, read_returns, read_fundamentals
from index_research.total_returns import read_actions, PRICE_BASES
from index_research.empirical_validation import evidence_gate
from . import service

SOURCE_FILES = (
    "prices.csv", "membership.csv", "benchmark.csv", "fundamentals.csv",
    "sectors.csv", "corporate_actions.csv", "PIT_MEMBERSHIP_PROVENANCE.json",
    "BENCHMARK_PROVENANCE.json", "BENCHMARK_SOURCE.json",
    "RETURN_METHODOLOGY.json", "EVIDENCE_REVIEW.json",
    "FUNDAMENTAL_METHODS.json", "DAILY_AGGREGATION_PROVENANCE.json",
)
HASH = re.compile(r"^[a-f0-9]{64}$")
STATUS = frozenset({"pass", "review", "blocked", "not_applicable"})


def sha256(file: Path) -> str:
    if file.is_symlink() or not file.is_file():
        raise ValueError("Unsafe or unavailable evidence input: " + file.name)
    h = hashlib.sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_hashes(folder: Path) -> dict[str, str]:
    """Pin all relevant source inputs and provenance, not mutable result files."""
    values = {}
    for name in SOURCE_FILES:
        p = folder / name
        if p.exists() or p.is_symlink():
            values[name] = sha256(p)
    return values


def _json(folder: Path, name: str) -> dict:
    path = folder / name
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, ValueError):
        return {}


def _check(name: str, status: str, detail: str, next_action: str = "") -> dict:
    if status not in STATUS:
        raise ValueError("Invalid audit status")
    return {"name": name, "status": status, "detail": detail, "next_action": next_action}


def _pit_reconcile(folder: Path, prices: pd.DataFrame,
                   membership: pd.DataFrame) -> tuple[str, str]:
    proof = _json(folder, "PIT_MEMBERSHIP_PROVENANCE.json")
    if not proof:
        return "blocked", ("No pinned effective-date PIT membership manifest. "
                           "A current ticker list cannot establish prior constituents.")
    intervals = proof.get("intervals")
    if not isinstance(intervals, list) or not intervals or len(intervals) > 4000:
        return "blocked", "PIT manifest lacks a bounded effective-date interval history"
    payload = json.dumps(intervals, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(payload).hexdigest() != proof.get("intervals_sha256"):
        return "blocked", "PIT interval snapshot digest does not match stored evidence"
    if not HASH.fullmatch(str(proof.get("source_sha256", ""))):
        return "blocked", "PIT source checksum missing or malformed"
    commit = str(proof.get("source_commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        return "blocked", "PIT source is not pinned to an immutable commit"
    coverage = proof.get("covered_through")
    try:
        max_date = pd.Timestamp(date.fromisoformat(str(coverage)))
    except (TypeError, ValueError):
        return "blocked", "PIT source lacks an explicit coverage-through date"
    if prices.index.max().normalize() > max_date:
        return "blocked", "Price history extends beyond the PIT source's verified coverage window"
    missing = proof.get("missing_historical_symbols", [])
    if not isinstance(missing, list) or missing:
        return "blocked", "Historical renamed/delisted securities unresolved: " + str(len(missing) if isinstance(missing, list) else "?")
    if proof.get("missing_eligible_price_observations", 0):
        return "blocked", "PIT source records missing eligible price observations"
    by_ticker: dict[str, list[tuple[pd.Timestamp, pd.Timestamp | None]]] = {}
    for r in intervals:
        if not isinstance(r, dict) or not all(k in r for k in ("symbol", "valid_from", "valid_to")):
            return "blocked", "Malformed PIT source interval"
        try:
            from_date = pd.Timestamp(date.fromisoformat(str(r["valid_from"])))
            until = pd.Timestamp(date.fromisoformat(str(r["valid_to"]))) if r["valid_to"] else None
        except (TypeError, ValueError):
            return "blocked", "PIT effective dates are invalid"
        if until is not None and until <= from_date:
            return "blocked", "PIT source has nonpositive membership interval"
        by_ticker.setdefault(str(r["symbol"]), []).append((from_date, until))
    expected_names = set(by_ticker)
    if expected_names - set(prices.columns):
        return "blocked", "Price file omits securities appearing in pinned historical membership"
    if set(prices.columns) - expected_names:
        return "blocked", "Price file has tickers with no pinned PIT interval"
    for ticker, ranges in by_ticker.items():
        prior = None
        for start, stop in sorted(ranges, key=lambda x: x[0]):
            if prior is not None and start < prior:
                return "blocked", "Overlapping PIT membership events: " + ticker
            prior = stop if stop is not None else pd.Timestamp("2262-01-01")
        expected = pd.Series(False, index=prices.index)
        for start, stop in ranges:
            expected |= (prices.index >= start) & ((prices.index < stop) if stop is not None else True)
        actual = membership[ticker]
        if not np.array_equal(actual.to_numpy(dtype=bool), expected.to_numpy(dtype=bool)):
            return "blocked", "PIT membership.csv disagrees with pinned effective-date source for " + ticker
    # Cardinality of the actual index is a separate check: a complete
    # internally consistent five-security subset is not a complete NIFTY 50.
    index_id = proof.get("index_id")
    if index_id in {"nifty50_pit", "banknifty_pit"}:
        for dt in prices.index:
            observed = int(membership.loc[dt].sum())
            if index_id == "nifty50_pit":
                expected_count = 50
            elif dt >= pd.Timestamp("2025-12-31"):
                expected_count = 14
            elif dt >= pd.Timestamp("2020-03-27"):
                expected_count = 12
            else:
                expected_count = None
            if expected_count is not None and observed != expected_count:
                return "blocked", (f"Incomplete {index_id} membership on {dt.date()}: "
                                   f"{observed} observed, expected {expected_count}. "
                                   "Missing historical price tickers cannot be dropped.")
    return "review", ("Membership states match the pinned intervals for every observed month. "
                      "Underlying reconstructed index notices are not NSE-certified.")


def inspect(dataset_id: str, *, validation_start: str | None = None,
            final_test_start: str | None = None,
            selected_factors: list[str] | None = None) -> dict:
    """Read-only, multi-layer source audit with actionable blockers.

    `structural_run_ready` allows exploratory computation; publication or
    independent market-data certification is NEVER granted automatically.
    """
    folder, record = service.dataset_path(dataset_id)
    checks: list[dict] = []
    def add(name: str, status: str, detail: str, next_action: str = ""):
        checks.append(_check(name, status, detail, next_action))

    source_hashes_now = source_hashes(folder)
    kind = record.get("kind", "unknown")
    synthetic = kind == "synthetic" or (folder / "DO_NOT_CITE.txt").exists()
    add("Real historical source", "blocked" if synthetic else "review",
        "Synthetic demonstration: not NSE/Dhan market evidence" if synthetic else
        "Local observed dataset; source authority, completeness and licensing require review",
        "Choose original licensed market inputs rather than synthetic fixtures" if synthetic
        else "Attach original source URLs, download timestamps and permitted license evidence")

    prices: pd.DataFrame | None = None
    membership: pd.DataFrame | None = None
    benchmark: pd.Series | None = None
    for name, label in (("prices.csv", "Monthly price panel"),
                        ("membership.csv", "Effective-date constituent states"),
                        ("benchmark.csv", "Paired benchmark returns")):
        if name not in source_hashes_now:
            add(label, "blocked", name + " missing", "Prepare this exact original-data artifact")
            continue
        try:
            if name == "prices.csv":
                prices = read_matrix(folder / name, positive=True)
                add(label, "pass", f"{len(prices)} rows, {len(prices.columns)} securities; no missing prices created")
            elif name == "membership.csv":
                if prices is None:
                    raise ValueError("Price panel must be valid before eligibility reconciliation")
                membership = read_membership(folder / name, prices.index, prices.columns)
                add(label, "pass", f"Reconstructed {int(membership.to_numpy().sum())} eligible security/month states")
            elif name == "benchmark.csv":
                benchmark = read_returns(folder / name)
                if prices is None or not prices.index.equals(benchmark.index):
                    raise ValueError("Benchmark and price dates differ; no automatic calendar imputation")
                add(label, "pass", "Benchmark has one finite, >−100% return on each observed price month")
        except (ValueError, TypeError, KeyError, OSError) as exc:
            add(label, "blocked", str(exc), "Repair and re-import original data")

    if prices is not None and membership is not None:
        state, detail = _pit_reconcile(folder, prices, membership)
        add("Point-in-time source reconciliation", state, detail,
            "Import source-dated NSE notices/immutable PIT intervals and resolve renamed/delisted securities")
        # A currently eligible security needs both an observed close and a
        # valid forward return. The final decision has no next month to compare.
        missing = membership & (prices.isna() | ~np.isfinite(prices))
        forward = prices.shift(-1).div(prices).sub(1)
        missing_forward = (membership & ~np.isfinite(forward)).iloc[:-1]
        count = int(missing.to_numpy().sum()) + int(missing_forward.to_numpy().sum())
        add("Eligible price and forward-return coverage", "pass" if count == 0 else "blocked",
            f"Eligible missing price/forward-return cells: {count}",
            "Download actual missing historical securities and exit/delisting observations")
    else:
        add("Point-in-time source reconciliation", "blocked", "Cannot check PIT without valid prices and member states")
        add("Eligible price and forward-return coverage", "blocked", "Cannot check eligible forward returns")

    benchmark_proof = _json(folder, "BENCHMARK_PROVENANCE.json")
    bench_manifest = _json(folder, "BENCHMARK_SOURCE.json")
    benchmark_kind = str(benchmark_proof.get("basis", ""))
    is_tri = bool(benchmark_proof.get("is_total_return_index"))
    return_convention = bench_manifest.get("return_convention")
    if (benchmark is None or not is_tri or return_convention not in
            {"gross_total_return", "net_total_return"} or
            not HASH.fullmatch(str(bench_manifest.get("source_sha256", "")))):
        add("Total-return benchmark provenance", "blocked",
            "Official TRI source levels, matching return convention or provenance hash are absent; a Dhan spot index is not TRI",
            "Import an original licensed NSE Indices TRI levels CSV through Data Library")
    else:
        match = (bench_manifest.get("return_convention") == benchmark_proof.get("return_convention")
                 and bench_manifest.get("index_name") == benchmark_proof.get("index_name"))
        pit = _json(folder, "PIT_MEMBERSHIP_PROVENANCE.json")
        declared_index = str(pit.get("index_name", "")).lower().replace(" ", "")
        benchmark_index = str(bench_manifest.get("index_name", "")).lower().replace(" ", "")
        wrong_index = bool(declared_index and
                           (("bank" in declared_index) != ("bank" in benchmark_index)))
        add("Total-return benchmark provenance", "review" if match and not wrong_index else "blocked",
            "TRI source metadata and aligned monthly returns are structurally consistent; issuer still requires independent verification"
            if match and not wrong_index else "TRI source convention/index is inconsistent with benchmark or PIT index",
            "Obtain original issuer TRI levels and resolve the convention/index mismatch")
    actions_path = folder / "corporate_actions.csv"
    method = _json(folder, "RETURN_METHODOLOGY.json")
    if not actions_path.is_file() or actions_path.is_symlink():
        add("Corporate-action return parity", "blocked",
            "No source-dated split/bonus/dividend/delisting ledger is present",
            "Import verified event records and generate dividend-reinvested wealth indices")
    else:
        try:
            actions = read_actions(actions_path)
            price_basis = method.get("price_basis")
            supported = price_basis in PRICE_BASES and bool(method.get("dividend_adjustment"))
            if not supported:
                raise ValueError("No documented adjustment basis and dividend reinvestment methodology")
            add("Corporate-action return parity", "review",
                f"{len(actions)} locally checked events; basis={price_basis}. Ledger completeness and vendor adjustment policy are NOT externally verified.",
                "Reconcile every ex-date, dividend and historical delisting from primary notices; do not interpret an empty ledger as no events")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            add("Corporate-action return parity", "blocked", str(exc),
                "Correct original action evidence and rerun total-return normalization")

    factors = set(selected_factors or []) & {"value", "quality", "size", "yield"}
    if factors:
        path = folder / "fundamentals.csv"
        if not path.is_file() or path.is_symlink():
            add("Publication-vintage fundamentals", "blocked",
                "Selected factors require publication-dated fundamentals.csv",
                "Import original first-publication filing records with as-of timestamps")
        else:
            try:
                published = read_fundamentals(path)
                if not factors.issubset(published.columns):
                    raise ValueError("Missing selected published fundamental factor columns")
                if published[list(factors)].notna().sum().min() < 2:
                    raise ValueError("Fewer than two historical observations for a selected factor")
                add("Publication-vintage fundamentals", "review",
                    f"{len(published)} first-availability-dated records; source releases still need independent verification",
                    "Inspect filing identifiers, revisions and official publication timestamps")
            except (ValueError, OSError, KeyError) as exc:
                add("Publication-vintage fundamentals", "blocked", str(exc))
    else:
        add("Publication-vintage fundamentals", "not_applicable",
            "No filing-based factor selected for this readiness check")

    timing = {"validation_start": validation_start, "final_test_start": final_test_start,
              "months_before_validation": None, "months_in_final_test": None,
              "preferred_train_months": 44, "minimum_test_months": 12}
    if not validation_start or not final_test_start or prices is None:
        add("Chronological frozen test design", "blocked",
            "Choose a validation start and later final-test start; both must have saved observed months",
            "Choose explicit dates before evaluating, with >=44 prevalidation months and >=12 final-test return months")
    else:
        try:
            a, b = pd.Timestamp(date.fromisoformat(validation_start)), pd.Timestamp(date.fromisoformat(final_test_start))
            if a >= b:
                raise ValueError("Validation must start before final test")
            decisions = prices.index
            train = int((decisions < a).sum())
            valid = int(((decisions >= a) & (decisions < b)).sum())
            # Each final-test month needs a preceding actual observation;
            # the exact realized test returns depend on the backtest's warmup.
            test = int((decisions >= b).sum())
            timing.update({"months_before_validation": train,
                           "months_in_validation": valid, "months_in_final_test": test})
            if train < 44 or valid < 1 or test < 12:
                raise ValueError(f"Need >=44 train months, >=1 validation month and >=12 final months (found {train}/{valid}/{test})")
            add("Chronological frozen test design", "pass",
                f"Locally declared chronological {train}/{valid}/{test} month train/validation/final windows",
                "Freeze inputs/config BEFORE evaluating; never tune on final-test returns")
        except (TypeError, ValueError) as exc:
            add("Chronological frozen test design", "blocked", str(exc),
                "Extend observations and choose valid training, validation and final dates")

    review_declaration = folder / "EVIDENCE_REVIEW.json"
    if review_declaration.is_file() and not review_declaration.is_symlink():
        try:
            declared = evidence_gate(folder, review_declaration)
            complete = declared["status"] != "BLOCKED"
            description = ("Human declarations present but third-party cross-check not performed"
                           if complete else "Human review has missing evidence: " +
                           ", ".join((declared["missing_input_files"] +
                                      declared["missing_declarations"] +
                                      declared["unchecked_review_flags"])[:10]))
        except (ValueError, TypeError, OSError, KeyError) as exc:
            complete = False
            description = str(exc)
        add("Independent original-source and licensing review",
            "review" if complete else "blocked", description,
            "Have an independent reviewer reconcile original issuer files, events, market calendar and data rights")
    else:
        add("Independent original-source and licensing review", "blocked",
            "No signed, source-linked independent EVIDENCE_REVIEW.json",
            "Arrange independent original-source, licensing and dividend/PIT verification")

    critical = {"Monthly price panel", "Effective-date constituent states",
                "Paired benchmark returns", "Eligible price and forward-return coverage",
                "Chronological frozen test design"}
    structural_run_ready = not synthetic and all(
        c["status"] == "pass" for c in checks if c["name"] in critical)
    review_items = [c for c in checks if c["status"] in {"review", "blocked"}]
    return {
        "dataset_id": dataset_id, "dataset_kind": kind,
        "status": "software_structurally_ready_unverified" if structural_run_ready else "incomplete_source_or_timing",
        "structural_run_ready": structural_run_ready,
        "independent_source_certified": False,
        "publication_certified": False,
        "checks": checks, "timing": timing,
        "source_hashes": source_hashes_now,
        "missing_source_actions": [{"name": c["name"], "status": c["status"],
                                     "action": c["next_action"]} for c in review_items],
        "warning": "Local structural and hash tests are NOT an independent source audit. "
                   "Source declarations cannot certify original financial data or licensing.",
    }
