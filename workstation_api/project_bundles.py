"""Portable QuantLab research-project bundles without licensed price history.

Only allowlisted JSON records and a metrics-only summary of referenced runs
are exported. Raw OHLCV, tokens, environment variables and executable cells
are never included. Imports create new IDs and never overwrite local work.
"""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile
from datetime import datetime, timezone
import hashlib
import json

from . import model_lab, research_library

MAX_BUNDLE = 8 * 1024 * 1024
MAX_RECORDS = 150
ALLOWED = frozenset({"project", "notebook", "note", "chart", "comparison",
                     "configuration", "dashboard", "study"})
EXCLUDED_PAYLOAD_KEYS = frozenset({"access_token", "secret", "api_key", "password", "credentials"})


def _safe(value, depth=0):
    """Bounded recursive redaction for exported JSON (defense in depth)."""
    if depth > 18:
        raise ValueError("Research bundle exceeds maximum JSON nesting")
    if isinstance(value, dict):
        return {str(k): _safe(v, depth+1) for k, v in value.items()
                if str(k).lower() not in EXCLUDED_PAYLOAD_KEYS}
    if isinstance(value, list):
        if len(value) > 10000:
            raise ValueError("Bundle contains an oversized array")
        return [_safe(v,depth+1) for v in value]
    if value is None or isinstance(value, (str,int,float,bool)):
        return value
    raise ValueError("Unsupported exported JSON value")


def _linked(record, project_id):
    if record["id"] == project_id:
        return True
    payload=record["payload"]
    if payload.get("project_id") == project_id:
        return True
    if payload.get("source_project_id") == project_id:
        return True
    return False


def _run_snapshots(records: list[dict]) -> list[dict]:
    refs=set()
    for record in records:
        for cell in record.get("payload",{}).get("cells",[]):
            if isinstance(cell,dict) and cell.get("type")=="run" and isinstance(cell.get("run_id"),str):
                refs.add(cell["run_id"])
    out=[]
    for run_id in sorted(refs)[:30]:
        try:
            r=model_lab.read_saved_model(run_id)
        except (ValueError,FileNotFoundError):
            out.append({"original_id":run_id,"status":"unavailable"})
            continue
        out.append({"original_id":run_id,"status":"summary_only",
                    "model_id":r["model_id"],"title":r.get("title"),
                    "parameters":_safe(r.get("params",{})),
                    "metrics":_safe(r.get("metrics",[]))[:100],
                    "source_sha256":r.get("source_sha256"),
                    "source_metadata":_safe(r.get("source") or {}),
                    "generated_utc":r.get("generated_utc"),
                    "warning":"Source observations and executable model versions not included."})
    return out


def bundle_path(project_id: str):
    project=research_library.get(project_id)
    if project["kind"]!="project" or project["trashed"]:
        raise ValueError("Select an active research project for export")
    records=[r for r in research_library.list_items(archived=True,limit=500)
             if r["kind"] in ALLOWED and _linked(r,project_id)]
    if len(records)>MAX_RECORDS:
        raise ValueError("Project has too many records to export as one bundle")
    canonical=[]
    for record in records:
        canonical.append({"original_id":record["id"],"kind":record["kind"],
                          "title":record["title"],"payload":_safe(record["payload"]),
                          "tags":record["tags"],"favorite":record["favorite"]})
    run_summaries=_run_snapshots(records)
    raw=json.dumps({"records":canonical,"run_summaries":run_summaries},
                   ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
    if len(raw)>MAX_BUNDLE//2:
        raise ValueError("Project exceeds safe portable-bundle size. Reduce saved figure snapshots.")
    checksum=hashlib.sha256(raw).hexdigest()
    manifest={"format":"quantlab-project-v1","created_utc":datetime.now(timezone.utc).isoformat(),
              "project_original_id":project_id,"records":len(canonical),
              "run_summaries":len(run_summaries),"payload_sha256":checksum,
              "data_policy":"No raw or licensed OHLCV, source price files, tokens or code. "
                            "Run entries are frozen summaries, not executable runs."}
    target=research_library.root() / "exports" / (project_id+".zip")
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix(".pending")
    try:
        with ZipFile(tmp,"w",compression=ZIP_DEFLATED,compresslevel=6) as archive:
            archive.writestr("manifest.json",json.dumps(manifest,sort_keys=True,indent=2))
            archive.writestr("records.json",raw)
        if tmp.stat().st_size>MAX_BUNDLE:
            raise ValueError("Portable project archive exceeds 8MB")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def import_bundle(data: bytes) -> dict:
    if not isinstance(data,bytes) or len(data)>MAX_BUNDLE:
        raise ValueError("Portable project bundle must be an 8MB-or-smaller ZIP")
    try:
        with ZipFile(BytesIO(data),"r") as archive:
            names=archive.namelist()
            if len(names)!=2 or set(names)!={"manifest.json","records.json"}:
                raise ValueError("Bundle requires only manifest.json and records.json")
            if any(info.file_size>MAX_BUNDLE//2 or info.is_dir() for info in archive.infolist()):
                raise ValueError("Unexpected or oversized ZIP member")
            manifest=json.loads(archive.read("manifest.json"))
            raw=archive.read("records.json")
    except BadZipFile as exc:
        raise ValueError("Not a valid QuantLab project bundle") from exc
    if manifest.get("format")!="quantlab-project-v1":
        raise ValueError("Unsupported project-bundle version")
    if hashlib.sha256(raw).hexdigest()!=manifest.get("payload_sha256"):
        raise ValueError("Project bundle checksum mismatch")
    body=json.loads(raw)
    rows=body.get("records")
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_RECORDS:
        raise ValueError("Project bundle must contain 1–150 records")
    original=str(manifest.get("project_original_id",""))
    by_id={}
    for item in rows:
        if (not isinstance(item,dict) or item.get("kind") not in ALLOWED
                or not isinstance(item.get("title"),str)
                or not isinstance(item.get("payload"),dict)
                or not isinstance(item.get("tags"),list)
                or not isinstance(item.get("original_id"),str)):
            raise ValueError("Malformed project-bundle record")
        if item["original_id"] in by_id:
            raise ValueError("Duplicate portable-record identifier")
        # Validate all payloads and tags BEFORE writing any records.
        research_library._validate_payload(item["payload"])
        research_library._validate_tags(item["tags"])
        if not 1<=len(item["title"].strip())<=120:
            raise ValueError("Portable record has invalid title")
        by_id[item["original_id"]]=item
    if original not in by_id or by_id[original]["kind"]!="project":
        raise ValueError("Portable bundle has no matching project")
    # The project record is created first; subsequent records point to its new ID.
    base=by_id[original]
    created=[]
    project=research_library.create("project",base["title"]+" (imported)",
                                     {**base["payload"],"imported_from":original},base["tags"])
    created.append(project["id"])
    mapping={original:project["id"]}
    try:
        for old_id, item in by_id.items():
            if old_id==original:
                continue
            payload=dict(item["payload"])
            if payload.get("project_id")==original:
                payload["project_id"]=project["id"]
            if payload.get("source_project_id")==original:
                payload["source_project_id"]=project["id"]
            payload["portable_source_id"]=old_id
            new=research_library.create(item["kind"],item["title"],payload,item["tags"])
            mapping[old_id]=new["id"]
            created.append(new["id"])
        # Remap any references to locally created chart/configuration records.
        for original_id,new_id in mapping.items():
            if original_id==original: continue
            record=research_library.get(new_id)
            payload=record["payload"]
            cells=payload.get("cells")
            if isinstance(cells,list):
                rewritten=[]
                for cell in cells:
                    if not isinstance(cell,dict): continue
                    clean=dict(cell)
                    if clean.get("chart_id") in mapping:
                        clean["chart_id"]=mapping[clean["chart_id"]]
                    elif clean.get("chart_id"):
                        clean["unresolved_portable_chart"]=clean.pop("chart_id")
                    if clean.get("run_id"):
                        clean["unresolved_portable_run"]=clean.pop("run_id")
                    rewritten.append(clean)
                research_library.update(new_id,payload={**payload,"cells":rewritten})
        # Preserve summary-only run evidence as a clearly non-executable note.
        snapshots=body.get("run_summaries") or []
        if not isinstance(snapshots,list) or len(snapshots)>30:
            raise ValueError("Invalid run summaries")
        if snapshots:
            note=research_library.create("note","Imported run summaries (non-executable)",
                    {"project_id":project["id"],"summaries":_safe(snapshots),
                     "warning":"Raw prices and executable run versions are not included."},
                    ["portable","unverified"])
            created.append(note["id"])
    except Exception:
        for item_id in reversed(created):
            try:research_library.action(item_id,"trash")
            except (FileNotFoundError,ValueError):pass
        raise
    return {"project_id":project["id"],"imported_records":len(created),
            "unresolved_saved_runs":len(body.get("run_summaries") or []),
            "warning":"An imported project preserves settings, figures and summary metrics only. "
                      "Rebind observed datasets and rerun models before making new claims."}
