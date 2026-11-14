"""In-app NSE MCP informational source checks, never silent research-data imports.

This service is called by the loopback-only FastAPI workstation. It selects
the right official NSE MCP tool for a user task, checks the live tool schema,
handles provider-internal errors, and prevents MCP price-index data from
quietly replacing existing TRI, Dhan prices or audited research inputs.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from threading import Lock
from time import monotonic
import json
import re

import httpx

from . import nse_source_automation as nse

SOURCE_NAME = "NSE Official MCP"
MIN_INTERVAL_SECONDS = 2.0
_LOCK = Lock()
_NEXT_REMOTE_AT = 0.0

TASKS = (
    {"id": "corporate_actions", "name": "Corporate actions", "purpose":
     "Check ex-dated dividends, splits and bonuses for a stock.", "server": "bhavcopy",
     "tool": "get_corporate_actions"},
    {"id": "stock_history", "name": "Stock history", "purpose":
     "Inspect up to 3 months of raw OHLCV and check corporate actions first.",
     "server": "bhavcopy", "tool": "get_stock_history"},
    {"id": "symbol_search", "name": "Find a stock", "purpose":
     "Resolve an NSE symbol from a name or partial ticker.", "server": "bhavcopy",
     "tool": "nse_lookup_symbol"},
    {"id": "index_history", "name": "Index context", "purpose":
     "Inspect official index price levels (NOT a total-return index).",
     "server": "bhavcopy", "tool": "get_index_history"},
)
TASK_INDEX = {row["id"]: row for row in TASKS}
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9&._-]{0,24}$")
INDEX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &()./_-]{1,59}$")
QUERY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &()._-]{1,49}$")


def capabilities() -> dict:
    """Safe to load automatically; no network request or dataset mutation."""
    return {
        "provider": SOURCE_NAME, "configured": True, "connection": "not_checked",
        "tasks": list(TASKS), "authenticated_broker_data_required": False,
        "usage": "informational_and_educational_only",
        "research_data_write_allowed": False,
        "website_scraping_enabled": False,
        "raw_history_is_total_return": False,
        "note": "NSE MCP checks are informational. QuantLab never automatically "
                "replaces your saved TRI, research market data or actual issuer evidence.",
    }


def _limited_request_slot() -> None:
    global _NEXT_REMOTE_AT
    with _LOCK:
        current = monotonic()
        if current < _NEXT_REMOTE_AT:
            raise ValueError("NSE was checked just now. Retry after a moment; "
                             "requests are intentionally throttled.")
        _NEXT_REMOTE_AT = current + MIN_INTERVAL_SECONDS


def _date(value: str, name: str, *, allow_today: bool = False) -> str:
    if value == "today" and allow_today:
        return value
    if not isinstance(value, str) or not value:
        raise ValueError(name + " is required")
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(name + " must be YYYY-MM-DD") from None
    if parsed > date.today() + timedelta(days=1):
        raise ValueError(name + " cannot be in the future")
    return parsed.isoformat()


def _months(value: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise ValueError("Choose 1-" + str(maximum) + " months per NSE lookup")
    return value


def _task_arguments(task: str, details: dict) -> tuple[str, dict, dict | None]:
    """Return primary tool, validated official inputs, and optional CA preflight."""
    if task not in TASK_INDEX:
        raise ValueError("Unknown NSE source task")
    if not isinstance(details, dict):
        raise ValueError("Invalid NSE form inputs")
    if task == "symbol_search":
        term = str(details.get("query", "")).strip()
        if not QUERY_PATTERN.fullmatch(term):
            raise ValueError("Enter 2-50 letters or numbers to find an NSE stock")
        return "nse_lookup_symbol", {"query": term}, None
    if task == "index_history":
        name = str(details.get("index_name", "")).strip()
        if not INDEX_PATTERN.fullmatch(name):
            raise ValueError("Enter a valid NSE index name, such as Nifty 50")
        months = _months(details.get("months", 3), 12)
        end_date = _date(str(details.get("end_date", "today")), "End date", allow_today=True)
        return "get_index_history", {"indexName": name, "months": months,
                                     "endDate": end_date}, None
    symbol = str(details.get("symbol", "")).strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("Enter a valid NSE stock symbol, such as RELIANCE")
    if task == "corporate_actions":
        end = _date(str(details.get("to_date", "today")), "End date", allow_today=True)
        start = details.get("from_date", "")
        start = _date(str(start or (date.today() - timedelta(days=365)).isoformat()),
                      "Start date")
        real_end = date.today() if end == "today" else date.fromisoformat(end)
        if date.fromisoformat(start) > real_end:
            raise ValueError("Start date must not follow end date")
        return "get_corporate_actions", {
            "symbol": symbol, "fromDate": start, "toDate": real_end.isoformat(),
        }, None
    months = _months(details.get("months", 3), 3)
    end = _date(str(details.get("end_date", "today")), "End date", allow_today=True)
    end_dt = date.today() if end == "today" else date.fromisoformat(end)
    start = end_dt - timedelta(days=31 * months)
    return "get_stock_history", {
        "symbol": symbol, "months": months, "endDate": end,
    }, {"symbol": symbol, "fromDate": start.isoformat(), "toDate": end_dt.isoformat()}


def _read_result(raw: dict) -> tuple[object, list[str]]:
    """Fail closed on provider errors in nested text even when isError=false."""
    if not isinstance(raw, dict):
        raise ValueError("NSE MCP returned an unexpected response")
    if raw.get("isError"):
        raise ValueError("NSE MCP reported the lookup failed; this does not mean no data exists")
    messages = []
    warnings: list[str] = []
    if isinstance(raw.get("structuredContent"), dict):
        messages.append(raw["structuredContent"])
    for entry in raw.get("content", []):
        if not isinstance(entry, dict) or entry.get("type") != "text":
            continue
        payload = entry.get("text")
        if not isinstance(payload, str):
            continue
        try:
            decoded = json.loads(payload)
        except (ValueError, TypeError):
            decoded = payload[:10000]
        messages.append(decoded)
    if not messages:
        raise ValueError("NSE MCP returned no usable information; do not assume zero events")
    for item in messages:
        if isinstance(item, dict):
            error = item.get("error")
            if error:
                raise ValueError("NSE MCP could not fetch this source: " + str(error)[:300] +
                                 " The result must remain unavailable, not zero.")
            warning = item.get("warning") or item.get("warnings")
            if warning:
                warnings.append(str(warning)[:500])
    return (messages[0] if len(messages) == 1 else messages), warnings


def run_lookup(task: str, details: dict, *, client_factory=None) -> dict:
    tool, params, actions_params = _task_arguments(task, details)
    _limited_request_slot()
    factory = client_factory or nse.NSEInfoMCP
    warnings: list[str] = []
    action_evidence = None
    try:
        with factory(TASK_INDEX[task]["server"]) as client:
            client.initialize()
            if actions_params is not None:
                # NSE explicitly directs consumers of stock history to check
                # corporate actions. Never treat a failed check as "none".
                try:
                    action_evidence, extra = _read_result(
                        client.one_lookup("get_corporate_actions", actions_params))
                    warnings.extend(extra)
                except (ValueError, httpx.HTTPError) as exc:
                    warnings.append("Corporate-action verification unavailable: " +
                                    str(exc)[:200] +
                                    ". Raw price changes may include splits or dividends.")
            primary, extra = _read_result(client.one_lookup(tool, params))
            warnings.extend(extra)
    except (ValueError, httpx.HTTPError, json.JSONDecodeError) as exc:
        return {
            "status": "provider_unavailable", "task": task,
            "message": str(exc)[:450], "provider": SOURCE_NAME,
            "data": None, "warnings": warnings,
            "research_data_updated": False,
            "no_events_verified": False,
            "suggested_next_step": "Retry later, check an original NSE source report, "
                                   "or use the authorized Dhan downloader for research prices.",
        }
    if task == "index_history":
        warnings.append("This is a PRICE index, not the NIFTY 50 TRI you already imported.")
    if task == "stock_history":
        warnings.append("Raw OHLCV is not a dividend-inclusive research return series.")
    return {
        "status": "available", "task": task, "provider": SOURCE_NAME,
        "data": primary, "corporate_actions_context": action_evidence,
        "warnings": warnings, "checked_utc": datetime.now(timezone.utc).isoformat(),
        "research_data_updated": False, "no_events_verified": False,
        "usage": "informational_and_educational_only",
        "suggested_next_step": "Compare with existing original-source records. "
                               "No backtest inputs or TRI values were changed.",
    }


def check_connection(*, client_factory=None) -> dict:
    _limited_request_slot()
    factory = client_factory or nse.NSEInfoMCP
    try:
        with factory("bhavcopy") as client:
            client.initialize()
            names = {t["name"] for t in client.tools() if t["informational_lookup_only"]}
        return {"status": "connected", "provider": SOURCE_NAME,
                "available_tasks": [row["id"] for row in TASKS if row["tool"] in names],
                "note": "Connection confirmed. Individual sources may still be unavailable."}
    except (ValueError, httpx.HTTPError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "provider": SOURCE_NAME,
                "available_tasks": [],
                "note": "NSE MCP is not reachable: " + str(exc)[:350]}
