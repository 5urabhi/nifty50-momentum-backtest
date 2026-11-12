"""Durable local QuantLab research library with reversible lifecycle operations.

SQLite holds metadata, not market data. Raw shared Dhan candles and canonical
stock observations are NEVER deleted through the dataset-management API.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
import hashlib
import html
import json
import re
import shutil
import sqlite3
import uuid

from . import model_lab, service

KINDS = frozenset({"configuration", "project", "notebook", "chart", "comparison",
                   "dashboard", "note", "report", "study"})
RESOURCE_KINDS = frozenset({"dataset", "model_run", "research_run"})
ALLOWED_ACTIONS = frozenset({"archive", "unarchive", "trash", "restore", "favorite",
                            "unfavorite", "purge"})
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,89}$")
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,90}$")
LOCK = RLock()
MAX_PAYLOAD = 180_000


def now():
    return datetime.now(timezone.utc).isoformat()


def root() -> Path:
    return service.DATA / "research_workspace"


def report_root() -> Path:
    return service.RESULTS.parent / "research_workspace_reports"


@contextmanager
def _connect():
    path = root() / "library.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        conn.executescript("""
      CREATE TABLE IF NOT EXISTS records (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
        payload TEXT NOT NULL, tags TEXT NOT NULL,
        favorite INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0,
        trashed INTEGER NOT NULL DEFAULT 0,
        created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS records_kind ON records(kind, trashed, updated_utc);
      CREATE TABLE IF NOT EXISTS resources (
        key TEXT PRIMARY KEY, kind TEXT NOT NULL, item_id TEXT NOT NULL,
        archived INTEGER NOT NULL DEFAULT 0,
        trashed INTEGER NOT NULL DEFAULT 0,
        original_path TEXT, trash_path TEXT,
        updated_utc TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS job_history (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
        created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL,
        error TEXT, result_excerpt TEXT
      );
      CREATE INDEX IF NOT EXISTS jobs_updated ON job_history(updated_utc);
    """)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _validate_payload(payload) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Research-library payload must be a JSON object")
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD:
        raise ValueError("Research item exceeds maximum local record size")
    return encoded


def _validate_tags(tags):
    if not isinstance(tags, list) or len(tags) > 20:
        raise ValueError("Use at most 20 tags")
    result = []
    for tag in tags:
        if not isinstance(tag, str) or len(tag.strip()) > 32:
            raise ValueError("Tag must be a short string")
        clean = tag.strip()
        if clean and clean not in result:
            result.append(clean)
    return json.dumps(result)


def _row(row):
    if row is None:
        raise FileNotFoundError("Research-library item not found")
    d = dict(row)
    d["payload"] = json.loads(d["payload"])
    d["tags"] = json.loads(d["tags"])
    for f in ("favorite", "archived", "trashed"):
        d[f] = bool(d[f])
    return d


def _id(kind):
    return kind[:5] + "_" + uuid.uuid4().hex[:16]


def create(kind: str, title: str, payload: dict | None = None, tags: list | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError("Unknown research item type")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        raise ValueError("Title must contain 1-120 characters")
    blob, labels = _validate_payload(payload or {}), _validate_tags(tags or [])
    stamp, item_id = now(), _id(kind)
    with LOCK, _connect() as conn:
        conn.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (item_id, kind, title.strip(), blob, labels, 0, 0, 0, stamp, stamp))
    return get(item_id)


def get(item_id: str) -> dict:
    if not ID.fullmatch(item_id):
        raise ValueError("Invalid research-library identifier")
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        return _row(conn.execute("SELECT * FROM records WHERE id=?", (item_id,)).fetchone())


def list_items(kind: str | None = None, query: str = "", *,
               archived: bool = False, trashed: bool = False, limit: int = 200) -> list:
    if kind and kind not in KINDS:
        raise ValueError("Unknown research item type")
    if len(query) > 120 or not 1 <= limit <= 500:
        raise ValueError("Invalid library search")
    params = [int(trashed)]
    sql = "SELECT * FROM records WHERE trashed=?"
    if not trashed and not archived:
        sql += " AND archived=0"
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    if query:
        sql += " AND (LOWER(title) LIKE ? OR LOWER(tags) LIKE ?)"
        match = "%" + query.strip().lower().replace("%", r"\%").replace("_", r"\_") + "%"
        params.extend([match, match])
    sql += " ORDER BY favorite DESC, updated_utc DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        return [_row(row) for row in conn.execute(sql, params)]


def update(item_id: str, *, title=None, payload=None, tags=None,
           favorite=None, archived=None) -> dict:
    old = get(item_id)
    if old["trashed"]:
        raise ValueError("Restore item before editing")
    modifications = []
    values = []
    if title is not None:
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
            raise ValueError("Title must contain 1-120 characters")
        modifications.append("title=?")
        values.append(title.strip())
    if payload is not None:
        modifications.append("payload=?")
        values.append(_validate_payload(payload))
    if tags is not None:
        modifications.append("tags=?")
        values.append(_validate_tags(tags))
    for flag, val in (("favorite", favorite), ("archived", archived)):
        if val is not None:
            if not isinstance(val, bool):
                raise ValueError(flag + " must be a boolean")
            modifications.append(flag + "=?")
            values.append(int(val))
    if not modifications:
        return old
    modifications.append("updated_utc=?")
    values.extend([now(), item_id])
    with LOCK, _connect() as conn:
        conn.execute("UPDATE records SET " + ",".join(modifications) + " WHERE id=?", values)
    return get(item_id)


def action(item_id: str, action_name: str, *, confirm: bool = False) -> dict:
    if action_name not in ALLOWED_ACTIONS:
        raise ValueError("Unknown research-library action")
    previous = get(item_id)
    if action_name == "archive":
        return update(item_id, archived=True)
    if action_name == "unarchive":
        return update(item_id, archived=False)
    if action_name == "favorite":
        return update(item_id, favorite=True)
    if action_name == "unfavorite":
        return update(item_id, favorite=False)
    if action_name == "purge":
        if not confirm or not previous["trashed"]:
            raise ValueError("Permanent deletion requires a trashed item and confirmation")
        if previous["kind"] == "report":
            for ext in (".html", ".md", ".pdf"):
                (report_root() / (item_id + ext)).unlink(missing_ok=True)
        with LOCK, _connect() as conn:
            conn.execute("DELETE FROM records WHERE id=? AND trashed=1", (item_id,))
        return {"id": item_id, "purged": True}
    with LOCK, _connect() as conn:
        conn.execute("UPDATE records SET trashed=?,updated_utc=? WHERE id=?",
                     (1 if action_name == "trash" else 0, now(), item_id))
    return get(item_id)


def batch_action(items: list[str], action_name: str) -> dict:
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise ValueError("Select between 1 and 50 library items")
    if len(set(items)) != len(items):
        raise ValueError("Duplicate library item in selection")
    if action_name == "purge":
        raise ValueError("Permanent deletion is per-item only")
    # Validate every entry before applying any updates.
    for item_id in items:
        get(item_id)
    return {"updated": [action(item_id, action_name)["id"] for item_id in items]}


def _resource_key(kind, item_id):
    if kind not in RESOURCE_KINDS or not RUN_ID.fullmatch(item_id):
        raise ValueError("Invalid research resource identifier")
    return kind + ":" + item_id


def _resource_path(kind: str, item_id: str) -> Path:
    _resource_key(kind, item_id)
    if kind == "dataset":
        folder, record = service.dataset_path(item_id)
        # Never delete the canonical shared library, downloaded candle caches,
        # static fixtures, or named base datasets. Only derived/uploaded views.
        bases = (service.DATA / "workstation_imports",
                 service.DATA / "dhan" / "monthly_research")
        if item_id.startswith("upload_"):
            allowed = folder.parent == bases[0]
        elif item_id.startswith("dhan_batch_"):
            allowed = folder.parent == bases[1] and folder.name.startswith("batch_")
        else:
            allowed = False
        if not allowed or record["id"] == "dhan_shared":
            raise ValueError("Protected source: only uploaded or derived Dhan views may be removed")
    elif kind == "model_run":
        if not model_lab.RUN_ID.fullmatch(item_id):
            raise ValueError("Unknown saved model-run ID")
        folder = model_lab._run_root() / (item_id + ".json")
    else:
        folder = service.RESULTS / item_id
    if not folder.exists() or folder.is_symlink():
        raise ValueError("Resource is missing or unsafe")
    return folder


def _stored_resource(conn, key):
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM resources WHERE key=?", (key,)).fetchone()
    return dict(row) if row else None


def resource_status(kind, item_id):
    key = _resource_key(kind, item_id)
    with _connect() as conn:
        result = _stored_resource(conn, key)
    return {"archived": bool(result and result["archived"]),
            "trashed": bool(result and result["trashed"])}


def resource_dependencies(kind: str, item_id: str) -> list[dict]:
    """Scan every saved reference before moving a source to Trash."""
    _resource_key(kind, item_id)
    refs = []
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id,kind,title FROM records WHERE trashed=0 "
                            "AND payload LIKE ? LIMIT 150",
                            ("%" + item_id + "%",)).fetchall()
    refs.extend([{"kind": row["kind"], "id": row["id"], "title": row["title"]}
                 for row in rows])
    if kind == "dataset":
        # Do NOT use service.runs() or model_lab.list_saved_models() here:
        # those intentionally paginate for UI and can miss older dependent runs.
        for file in service.RESULTS.glob("*/workstation_run.json"):
            if file.is_symlink() or file.parent.is_symlink() or not RUN_ID.fullmatch(file.parent.name):
                continue
            try:
                run = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if run.get("dataset_id") == item_id:
                refs.append({"kind": "research_run", "id": file.parent.name,
                             "title": file.parent.name})
        for file in model_lab._run_root().glob("*.json"):
            if file.is_symlink() or not model_lab.RUN_ID.fullmatch(file.stem):
                continue
            try:
                model_run = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (model_run.get("source") or {}).get("dataset_id") == item_id:
                refs.append({"kind": "model_run", "id": file.stem, "title": file.stem})
    return refs[:150]

def resource_action(kind: str, item_id: str, operation: str, *,
                    confirm: bool = False) -> dict:
    if operation not in {"archive", "unarchive", "trash", "restore", "purge"}:
        raise ValueError("Invalid resource operation")
    key = _resource_key(kind, item_id)
    with LOCK, _connect() as conn:
        state = _stored_resource(conn, key)
        if operation == "archive" or operation == "unarchive":
            if state and state["trashed"]:
                raise ValueError("Restore resource before archiving")
            archived = int(operation == "archive")
            conn.execute("INSERT INTO resources(key,kind,item_id,archived,updated_utc) VALUES(?,?,?,?,?) "
                         "ON CONFLICT(key) DO UPDATE SET archived=excluded.archived,updated_utc=excluded.updated_utc",
                         (key, kind, item_id, archived, now()))
        elif operation == "trash":
            if state and state["trashed"]:
                raise ValueError("Resource is already in Trash")
            if not confirm:
                raise ValueError("Deleting a resource requires explicit confirmation")
            dependencies = resource_dependencies(kind, item_id)
            if dependencies:
                raise ValueError("Resource is referenced by saved work: " +
                                 ", ".join(d["title"] for d in dependencies[:5]) +
                                 ". Archive it instead or remove dependencies first.")
            source = _resource_path(kind, item_id)
            target = root() / "trash" / kind / (item_id + "_" + uuid.uuid4().hex[:8])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            conn.execute("INSERT INTO resources(key,kind,item_id,archived,trashed,original_path,trash_path,updated_utc) "
                         "VALUES(?,?,?,0,1,?,?,?) ON CONFLICT(key) DO UPDATE SET trashed=1,"
                         "original_path=excluded.original_path,trash_path=excluded.trash_path,"
                         "updated_utc=excluded.updated_utc",
                         (key, kind, item_id, str(source), str(target), now()))
        elif operation == "restore":
            if not state or not state["trashed"]:
                raise ValueError("Resource not in Trash")
            src = Path(state["trash_path"])
            dest = Path(state["original_path"])
            allowed_trash = root() / "trash" / kind
            if src.parent != allowed_trash or dest.exists() or src.is_symlink() or not src.exists():
                raise ValueError("Cannot safely restore resource")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            conn.execute("UPDATE resources SET trashed=0,trash_path=NULL,"
                         "original_path=NULL,updated_utc=? WHERE key=?", (now(), key))
        elif operation == "purge":
            if not confirm or not state or not state["trashed"]:
                raise ValueError("Permanent deletion requires a trashed resource and confirmation")
            src = Path(state["trash_path"])
            if src.parent != root() / "trash" / kind or src.is_symlink():
                raise ValueError("Unsafe Trash path")
            if src.is_dir():
                shutil.rmtree(src)
            else:
                src.unlink(missing_ok=True)
            conn.execute("DELETE FROM resources WHERE key=?", (key,))
    return {"key": key, "kind": kind, "id": item_id,
            **resource_status(kind, item_id)}


def resource_listing(*, include_trashed: bool = False) -> list[dict]:
    rows = []
    for dataset in service.datasets(include_archived=True):
        status = resource_status("dataset", dataset["id"])
        if not include_trashed and (status["archived"] or status["trashed"]):
            continue
        rows.append({"kind": "dataset", "id": dataset["id"], "title": dataset["label"],
                     "summary": dataset.get("basis", ""), "protected": not (
                         dataset["id"].startswith("upload_") or
                         dataset["id"].startswith("dhan_batch_")),
                     **status})
    for group, data in (("model_run", model_lab.list_saved_models(include_archived=True, limit=1000)),
                        ("research_run", service.runs(include_archived=True, limit=1000))):
        for result in data:
            status = resource_status(group, result["id"])
            if not include_trashed and (status["archived"] or status["trashed"]):
                continue
            rows.append({"kind": group, "id": result["id"],
                         "title": result.get("title") or result.get("name") or result["id"],
                         "summary": result.get("dataset_id") or result.get("generated_utc") or "",
                         "protected": False, **status})
    if include_trashed:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT * FROM resources WHERE trashed=1"):
                rows.append({"kind": row["kind"], "id": row["item_id"],
                             "title": row["item_id"], "summary": "Moved to recoverable Trash",
                             "protected": False, "archived": bool(row["archived"]),
                             "trashed": True})
    return rows


def disk_usage() -> dict:
    paths = {"raw_market_data": service.DATA / "dhan" / "history",
             "shared_market": service.DATA / "dhan" / "shared_market.sqlite3",
             "prepared_research": service.DATA / "dhan" / "monthly_research",
             "saved_runs": service.RESULTS,
             "model_runs": model_lab._run_root(),
             "reports": report_root(),
             "trash": root() / "trash"}
    amounts = {}
    for label, path in paths.items():
        if path.is_symlink():
            amounts[label] = 0
        elif path.is_file():
            amounts[label] = path.stat().st_size
        elif path.is_dir():
            amounts[label] = sum(f.stat().st_size for f in path.rglob("*")
                                 if f.is_file() and not f.is_symlink())
        else:
            amounts[label] = 0
    return {"bytes": amounts, "total_bytes": sum(amounts.values()),
            "note": "Categories may overlap when a project has nested artifacts."}


def global_search(phrase: str) -> list[dict]:
    if not phrase or len(phrase) > 120:
        raise ValueError("Search term must contain 1-120 characters")
    needle = phrase.casefold()
    results = [{"kind": a["kind"], "id": a["id"], "title": a["title"],
                "location": "research_library"} for a in list_items(query=phrase, limit=75)]
    for item in resource_listing():
        if needle in (item["title"] + " " + item["summary"]).casefold():
            results.append({**item, "location": "resource_library"})
    return results[:100]


def render_notebook_report(notebook_id: str, *, format: str = "html") -> dict:
    """Freeze a safe, self-contained report snapshot from a saved notebook.

    No arbitrary HTML execution and no invented model metrics: run citations
    reference previously stored QuantLab results.
    """
    if format not in {"html", "markdown"}:
        raise ValueError("Unsupported report format")
    notebook = get(notebook_id)
    if notebook["kind"] != "notebook" or notebook["trashed"]:
        raise ValueError("Report source must be an active research notebook")
    cells = notebook["payload"].get("cells", [])
    if not isinstance(cells, list) or len(cells) > 100:
        raise ValueError("Notebook must have at most 100 cells")
    sections = []
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("type") not in ("markdown", "run", "chart", "table"):
            raise ValueError("Notebook contains an unsupported cell")
        kind = cell["type"]
        if kind == "markdown":
            text = str(cell.get("content", ""))[:12000]
            sections.append((kind, text))
        elif kind == "run":
            run_id = str(cell.get("run_id", ""))
            record = model_lab.read_saved_model(run_id)
            metrics = [{"label": m["label"], "value": m["value"], "unit": m["unit"]}
                       for m in record["metrics"]]
            sections.append((kind, json.dumps({"model": record["title"], "run_id": run_id,
                                               "source": record.get("source"),
                                               "metrics": metrics}, ensure_ascii=False, indent=2)))
        else:
            sections.append((kind, str(cell.get("content", ""))[:12000]))
    lines = ["# " + notebook["title"], "",
             "Generated: " + now(), "",
             "Research results are descriptive. Review source lineage and limits.", ""]
    for kind, body in sections:
        lines.extend(["## " + kind.title(), "", body, ""])
    report = create("report", notebook["title"] + " — report",
                    {"source_notebook_id": notebook_id, "format": format,
                     "generated_utc": now(), "section_count": len(sections)})
    report_root().mkdir(parents=True, exist_ok=True)
    md = "\n".join(lines)
    document = "<!doctype html><html lang='en'><head><meta charset='utf-8'>" + \
        "<meta name='viewport' content='width=device-width,initial-scale=1'>" + \
        "<title>" + html.escape(notebook["title"]) + "</title>" + \
        "<style>body{font:16px/1.65 system-ui;max-width:920px;margin:4rem auto;padding:0 2rem}" + \
        "pre{white-space:pre-wrap;background:#eff3f6;padding:1.2rem;border-radius:8px}" + \
        "h1,h2{color:#123340}small{color:#667}</style></head><body>" + \
        "<h1>" + html.escape(notebook["title"]) + "</h1>" + \
        "<small>Generated " + html.escape(now()) + \
        " · Observed data and theoretical simulations must not be conflated.</small>" + \
        "".join("<h2>" + html.escape(kind.title()) + "</h2><pre>" +
                html.escape(body) + "</pre>" for kind, body in sections) + "</body></html>"
    (report_root() / (report["id"] + ".md")).write_text(md, encoding="utf-8")
    (report_root() / (report["id"] + ".html")).write_text(document, encoding="utf-8")
    _write_pdf(report["id"], notebook["title"], md)
    return {**report, "formats": ["markdown", "html", "pdf"]}


def report_path(report_id: str, format: str) -> Path:
    report = get(report_id)
    if report["kind"] != "report" or report["trashed"]:
        raise FileNotFoundError("Report unavailable")
    ext = {"markdown": ".md", "html": ".html", "pdf": ".pdf"}.get(format)
    if ext is None:
        raise ValueError("Choose HTML, Markdown or PDF")
    path = report_root() / (report_id + ext)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError("Report artifact unavailable")
    return path


def _write_pdf(report_id: str, title: str, body: str) -> None:
    """Create a paginated, selectable PDF with conservative report styling."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    target = report_root() / (report_id + ".pdf")
    temp = target.with_name(target.name + "." + uuid.uuid4().hex[:8] + ".tmp")
    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=17,
                                 leading=23, textColor=colors.HexColor("#173d48"),
                                 spaceAfter=20)
    heading_style = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12,
                                   leading=17, textColor=colors.HexColor("#157468"),
                                   spaceBefore=12, spaceAfter=8)
    body_style = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5,
                                leading=14, textColor=colors.HexColor("#2d4050"),
                                spaceAfter=5, wordWrap="CJK")
    story = [Paragraph(html.escape(title), title_style), Spacer(1, 8)]
    # A line is wrapped in chunks before ReportLab receives it, preventing
    # overflowing long JSON identifiers and equations.
    for text_line in body.splitlines():
        if text_line.startswith("# "):
            continue
        if text_line.startswith("## "):
            story.append(Paragraph(html.escape(text_line[3:]), heading_style))
        elif text_line.strip():
            for offset in range(0, len(text_line), 130):
                story.append(Paragraph(html.escape(text_line[offset:offset+130]),
                                       body_style))
        else:
            story.append(Spacer(1, 6))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#607884"))
        canvas.drawString(48, 33, "QuantLab | local research evidence - not investment advice")
        canvas.drawRightString(letter[0]-48, 33, str(doc.page))
        canvas.restoreState()
    try:
        report_root().mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(str(temp), pagesize=letter,
                leftMargin=48,rightMargin=48,topMargin=52,bottomMargin=54,
                title=title, author="QuantLab Research")
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def report_source(report_id: str) -> dict:
    path = report_path(report_id, "markdown")
    return {"id": report_id, "content": path.read_text(encoding="utf-8")}


def edit_report(report_id: str, content: str) -> dict:
    """Update a user-edited report's frozen text, HTML and PDF together."""
    if not isinstance(content, str) or not 1 <= len(content.strip()) <= 90_000:
        raise ValueError("Report body must contain 1-90000 characters")
    record = get(report_id)
    if record["kind"] != "report" or record["trashed"]:
        raise ValueError("Only active generated reports may be edited")
    report_root().mkdir(parents=True, exist_ok=True)
    path = report_root() / (report_id + ".md")
    path.write_text(content, encoding="utf-8")
    safe = html.escape(content)
    (report_root() / (report_id + ".html")).write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>" + html.escape(record["title"]) + "</title></head>"
        "<body style='font:16px/1.6 system-ui;max-width:920px;margin:4rem auto;padding:2rem'>"
        "<h1>" + html.escape(record["title"]) + "</h1><pre style='white-space:pre-wrap'>"
        + safe + "</pre></body></html>", encoding="utf-8")
    _write_pdf(report_id, record["title"], content)
    metadata = {**record["payload"], "edited_utc": now(), "manually_edited": True}
    return update(report_id, payload=metadata)


def store_job(snapshot: dict) -> None:
    """Durable summary only; no market-data frames, secrets or large outputs."""
    job_id = str(snapshot.get("id", ""))
    if not RUN_ID.fullmatch(job_id):
        raise ValueError("Invalid job identifier")
    stamp = now()
    kind = str(snapshot.get("kind","unknown"))[:90]
    status = str(snapshot.get("status","unknown"))[:30]
    error = str(snapshot.get("error",""))[:300] if snapshot.get("error") else None
    result = snapshot.get("result")
    excerpt = None
    if isinstance(result, dict):
        excerpt = json.dumps({key: result.get(key) for key in (
            "status","dataset_id","study_id","message","run_id","id")
            if key in result}, ensure_ascii=False, allow_nan=False)[:2500]
    elif isinstance(result, str):
        excerpt = json.dumps({"run_id": result[:90]})
    with LOCK, _connect() as conn:
        conn.execute("""
        INSERT INTO job_history(id,kind,status,created_utc,updated_utc,error,result_excerpt)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET status=excluded.status,
         updated_utc=excluded.updated_utc,error=excluded.error,
         result_excerpt=excluded.result_excerpt
        """, (job_id,kind,status,snapshot.get("created_utc",stamp),stamp,error,excerpt))


def list_job_history(limit: int = 100) -> list[dict]:
    if not 1 <= limit <= 200:
        raise ValueError("Invalid job history limit")
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM job_history ORDER BY updated_utc DESC LIMIT ?",(limit,)))
    results = []
    for row in rows:
        item = dict(row)
        result = item.pop("result_excerpt")
        if result:
            try: item["result"] = json.loads(result)
            except ValueError: pass
        if item["status"] in {"running","queued"}:
            item["status"] = "interrupted"
            item["error"] = "The Python process was restarted before this job finished."
        results.append(item)
    return results
