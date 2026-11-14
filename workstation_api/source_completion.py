"""Actionable original-source worklist for a LOCAL QuantLab research dataset.

Read-only. It never calls a market vendor, invents prices, treats checkmarks as
independent verification, or writes/repackages original licensed observations.
A ZIP contains only missing-row identifiers, checksums, and source instructions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from io import BytesIO, StringIO
from zipfile import ZipFile, ZIP_DEFLATED
import csv
import json

from index_research.evidence_coverage import inspect_empirical_coverage
import pandas as pd
from . import historical_readiness, service

MAX_EXPORT_ROWS = 200_000
PREVIEW_ROWS = 40
FACTOR_NAMES = frozenset({"momentum", "low_volatility", "value", "quality", "size", "yield"})

# URLs are only official acquisition STARTING POINTS. Browsing does not grant
# data access, financial index creation, publication or redistribution rights.
NSE_RESEARCH = "https://www.nseindia.com/static/research/initiatives-data-for-research"
INDEX_HISTORY = "https://www.niftyindices.com/reports/historical-data"
INDEX_NOTICES = "https://www.niftyindices.com/Press_Release"
ACTION_ARCHIVE = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
FILING_ARCHIVE = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
EQUITY_HISTORY = "https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives"
WEIGHT_ARCHIVE = "https://niftyindices.com/reports/monthly-reports"

# Public archive pages can be browsed now, while requested research exports
# and granular Data Room access require different approval processes.
# 'public_page' is NOT a claim of unrestricted historical coverage or
# authorization to derive/distribute an investable NSE-based index.
PUBLIC_SOURCE_GUIDE = (
    {
        "key": "official_tri", "priority": 1,
        "name": "Official NIFTY 50 total-return index levels",
        "access": "public_page",
        "official_url": INDEX_HISTORY,
        "page_action": "Total returns Index Values → NIFTY 50 → dates → CSV",
        "quantlab_action": "Import the unchanged CSV as a TRI benchmark in Data Library. "
                           "Include the observed level before the first research return.",
        "route": "data",
        "limitations": "Spot index OHLCV is not TRI. Import requires real stock prices "
                       "and historical membership; benchmark use rights remain separate.",
    },
    {
        "key": "monthly_weights", "priority": 2,
        "name": "NIFTY constituent weights / market-capitalisation archives",
        "access": "public_page",
        "official_url": WEIGHT_ARCHIVE,
        "page_action": "Market Capitalisation, Weightage, Beta → choose month → ZIP",
        "quantlab_action": "Preserve each original ZIP/CSV and its report month. "
                           "Import historical weights with a source-date and publication-time manifest.",
        "route": "data",
        "limitations": "Monthly snapshots do not replace the actual effective-date "
                       "index inclusion/removal notices.",
    },
    {
        "key": "exchange_bhavcopy", "priority": 3,
        "name": "NSE equity Bhavcopy and security price/volume archives",
        "access": "public_page",
        "official_url": "https://www.nseindia.com/all-reports",
        "page_action": "Equities → CM-UDiFF Common Bhavcopy Final (ZIP) "
                       "or historical security-wise price/volume",
        "quantlab_action": "Keep the original exchange report alongside Dhan candles "
                           "to reconcile close, volume and historical symbol identity.",
        "route": "dhan",
        "limitations": "Bhavcopy close is an unadjusted trade price, not a "
                       "dividend-adjusted wealth series; format changes across eras.",
    },
    {
        "key": "index_notices", "priority": 4,
        "name": "Historical index reconstitution notices",
        "access": "public_page",
        "official_url": INDEX_NOTICES,
        "page_action": "Find the dated NIFTY 50 index inclusion/removal announcements",
        "quantlab_action": "Confirm effective dates, old names and delisted identities "
                           "against the reconstructed point-in-time membership.",
        "route": "data",
        "limitations": "A current membership list must never be backfilled over "
                       "older eligibility periods.",
    },
    {
        "key": "corporate_actions", "priority": 5,
        "name": "Original equity corporate actions",
        "access": "public_page",
        "official_url": ACTION_ARCHIVE,
        "page_action": "Search historical issuer actions by symbol and ex-date",
        "quantlab_action": "Prepare a sourced actions ledger with the true ex-date, "
                           "dividend cash, split/bonus and terminal outcomes.",
        "route": "data",
        "limitations": "Do not assume missing events equal no dividends or no delistings.",
    },
    {
        "key": "financial_filings", "priority": 6,
        "name": "Publication-dated company financial statements",
        "access": "public_page",
        "official_url": FILING_ARCHIVE,
        "page_action": "Retrieve actual historical filed results and publication dates",
        "quantlab_action": "Record the first-known date of each fundamentals vintage; "
                           "never apply revised present-day values to past decisions.",
        "route": "data",
        "limitations": "Original filed reports need normalization and as-of review.",
    },
    {
        "key": "research_data_request", "priority": 7,
        "name": "NSE Data for Research application",
        "access": "application_required",
        "official_url": NSE_RESEARCH,
        "page_action": "Complete the Data Seeking Request Form and submit to EPR",
        "quantlab_action": "Request authorized long history, delisted coverage, "
                           "research use rights and approval for derived results.",
        "route": "application",
        "limitations": "Academic/noncommercial research eligibility, costs, "
                       "confidentiality and index-creation restrictions apply.",
    },
    {
        "key": "data_room", "priority": 8,
        "name": "NSE Data for Analytics / NSE Data Room",
        "access": "grant_review",
        "official_url": "https://betanseapi.nseindia.com/static/research/initiatives-data-for-analytics",
        "page_action": "Read the NSE Data Room guidelines and contact the EPR team",
        "quantlab_action": "A separate research proposal may enable granular "
                           "microstructure and liquidity research inside a controlled environment.",
        "route": "application",
        "limitations": "This is not an immediate downloadable history feed; "
                       "access is reviewed and time-bound.",
    },
)

SOURCE_GUIDANCE = {
    "Real historical source":
        ("prices.csv", "dhan", EQUITY_HISTORY, "Use authorized original price records; verify identity and data rights."),
    "Monthly price panel":
        ("prices.csv", "dhan", EQUITY_HISTORY, "Prepare real month-end stock observations from covered historical identities."),
    "Effective-date constituent states":
        ("membership.csv", "import", INDEX_NOTICES, "Supply issuer-dated inclusions, exits and symbol aliases."),
    "Paired benchmark returns":
        ("benchmark.csv", "import", INDEX_HISTORY, "Import an official TRI level series including the prior close."),
    "Point-in-time source reconciliation":
        ("PIT_MEMBERSHIP_PROVENANCE.json", "import", INDEX_NOTICES,
         "Cross-check every effective-date entry and historical delisted identifier."),
    "Eligible price and forward-return coverage":
        ("prices.csv / corporate_actions.csv", "dhan", EQUITY_HISTORY,
         "Fetch missing historical closes and separately source exit and dividend payoffs."),
    "Total-return benchmark provenance":
        ("BENCHMARK_SOURCE.json", "import", INDEX_HISTORY,
         "Use actual NIFTY TRI, not a Dhan spot-index candle or assumed return."),
    "Corporate-action return parity":
        ("corporate_actions.csv", "import", ACTION_ARCHIVE,
         "Verify every ex-date, split, dividend and historical delisting payment."),
    "Publication-vintage fundamentals":
        ("fundamentals.csv", "import", FILING_ARCHIVE,
         "Use first-publication dates and documented revisions, not current restatements."),
    "Chronological frozen test design":
        ("historical date range / configuration", "dhan", EQUITY_HISTORY,
         "Extend genuine observations, leave the final test untouched and meet the +20% train buffer."),
    "Independent original-source and licensing review":
        ("EVIDENCE_REVIEW.json", "review", NSE_RESEARCH,
         "Obtain data use rights and a separate human review of original issuer evidence."),
}


def existing_benchmark_status(folder: Path) -> dict:
    """Inspect a prior TRI upload without requesting or creating a second one."""
    bench = folder / "benchmark.csv"
    result = {
        "state": "missing", "is_tri": False, "independently_verified": False,
        "monthly_returns": None, "first_month": None, "last_month": None,
        "source_sha256": None, "dataset_benchmark_sha256": None,
        "next_action": "Import an official TRI level file only if no TRI exists.",
    }
    if not bench.is_file() or bench.is_symlink():
        return result
    if bench.stat().st_size > 20 * 1024 * 1024:
        return {**result, "state": "invalid", "next_action": "Review oversized benchmark.csv"}
    result["dataset_benchmark_sha256"] = sha256(bench.read_bytes()).hexdigest()
    try:
        frame = pd.read_csv(bench)
        dates = pd.to_datetime(frame["date"], errors="raise")
        values = pd.to_numeric(frame["return"], errors="raise")
        if (frame.empty or dates.isna().any() or dates.duplicated().any()
                or values.isna().any() or not dates.is_monotonic_increasing):
            raise ValueError("Invalid benchmark dates or returns")
        result["monthly_returns"] = len(frame)
        result["first_month"] = dates.iloc[0].date().isoformat()
        result["last_month"] = dates.iloc[-1].date().isoformat()
        result["state"] = "benchmark_present_type_unverified"
        result["next_action"] = "Inspect benchmark source metadata before assuming TRI."
    except (OSError, ValueError, KeyError, TypeError):
        result["state"] = "invalid"
        result["next_action"] = "Repair invalid benchmark.csv without overwriting the original."
        return result
    provenance = {}
    for filename in ("BENCHMARK_PROVENANCE.json", "BENCHMARK_SOURCE.json"):
        file = folder / filename
        if file.is_symlink() or not file.is_file() or file.stat().st_size > 80_000:
            continue
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                provenance.update(payload)
        except (OSError, ValueError, TypeError):
            continue
    result["source_sha256"] = provenance.get("source_sha256")
    declared_tri = (
        provenance.get("is_total_return_index") is True
        and provenance.get("return_convention") in {"gross_total_return", "net_total_return"}
    ) or (
        provenance.get("return_convention") in {"gross_total_return", "net_total_return"}
        and provenance.get("index_name", "").upper().endswith("TRI")
    )
    if declared_tri:
        result.update({
            "state": "tri_present_source_unverified", "is_tri": True,
            "next_action": "TRI already imported. Do not upload it again. Check that "
                           "its actual observed months cover the entire research interval.",
        })
    elif provenance.get("is_total_return_index") is False:
        result.update({
            "state": "price_index_only",
            "next_action": "A price index cannot substitute for an official TRI.",
        })
    # Never promote a locally uploaded user file to independently certified.
    return result


def linked_tri_versions(dataset_id: str) -> list[dict]:
    """Find already-created TRI child versions for a selected original dataset.

    The documented TRI import creates a new immutable upload view with
    workstation_source.json.parent_dataset_id; it must not be mistaken for
    a missing benchmark simply because the user selected its original parent.
    """
    linked = []
    for record in service.datasets(include_archived=True)[:200]:
        child_id = str(record.get("id", ""))
        if child_id == dataset_id or not child_id.startswith("upload_"):
            continue
        folder, _ = service.dataset_path(child_id)
        manifest = folder / "workstation_source.json"
        if (manifest.is_symlink() or not manifest.is_file()
                or manifest.stat().st_size > 80_000):
            continue
        try:
            parsed = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict) or parsed.get("parent_dataset_id") != dataset_id:
                continue
            receipt = existing_benchmark_status(folder)
            if receipt["is_tri"]:
                linked.append({
                    "dataset_id": child_id,
                    "label": record.get("label", child_id),
                    "first_month": receipt["first_month"],
                    "last_month": receipt["last_month"],
                    "monthly_returns": receipt["monthly_returns"],
                    "independently_verified": False,
                })
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return linked[:20]


def _context(dataset_id: str, *, validation_start: str | None = None,
             final_test_start: str | None = None,
             selected_factors: list[str] | None = None) -> tuple[dict, list[dict]]:
    folder, dataset = service.dataset_path(dataset_id)
    selected = selected_factors or []
    if len(selected) > 6 or any(f not in FACTOR_NAMES for f in selected):
        raise ValueError("Unrecognized or excessive selected factor list")
    readiness = historical_readiness.inspect(
        dataset_id, validation_start=validation_start,
        final_test_start=final_test_start, selected_factors=selected)
    coverage = None
    missing_rows: list[dict] = []
    coverage_error = None
    if (folder / "prices.csv").is_file() and not (folder / "prices.csv").is_symlink():
        try:
            coverage = inspect_empirical_coverage(folder, {
                "validation_start": validation_start,
                "final_test_start": final_test_start,
                "factor_weights": {f: 1.0 for f in selected},
            })
            missing_rows = coverage.pop("missing_security_observation_rows", [])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            # Fail closed, but keep the user-facing repair worklist reachable.
            # A corrupt price file must not make every source action disappear.
            coverage_error = "Coverage calculation blocked: " + str(exc)[:300]

    actions = []
    for check in readiness["checks"]:
        target, flow, url, advice = SOURCE_GUIDANCE.get(
            check["name"], ("reviewed original evidence", "import", NSE_RESEARCH,
                            "Review the exact data sources and implementation."))
        actions.append({
            "category": check["name"], "status": check["status"],
            "target": target, "flow": flow, "official_source_url": url,
            "why": check["detail"], "next_action": check["next_action"] or advice,
        })
    stage = readiness["timing"]
    preferred = stage.get("preferred_train_months", 44)
    actual = stage.get("months_before_validation")
    # A source worklist is actionable even when a user has not selected dates.
    summary = {
        "price_months": coverage["price_observations"] if coverage else None,
        "price_securities": coverage["securities_in_observed_panel"] if coverage else None,
        "missing_entire_months": len(coverage["missing_entire_months"]) if coverage else None,
        "missing_eligible_prices": coverage["missing_eligible_prices"] if coverage else None,
        "missing_eligible_forward_returns": coverage["missing_eligible_forward_returns"] if coverage else None,
        "unresolved_historical_symbols": len(coverage["unresolved_historical_symbols"]) if coverage else None,
        "benchmark_alignment": coverage["benchmark_alignment"] if coverage else "unavailable",
        "prevalidation_months": actual,
        "preferred_prevalidation_months_with_20pct_buffer": preferred,
        "prevalidation_shortfall_to_buffer": max(0, preferred - actual) if actual is not None else None,
        "final_test_forward_returns": coverage["observed_final_test_months"] if coverage else None,
        "required_final_test_forward_returns": 12,
        "historical_structural_run_ready": readiness["structural_run_ready"],
        "independent_original_source_certified": False,
        "publication_certified": False,
    }
    report = {
        "dataset_id": dataset_id, "dataset_label": dataset.get("label", dataset_id),
        "source_kind": dataset.get("kind", "unknown"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "readiness": readiness, "summary": summary,
        "actions": actions,
        "existing_benchmark": existing_benchmark_status(folder),
        "linked_tri_versions": linked_tri_versions(dataset_id),
        "public_sources": [dict(row) for row in PUBLIC_SOURCE_GUIDE],
        "missing_security_month_count": len(missing_rows),
        "missing_security_month_preview": missing_rows[:PREVIEW_ROWS],
        "missing_calendar_months": coverage["missing_entire_months"] if coverage else [],
        "unresolved_symbols": coverage["unresolved_historical_symbols"] if coverage else [],
        "coverage_warnings": coverage["warnings"] if coverage else [
            coverage_error or "No prepared monthly prices.csv exists to calculate exact historical gaps."],
        "exact_gap_calculation_available": coverage is not None,
        "official_research_access_url": NSE_RESEARCH,
        "downloadable_original_market_data": False,
        "warning": ("This is a local evidence acquisition plan. It does NOT contain any new "
                    "licensed market data, is not an original-source authenticity review, "
                    "and cannot certify investability or publication rights."),
    }
    return report, missing_rows


def worklist(dataset_id: str, *, validation_start: str | None = None,
             final_test_start: str | None = None,
             selected_factors: list[str] | None = None) -> dict:
    """Return bounded UI preview; never leak an entire sensitive dataset."""
    return _context(dataset_id, validation_start=validation_start,
                    final_test_start=final_test_start,
                    selected_factors=selected_factors)[0]


def _safe_cell(value: object) -> str:
    """Prevent CSV formula execution when a worklist opens in a spreadsheet."""
    string = str(value if value is not None else "")
    if string.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + string
    return string


def _csv(fields: list[str], rows: list[dict]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([_safe_cell(row.get(name, "")) for name in fields])
    return stream.getvalue()


def export_zip(dataset_id: str, *, validation_start: str | None = None,
               final_test_start: str | None = None,
               selected_factors: list[str] | None = None) -> bytes:
    """User-triggered source request package; all original input files remain local."""
    report, missing_rows = _context(
        dataset_id, validation_start=validation_start,
        final_test_start=final_test_start, selected_factors=selected_factors)
    if len(missing_rows) > MAX_EXPORT_ROWS:
        raise ValueError("More than 200,000 missing rows. Use the local "
                         "prepare_research_data.py coverage-audit command instead.")
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as pack:
        pack.writestr("SOURCE_WORKLIST.json",
                      json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        pack.writestr("MISSING_SECURITY_MONTHS.csv",
                      _csv(["date", "ticker", "problem"], missing_rows))
        pack.writestr("MISSING_CALENDAR_MONTHS.csv",
                      _csv(["month"], [{"month": x} for x in report["missing_calendar_months"]]))
        pack.writestr("UNRESOLVED_HISTORICAL_IDENTITIES.csv",
                      _csv(["ticker"], [{"ticker": x} for x in report["unresolved_symbols"]]))
        pack.writestr("SOURCE_ACTIONS.csv", _csv(
            ["category", "status", "target", "flow", "official_source_url", "next_action"],
            report["actions"]))
        pack.writestr("OFFICIAL_SOURCE_GUIDE.csv", _csv(
            ["priority", "name", "access", "official_url", "page_action",
             "quantlab_action", "route", "limitations"],
            report["public_sources"]))
        pack.writestr("README.txt",
            "QuantLab Original-Source Worklist\n\n"
            "Read-only, derived missing-evidence identifiers and source checksums.\n"
            "Does NOT include licensed prices, cashflows, market orders or credentials.\n"
            "Never interpret a green structural check as independent certification.\n"
            "NSE research access/application: " + NSE_RESEARCH + "\n"
            "Dhan daily prices do not prove historically correct NIFTY membership,\n"
            "dividends, delisting recovery, original filings or official TRI.\n"
            "Obtain permission before using or redistributing issuer market data.\n"
            "Resolve the source actions and rerun the audit before freezing a test.\n")
    return archive.getvalue()
