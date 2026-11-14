"""Portable evidence bundles for saved QuantLab model and index research runs.

A bundle contains exact saved output, evidence, provenance manifest, environment,
independent integrity verifier, and source-aware replay instructions. No raw
licensed OHLCV or broker secrets are distributed. Full numerical re-execution
requires the original source bytes and the pinned version of this repository.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile

import numpy
import pandas
import scipy

from . import model_lab, research_next, result_evidence, research_library, service

SAFE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
MAX_MEMBER = 12_000_000
MAX_PACKAGE = 22_000_000
INPUT_NAMES = frozenset({
    "prices.csv", "daily_prices.csv", "membership.csv", "benchmark.csv",
    "fundamentals.csv", "sectors.csv", "corporate_actions.csv",
    "factor_returns.csv", "benchmark_weights.csv", "liquidity.csv",
})


def _safe_json(obj) -> bytes:
    def convert(value, depth=0):
        if depth > 24:
            raise ValueError("Research export JSON nesting is too deep")
        if value is None or isinstance(value, (bool, str, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            if len(value) > 40000:
                raise ValueError("Oversized research export object")
            return {str(key): convert(item, depth + 1) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            if len(value) > 100000:
                raise ValueError("Oversized research export numerical array")
            return [convert(item, depth + 1) for item in value]
        if hasattr(value, "item"):
            return convert(value.item(), depth + 1)
        return str(value)
    raw = json.dumps(convert(obj), ensure_ascii=False, indent=2,
                     sort_keys=True, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_MEMBER:
        raise ValueError("Research export exceeds the per-member size limit")
    return raw


def _git_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=service.ROOT,
            capture_output=True, text=True, timeout=2, check=False)
        sha = completed.stdout.strip()
        return sha if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _hash_file(path: Path) -> str:
    hash_obj = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def _source_integrity(source: dict, hashes: dict) -> dict:
    dataset_id = source.get("dataset_id")
    if not dataset_id:
        return {"dataset_id": None, "status": "not_applicable",
                "observations_replayable": False, "files": []}
    try:
        folder, _ = service.dataset_path(str(dataset_id))
    except (ValueError, KeyError, FileNotFoundError, OSError):
        return {"dataset_id": dataset_id, "status": "unavailable",
                "observations_replayable": False, "files": [],
                "note": "Original source dataset not available on this machine."}
    entries = []
    for name, expected in sorted(hashes.items()):
        if name not in INPUT_NAMES or not re.fullmatch(r"[0-9a-fA-F]{64}", str(expected)):
            entries.append({"name": str(name), "status": "invalid_saved_reference"})
            continue
        candidate = folder / name
        if candidate.is_symlink() or not candidate.is_file():
            entries.append({"name": name, "expected_sha256": expected,
                            "status": "missing"})
            continue
        current = _hash_file(candidate)
        entries.append({"name": name, "expected_sha256": expected,
                        "current_sha256": current,
                        "status": "matches" if current == expected else "changed"})
    all_match = bool(entries) and all(x["status"] == "matches" for x in entries)
    return {"dataset_id": dataset_id, "status": "local_hash_match" if all_match else
            "incomplete_or_changed", "observations_replayable": all_match,
            "files": entries,
            "note": "Hash agreement checks bytes only; this does not independently audit the data."}


def _verifier() -> bytes:
    return r'''#!/usr/bin/env python3
"""Verify archived QuantLab evidence bytes, NOT external vendor accuracy."""
from pathlib import Path
import hashlib, json, sys

folder=Path(__file__).resolve().parent
manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
checks=manifest["member_sha256"]
ok=True
for name,digest in sorted(checks.items()):
    # member names are fixed, base filenames created by QuantLab.
    if Path(name).name!=name or name.startswith("."):
        print("UNSAFE NAME",name);ok=False;continue
    target=folder/name
    if target.is_symlink() or not target.is_file():
        print("MISSING",name);ok=False;continue
    actual=hashlib.sha256(target.read_bytes()).hexdigest()
    matches=actual==digest
    print("MATCH" if matches else "CHANGED",name)
    ok=matches and ok
print("Archive integrity:", "PASS" if ok else "FAIL")
print("Independent historical-market certification: NOT PERFORMED")
sys.exit(0 if ok else 2)
'''.encode("utf-8")


def _readme(kind: str, run_id: str, has_source: bool,
            git_sha: str | None) -> bytes:
    command = (f"python scripts/reproduce_study.py --run-id {run_id} --json"
               if kind == "research_run" else
               "Open Research Workspace -> Research Tools -> Reproducibility audit "
               "and select this saved model run. Enable recompute.")
    message = f"""# QuantLab research evidence package

Run ID: {run_id}
Run type: {kind}
Repository revision: {git_sha or 'not available'}

## Contents

- \`manifest.json\`: checksums, source classification, replayability and evidence status.
- \`saved_result.json\`: the original saved Python outputs, metadata and numerical values.
- \`evidence_audit.json\`: the existing deterministic source and statistical checks.
- \`method_explanation.json\`: exact saved numerical assumptions or methodology.
- \`environment.json\`: Python, numpy, pandas, scipy and current git SHA.
- \`source_integrity.json\`: original expected source hashes and local byte verification.
- \`verify_bundle.py\`: read-only verifier for the accompanying extracted archive.
- \`saved_monthly_returns.csv\` (index runs only): *derived* saved monthly result series,
  not original licensed OHLCV, membership, or corporate-action data.

## Verify

Extract this ZIP, then run \`python verify_bundle.py\` inside the extracted folder.
The verifier checks the members listed in \`manifest.json\` but it cannot check
whether the original licensed data were economically correct.

## Numerically replay

1. Check out the listed repository git SHA and install pinned dependencies.
2. Supply the original input files in the same authorized dataset layout.
3. Confirm \`source_integrity.json\` lists actual matching input file SHA-256 hashes.
4. On the original local workstation, run:
   \`{command}\`
5. Inspect the saved source provenance, numerical tolerance and dataset vintage.

Replay-ready on this machine at export: {str(has_source).lower()}.

## Scientific limitations

**NOT an independent market-data audit or investment-performance certification.**
No API tokens, raw Dhan candles, licensed constituent notices, or licensed filing
exports are bundled. Historical NIFTY membership, dividends/adjusted returns,
published fundamentals, matching official TRI and execution costs still need
original-source verification.

A matching code hash and numeric reproduction do not establish a statistically
untouched final holdout. Research outcomes remain conditional on source quality.
"""
    return message.encode("utf-8")


def bundle_path(kind: str, run_id: str) -> Path:
    if kind not in ("model_run", "research_run") or not SAFE.fullmatch(run_id):
        raise ValueError("Select an existing saved model_run or research_run")
    if kind == "model_run":
        saved = model_lab.read_saved_model(run_id)
        source = saved.get("source") or {}
        expected = {}
        file_name = source.get("source_file")
        digest = saved.get("source_sha256")
        if file_name in INPUT_NAMES and isinstance(digest, str):
            expected[file_name] = digest
    else:
        saved = service.run_details(run_id)
        source = saved.get("source") or {}
        expected = saved.get("meta", {}).get("input_sha256", {}) or {}
    evidence = result_evidence.summarize(kind, run_id)
    explanation = research_next.explain_saved(kind, run_id)
    source_state = _source_integrity(source, expected)
    git_sha = _git_sha()
    env = {"python": sys.version.split()[0], "platform": platform.platform(),
           "numpy": numpy.__version__, "pandas": pandas.__version__,
           "scipy": scipy.__version__, "git_sha": git_sha,
           "source_code_available_from": "The repository at the recorded SHA",
           "environment_reproduced_here": False}
    contents = {
        "saved_result.json": _safe_json(saved),
        "evidence_audit.json": _safe_json(evidence),
        "method_explanation.json": _safe_json(explanation),
        "source_integrity.json": _safe_json(source_state),
        "environment.json": _safe_json(env),
        "verify_bundle.py": _verifier(),
        "README.md": _readme(kind, run_id,
                              source_state["observations_replayable"], git_sha),
    }
    if kind == "research_run":
        # Derived strategy/benchmark returns, never raw vendor candles.
        archive_folder = service._run_path(run_id)
        target = archive_folder / "monthly_results.csv"
        if target.is_file() and not target.is_symlink() and target.stat().st_size <= MAX_MEMBER:
            contents["saved_monthly_returns.csv"] = target.read_bytes()
    manifest = {
        "format": "quantlab-source-bound-evidence-v1", "kind": kind,
        "run_id": run_id, "created_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": evidence.get("evidence_class"),
        "readiness": evidence.get("readiness"), "source_sha256": expected,
        "replayable_local_source": source_state["observations_replayable"],
        "git_sha": git_sha, "independent_source_audit": False,
        "observed_investment_performance_certified": False,
        "raw_licensed_vendor_data_included": False,
        "member_sha256": {name: sha256(blob).hexdigest()
                          for name, blob in contents.items()},
    }
    contents["manifest.json"] = _safe_json(manifest)
    root = research_library.root() / "exports"
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"evidence_{kind}_{run_id}.zip"
    with tempfile.NamedTemporaryFile(dir=root, prefix="ql_evidence_", suffix=".zip",
                                     delete=False) as staging:
        staged = Path(staging.name)
    try:
        with ZipFile(staged, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for name, blob in sorted(contents.items()):
                if len(blob) > MAX_MEMBER:
                    raise ValueError("Evidence bundle member exceeds size limit")
                archive.writestr(name, blob)
        if staged.stat().st_size > MAX_PACKAGE:
            raise ValueError("Evidence bundle ZIP exceeds 22MB limit")
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)
    return destination
