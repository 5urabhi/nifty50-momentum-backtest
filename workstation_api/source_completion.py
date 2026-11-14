"""Actionable original-source worklist for a LOCAL QuantLab research dataset.

Read-only. It never calls a market vendor, invents prices, treats checkmarks as
independent verification, or writes/repackages original licensed observations.
A ZIP contains only missing-row identifiers, checksums, and source instructions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO, StringIO
from zipfile import ZipFile, ZIP_DEFLATED
import csv
import json

from index_research.evidence_coverage import inspect_empirical_coverage
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
    if (folder / "prices.csv").is_file() and not (folder / "prices.csv").is_symlink():
        coverage = inspect_empirical_coverage(folder, {
            "validation_start": validation_start,
            "final_test_start": final_test_start,
            "factor_weights": {f: 1.0 for f in selected},
        })
        missing_rows = coverage.pop("missing_security_observation_rows", [])
    else:
        coverage, missing_rows = None, []

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
        "missing_security_month_count": len(missing_rows),
        "missing_security_month_preview": missing_rows[:PREVIEW_ROWS],
        "missing_calendar_months": coverage["missing_entire_months"] if coverage else [],
        "unresolved_symbols": coverage["unresolved_historical_symbols"] if coverage else [],
        "coverage_warnings": coverage["warnings"] if coverage else [
            "No prepared monthly prices.csv exists to calculate exact historical gaps."],
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
