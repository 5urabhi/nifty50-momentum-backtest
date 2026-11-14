#!/usr/bin/env python3
"""QuantLab NSE collector: official informational MCP + prepared local exports.

Does not scrape NSE / NSE Indices websites. Original NSE terms prohibit
systematic collection. Prices for research backtesting should continue to use
authorized Dhan APIs and separately approved research-data records.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workstation_api import nse_source_automation as nse, source_completion, service


def _json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False, default=str))


def _tri_status(dataset_id: str) -> dict:
    folder, record = service.dataset_path(dataset_id)
    return {
        "dataset_id": dataset_id,
        "label": record.get("label", dataset_id),
        "kind": record.get("kind"),
        "existing_benchmark": source_completion.existing_benchmark_status(folder),
        "no_new_tri_import_attempted": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect existing TRI, safely import downloaded NSE source "
                    "exports, or make one official NSE MCP informational query. "
                    "No site scraping, batch harvesting or broker orders.")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Check existing datasets / TRI without changing them")
    status.add_argument("--dataset-id", help="Known local data manager dataset ID")
    plan = sub.add_parser("plan", help="Show exact remaining source gaps for one dataset")
    plan.add_argument("--dataset-id", required=True)
    plan.add_argument("--validation-start")
    plan.add_argument("--final-test-start")
    intake = sub.add_parser("intake", help="Prepare already downloaded authorized CSV/ZIP/XLSX/PDF files")
    intake.add_argument("files", nargs="+", type=Path)
    intake.add_argument("--output-root", type=Path,
                        help="Local ignored data output directory (not GitHub)")
    discover = sub.add_parser("mcp-tools",
                              help="Discover official NSE informational MCP tools; no scraping")
    discover.add_argument("--server", choices=tuple(nse.MCP_SERVERS), default="bhavcopy")
    lookup = sub.add_parser("mcp-lookup",
                            help="ONE informational NSE MCP call; never persisted as research data")
    lookup.add_argument("--server", choices=tuple(nse.MCP_SERVERS), default="bhavcopy")
    lookup.add_argument("--tool", required=True, choices=sorted(nse.INFO_TOOLS))
    lookup.add_argument("--args", required=True, help="JSON arguments from mcp-tools inputSchema")
    lookup.add_argument("--ack-informational-use", action="store_true",
                        help="Confirm informational-only lookup, no backtesting or redistribution")
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            if args.dataset_id:
                _json(_tri_status(args.dataset_id))
            else:
                _json({"datasets": [
                    _tri_status(record["id"])
                    for record in service.datasets(include_archived=True)
                    if record["kind"] != "synthetic"
                ], "hint": "If TRI was already imported, select that derived dataset "
                            "rather than uploading a second copy."})
        elif args.command == "plan":
            _json(source_completion.worklist(
                args.dataset_id, validation_start=args.validation_start,
                final_test_start=args.final_test_start))
        elif args.command == "intake":
            _json(nse.intake_local_exports(args.files, root=args.output_root))
        elif args.command == "mcp-tools":
            with nse.NSEInfoMCP(args.server) as client:
                client.initialize()
                _json({"server": args.server, "tools": client.tools(),
                       "use": "informational_only",
                       "historical_scope": "5 years stated by NSE, not a full 2014+ record"})
        elif args.command == "mcp-lookup":
            if not args.ack_informational_use:
                parser.error("Explicitly pass --ack-informational-use. "
                             "This is not a market-data backtest license.")
            arguments = json.loads(args.args)
            if not isinstance(arguments, dict):
                parser.error("--args must be a JSON object")
            with nse.NSEInfoMCP(args.server) as client:
                client.initialize()
                _json({"server": args.server, "tool": args.tool,
                       "status": "informational_only_not_source_certified",
                       "result": client.one_lookup(args.tool, arguments)})
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("NSE source action blocked: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
