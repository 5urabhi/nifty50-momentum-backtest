"""Explicit, source-locked recovery of interrupted LOCAL quantitative research jobs.

Never resumes automatically. No raw market-data copies, broker credentials,
frozen-test executions or Dhan downloads are serialized. A recovered job may be
retried only after the user clicks Retry and the original input bytes still
match a SHA-256 source receipt. Job snapshots live under the ignored data folder.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import uuid

from . import research_library, service

ID = re.compile(r"^[0-9a-f]{16}$")
SENSITIVE = re.compile(r"(?i)(access[-_]?token|api[-_]?key|password|secret|bearer\s|credential|private[-_]?key)")
ALLOWED = frozenset({
    "workspace_parameter_sweep", "workspace_grid_sweep",
    "workspace_validation", "workspace_report", "workspace_learning",
})
SOURCES = (
    "prices.csv", "daily_prices.csv", "membership.csv", "benchmark.csv",
    "fundamentals.csv", "sectors.csv", "corporate_actions.csv",
    "benchmark_weights.csv", "factor_returns.csv", "liquidity.csv",
    "RETURN_METHODOLOGY.json", "PIT_MEMBERSHIP_PROVENANCE.json",
    "BENCHMARK_SOURCE.json",
)
MAX_FILE_SIZE = 300 * 1024 * 1024  # Huge files require an explicit fresh run.
MAX_SPEC_SIZE = 20_000


def _root() -> Path:
    return service.DATA / "research_workspace" / "restart_retries"


def _json(value: object) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_SPEC_SIZE:
        raise ValueError("Saved job parameters exceed the safe resume limit")
    return payload


def _no_secrets(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or SENSITIVE.search(key):
                raise ValueError("Cannot persist job arguments containing credential fields")
            _no_secrets(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _no_secrets(child)
    elif isinstance(value, str) and SENSITIVE.search(value):
        raise ValueError("Cannot persist job arguments containing credential material")


def _hash_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected unmodified, regular research input: " + path.name)
    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("Original research input too large for automatic retry fingerprint")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _dataset_id(kind: str, args: list, kwargs: dict) -> str | None:
    if kind in {"workspace_parameter_sweep", "workspace_grid_sweep"}:
        return str(args[1]) if len(args) > 1 and args[1] else None
    if kind == "workspace_validation":
        return str(kwargs["dataset_id"]) if kwargs.get("dataset_id") else None
    if kind == "workspace_learning":
        return str(args[0]) if args and args[0] else None
    return None


def _fingerprint(kind: str, args: list, kwargs: dict) -> str:
    if kind not in ALLOWED:
        raise ValueError("Only source-safe local research jobs can be recovered")
    checked: dict[str, object] = {"kind": kind}
    # Changing the implementation invalidates old run parameters: rerun
    # from the original configuration rather than silently implying replay.
    program = Path(__file__).resolve().parent
    modules = {
        "workspace_parameter_sweep": "research_insights.py",
        "workspace_grid_sweep": "research_advanced.py",
        "workspace_validation": "research_insights.py",
        "workspace_report": "research_library.py",
        "workspace_learning": "research_learning.py",
    }
    checked["research_code"] = _hash_file(program / modules[kind])
    if kind == "workspace_report":
        if not args or not isinstance(args[0], str):
            raise ValueError("Report requires an existing immutable notebook identifier")
        notebook = research_library.get(args[0])
        if notebook["kind"] != "notebook" or notebook["trashed"]:
            raise ValueError("Saved report notebook is unavailable")
        checked["notebook"] = hashlib.sha256(
            json.dumps(notebook, sort_keys=True, ensure_ascii=False,
                       allow_nan=False).encode("utf-8")).hexdigest()
    else:
        dataset_id = _dataset_id(kind, args, kwargs)
        if dataset_id:
            folder, record = service.dataset_path(dataset_id)
            if record["kind"] == "synthetic":
                checked["evidence"] = "synthetic_not_market"
            checked["dataset"] = dataset_id
            source_hashes = {}
            for name in SOURCES:
                path = folder / name
                if path.exists() or path.is_symlink():
                    source_hashes[name] = _hash_file(path)
            if "prices.csv" not in source_hashes and "daily_prices.csv" not in source_hashes:
                raise ValueError("No original local price series to lock for restart recovery")
            checked["sources"] = source_hashes
        else:
            checked["evidence"] = "mathematical_assumptions_only"
    return hashlib.sha256(_json(checked)).hexdigest()


def save(job_id: str, kind: str, args: tuple, kwargs: dict) -> bool:
    """Save only explicitly recoverable research inputs and their source lock."""
    if not ID.fullmatch(job_id) or kind not in ALLOWED:
        return False
    payload = {"version": 1, "job_id": job_id, "kind": kind,
               "args": list(args), "kwargs": kwargs}
    _no_secrets(payload)
    payload["input_fingerprint"] = _fingerprint(kind, payload["args"], kwargs)
    encoded = _json(payload)
    directory = _root()
    if directory.is_symlink():
        raise ValueError("Unsafe job recovery directory")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (job_id + ".json")
    if target.exists() or target.is_symlink():
        raise ValueError("Job recovery specification already exists")
    temporary = directory / ("." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            os.chmod(temporary, 0o600)
            handle.write(encoded)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def available(job_id: str) -> bool:
    if not ID.fullmatch(job_id):
        return False
    path = _root() / (job_id + ".json")
    return path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SPEC_SIZE


def restore(job_id: str) -> tuple[str, list, dict]:
    if not available(job_id):
        raise ValueError("No safe original job configuration was saved")
    path = _root() / (job_id + ".json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != 1 or raw.get("job_id") != job_id:
        raise ValueError("Invalid persistent retry manifest")
    kind, args, kwargs = raw.get("kind"), raw.get("args"), raw.get("kwargs")
    if kind not in ALLOWED or not isinstance(args, list) or not isinstance(kwargs, dict):
        raise ValueError("Unrecognized persistent retry arguments")
    _no_secrets(raw)
    observed = _fingerprint(kind, args, kwargs)
    if not isinstance(raw.get("input_fingerprint"), str) or not hmac.compare_digest(
            raw["input_fingerprint"], observed):
        raise ValueError("Saved dataset, notebook or calculation code changed. "
                         "Reopen the source and run with a new configuration.")
    return kind, args, kwargs
