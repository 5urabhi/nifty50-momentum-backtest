"""NSE source acquisition without prohibited website scraping.

Two explicitly separate workflows:
  - Official NSE MCP: bounded single informational queries, never research-data
    backfills, broker orders or automatic writes to QuantLab model inputs.
  - Local authorized exports: immutable intake and manifest generation for
    CSV/ZIP/XLSX/PDF already lawfully obtained by the researcher.

Both NSE and NSE Indices prohibit systematic website scraping. A public
download button is not a research/commercial redistribution license.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import csv
import json
import os
import re
import shutil
import stat
import uuid

import httpx

from . import service

MCP_SERVERS = {
    "bhavcopy": "https://mcp.nseindia.in/bhavcopy/cm/mcp",
    "cash_market": "https://mcp.nseindia.in/cmmkt/mcp",
}
# Informational lookups only; no mass historical scraping or strategy backtests.
INFO_TOOLS = frozenset({
    "search_symbols", "nse_lookup_symbol", "get_corporate_actions",
    "get_stock_history", "get_ltp_by_date", "get_index_history",
    "get_index_snapshot", "get_index_valuation",
})
PROTOCOL = "2025-06-18"
MAX_REQUEST_BODY = 4000
MAX_RESPONSE_BODY = 2 * 1024 * 1024
MAX_RAW_FILE = 40 * 1024 * 1024
MAX_UNPACKED = 80 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 80
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,119}$")
TYPES = {".csv", ".zip", ".xlsx", ".xls", ".pdf"}
INDEX_WEIGHTS = "https://www.niftyindices.com/reports/monthly-reports"


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _safe_name(name: str) -> str:
    if not isinstance(name, str) or Path(name).name != name or name.startswith("."):
        raise ValueError("Source file names must be flat and not hidden")
    if not SAFE_NAME.fullmatch(name) or Path(name).suffix.lower() not in TYPES:
        raise ValueError("Source file extension/name not supported: " + name[:90])
    return name


def _archive_member_name(value: str) -> str:
    """Flatten safe inner CSV paths; reject traversal without rejecting README.txt."""
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ValueError("Unsafe archive member name")
    parts = value.split("/")
    if len(parts) > 5 or any(not part or part in {".", ".."}
                             or not SAFE_NAME.fullmatch(part) for part in parts):
        raise ValueError("Unsafe archive member path")
    return parts[-1]


def _read_original(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Provide an ordinary local export, not a symlink or remote path")
    if path.stat().st_size == 0 or path.stat().st_size > MAX_RAW_FILE:
        raise ValueError("Original export is empty or exceeds 40 MiB")
    return path.read_bytes()


def _weights_csv(data: bytes) -> bool:
    header = data[:12000].decode("utf-8-sig", errors="replace").lower()
    first = header.splitlines()[0] if header else ""
    return ("symbol" in first or "ticker" in first) and (
        "weightage" in first or "weight" in first)


def _entries_in_zip(data: bytes) -> list[tuple[str, bytes]]:
    try:
        archive = ZipFile(BytesIO(data))
        with archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError("Archive is empty or contains too many members")
            total = 0
            output: list[tuple[str, bytes]] = []
            names: set[str] = set()
            for info in members:
                # Reject symlinks and dangerous names, including ZIP path traversal.
                if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    raise ValueError("Symlinks are not accepted inside source archives")
                name = _archive_member_name(info.filename)
                total += info.file_size
                if info.file_size > MAX_RAW_FILE or total > MAX_UNPACKED:
                    raise ValueError("Archive exceeds safe extraction limits")
                if info.file_size > max(1, info.compress_size) * 200:
                    raise ValueError("Archive compression ratio is suspicious")
                if name.casefold() in names:
                    raise ValueError("Repeated archive member name: " + name)
                names.add(name.casefold())
                if name.lower().endswith(".csv"):
                    body = archive.read(info)
                    if len(body) != info.file_size:
                        raise ValueError("Unexpected decompressed file length")
                    output.append((name, body))
            return output
    except BadZipFile as exc:
        raise ValueError("Invalid ZIP: supply the original exchange download") from exc


def intake_local_exports(files: list[Path], *, root: Path | None = None) -> dict:
    """Immutable, private, manual-export intake. NEVER fetches a website.

    This creates reusable original-file receipts and an intentionally incomplete
    source-date manifest for the existing strict benchmark-weight importer.
    Missing publication times MUST be reviewed and filled by the user.
    """
    if not 1 <= len(files) <= 20:
        raise ValueError("Select 1-20 local original source files per intake")
    base = root if root is not None else service.DATA / "nse" / "authorized_intake"
    if base.exists() and base.is_symlink():
        raise ValueError("Refusing a symlink as intake root")
    base.mkdir(parents=True, exist_ok=True)
    ident = "intake_" + uuid.uuid4().hex[:16]
    pending = base / ("." + ident + ".pending")
    dest = base / ident
    pending.mkdir(mode=0o700, exist_ok=False)
    recorded = []
    weights = []
    seen: set[str] = set()
    try:
        (pending / "originals").mkdir(mode=0o700)
        for original in files:
            source = Path(original).expanduser()
            name = _safe_name(source.name)
            if name.casefold() in seen:
                raise ValueError("Duplicate original filenames in one intake")
            seen.add(name.casefold())
            raw = _read_original(source)
            digest = _sha(raw)
            stored = pending / "originals" / name
            with stored.open("xb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(raw)
            csv_names = []
            contents = _entries_in_zip(raw) if name.lower().endswith(".zip") else (
                [(name, raw)] if name.lower().endswith(".csv") else [])
            for csv_name, csv_data in contents:
                csv_name = _safe_name(csv_name)
                target = pending / csv_name
                if target.exists():
                    raise ValueError("Two reports share a CSV name; separate the intakes: " + csv_name)
                with target.open("xb") as handle:
                    os.fchmod(handle.fileno(), 0o600)
                    handle.write(csv_data)
                csv_names.append(csv_name)
                if _weights_csv(csv_data):
                    weights.append({
                        "file": csv_name, "snapshot_date": "", "published_at": "",
                        "source_url": INDEX_WEIGHTS,
                    })
            recorded.append({
                "name": name, "original_sha256": digest, "bytes": len(raw),
                "extracted_csvs": csv_names,
                "source_file_preserved": True,
                "original_source_authenticity_reviewed": False,
                "source_research_redistribution_permission_verified": False,
            })
        if weights:
            with (pending / "WEIGHTAGE_MANIFEST_TEMPLATE.csv").open(
                    "x", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, ["file", "snapshot_date", "published_at", "source_url"])
                writer.writeheader()
                writer.writerows(weights)
        receipt = {
            "source": "user_provided_local_export", "id": ident,
            "ingested_utc": datetime.now(timezone.utc).isoformat(),
            "files": recorded, "weightage_csv_candidates": len(weights),
            "source_verified_by_nse": False, "license_verified": False,
            "tri_overwritten": False,
            "warning": "This is local intake, NOT NSE website scraping or official approval. "
                       "Complete genuine snapshot and first-publication dates before using "
                       "the strict weight importer. Existing TRI datasets stay untouched.",
        }
        (pending / "SOURCE_INTAKE.json").write_text(json.dumps(
            receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        pending.rename(dest)
    except Exception:
        shutil.rmtree(pending, ignore_errors=True)
        raise
    return {**receipt, "directory": str(dest)}


def _decode_mcp(body: bytes, content_type: str, message_id: int) -> dict:
    if len(body) > MAX_RESPONSE_BODY:
        raise ValueError("NSE MCP response exceeds informational size limit")
    if content_type.startswith("application/json"):
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError("Unexpected NSE MCP JSON response")
        return result
    if content_type.startswith("text/event-stream"):
        # A bounded request-response SSE stream (not a long-running subscription).
        for event in body.decode("utf-8").split("\n\n"):
            payload = "\n".join(line[5:].lstrip() for line in event.splitlines()
                                if line.startswith("data:"))
            if not payload:
                continue
            parsed = json.loads(payload)
            if isinstance(parsed, dict) and parsed.get("id") == message_id:
                return parsed
        raise ValueError("No matching JSON-RPC response in NSE MCP event stream")
    raise ValueError("NSE MCP did not return a JSON-RPC response")


class NSEInfoMCP:
    """Official NSE MCP client, limited to one informational lookup per call.

    Deliberately separate from backtest and price-cache ingestion. The publicly
    documented 5-year history cannot certify the full historical 2014+ study.
    """

    def __init__(self, server: str = "bhavcopy", *,
                 transport: httpx.BaseTransport | None = None):
        if server not in MCP_SERVERS:
            raise ValueError("Only official, pinned NSE MCP server URLs are supported")
        self.server = server
        self.url = MCP_SERVERS[server]
        self.session: str | None = None
        self.protocol = PROTOCOL
        self.client = httpx.Client(
            timeout=httpx.Timeout(20.0), follow_redirects=False,
            trust_env=False, transport=transport)
        self._next_id = 1

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _request(self, method: str, params: dict | None = None,
                 *, notification: bool = False) -> dict:
        payload: dict = {"jsonrpc": "2.0", "method": method}
        request_id = self._next_id
        if not notification:
            payload["id"] = request_id
            self._next_id += 1
        if params is not None:
            payload["params"] = params
        encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BODY:
            raise ValueError("Informational NSE request is too large")
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if method != "initialize":
            headers["MCP-Protocol-Version"] = self.protocol
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        response = self.client.post(self.url, content=encoded, headers=headers)
        if response.status_code in (401, 403, 429):
            raise ValueError("NSE MCP refused this query or rate-limited requests; "
                             "respect provider access limits")
        if response.status_code >= 300:
            raise ValueError("NSE MCP returned HTTP " + str(response.status_code))
        if notification:
            if response.status_code != 202:
                raise ValueError("NSE MCP did not acknowledge initialization")
            return {}
        session = response.headers.get("mcp-session-id")
        if session and len(session) <= 180:
            self.session = session
        result = _decode_mcp(
            response.content, response.headers.get("content-type", "").split(";")[0],
            request_id)
        if "error" in result:
            raise ValueError("NSE MCP JSON-RPC error: " +
                             str(result["error"].get("message", "query rejected"))[:160])
        return result.get("result", {})

    def initialize(self) -> dict:
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "quantlab-source-info", "version": "1.0.0"},
        })
        negotiated = result.get("protocolVersion", PROTOCOL)
        if negotiated not in {"2025-03-26", "2025-06-18", "2025-11-25"}:
            raise ValueError("NSE MCP negotiated an unsupported protocol version")
        self.protocol = negotiated
        self._request("notifications/initialized", notification=True)
        return result

    def tools(self) -> list[dict]:
        result = self._request("tools/list", {})
        entries = result.get("tools", [])
        if not isinstance(entries, list) or len(entries) > 150:
            raise ValueError("Unexpected NSE MCP tool catalogue")
        return [{
            "name": str(t.get("name", "")),
            "description": str(t.get("description", ""))[:600],
            "inputSchema": t.get("inputSchema", {}),
            "informational_lookup_only": t.get("name") in INFO_TOOLS,
        } for t in entries if isinstance(t, dict)]

    def one_lookup(self, tool: str, arguments: dict) -> dict:
        if tool not in INFO_TOOLS or not isinstance(arguments, dict):
            raise ValueError("Only allowlisted informational NSE tool requests are available")
        available = {entry["name"] for entry in self.tools()}
        if tool not in available:
            raise ValueError("Official NSE MCP does not offer " + tool)
        result = self._request("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            raise ValueError("Official NSE MCP reported that this lookup failed")
        return result
