"""Single-use, locally frozen historical experiment protocols.

Protect against accidental post-freeze parameter/data edits and repeated use
of a final-test period. This does not prevent a human inspecting files before
freeze; timestamps are local and neither source facts nor holdout independence
are independently notarized.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import uuid

from . import historical_readiness, service

ID = re.compile(r"^freeze_[a-f0-9]{20}$")


def _root() -> Path:
    return service.RESULTS.parent / "frozen_studies"


def _canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _digest(body: dict) -> str:
    return hashlib.sha256(_canonical(body)).hexdigest()


def _path(protocol_id: str) -> Path:
    if not ID.fullmatch(protocol_id):
        raise ValueError("Invalid frozen protocol ID")
    path = _root() / (protocol_id + ".json")
    if path.is_symlink():
        raise ValueError("Unsafe protocol path")
    return path


def read(protocol_id: str) -> dict:
    path = _path(protocol_id)
    if not path.is_file() or path.stat().st_size > 100_000:
        raise ValueError("Unknown frozen protocol")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("id") != protocol_id:
        raise ValueError("Frozen protocol identity mismatch")
    documented = data.get("sha256")
    original = dict(data)
    original.pop("sha256", None)
    if _digest(original) != documented:
        raise ValueError("Frozen protocol was altered; execution forbidden")
    used = path.with_suffix(".use")
    state = "consumed" if used.exists() else "available"
    return {**data, "state": state}


def create(dataset_id: str, config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("Frozen configuration is required")
    if config.get("dataset_id"):
        raise ValueError("Dataset ID must be a separate, explicit argument")
    if not config.get("validation_start") or not config.get("final_test_start"):
        raise ValueError("Declare both validation and final-test dates before freezing")
    weights = config.get("factor_weights", {})
    if not isinstance(weights, dict):
        raise ValueError("Missing factor configuration")
    chosen = [k for k, v in weights.items() if isinstance(v, (int, float)) and v > 0]
    report = historical_readiness.inspect(
        dataset_id, validation_start=str(config["validation_start"]),
        final_test_start=str(config["final_test_start"]), selected_factors=chosen)
    if not report["structural_run_ready"]:
        missing = [r["name"] + ": " + r["detail"] for r in report["checks"]
                   if r["name"] in {"Monthly price panel", "Effective-date constituent states",
                                    "Paired benchmark returns",
                                    "Eligible price and forward-return coverage",
                                    "Chronological frozen test design"}
                   and r["status"] != "pass"]
        raise ValueError("Frozen exploratory evaluation blocked: " + "; ".join(missing))
    folder, dataset = service.dataset_path(dataset_id)
    if dataset.get("kind") == "synthetic" or (folder / "DO_NOT_CITE.txt").exists():
        raise ValueError("Synthetic demonstration may not use a historical frozen-test claim")
    fingerprints = historical_readiness.source_hashes(folder)
    for name in ("prices.csv", "membership.csv", "benchmark.csv"):
        if name not in fingerprints:
            raise ValueError("Frozen protocol lacks core source input: " + name)
    directory = _root()
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "id": "freeze_" + uuid.uuid4().hex[:20],
        "dataset_id": dataset_id, "dataset_kind": dataset["kind"],
        "config": dict(config), "config_sha256": _digest(config),
        "source_sha256": fingerprints,
        "validation_start": config["validation_start"],
        "final_test_start": config["final_test_start"],
        "registered_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "one_use_software_frozen_exploratory_study",
        "source_check_status": report["status"],
        "independent_source_certified": False,
        "prospective_protocol_notarized": False,
        "publication_certified": False,
        "warning": "Local timestamps and original-source hashes do not prove nobody "
                   "looked at the final test beforehand. Human/source verification "
                   "and exchange licensing remain distinct requirements.",
    }
    record["sha256"] = _digest(record)
    target = _path(record["id"])
    with target.open("xb") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, indent=2,
                                allow_nan=False).encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return {**record, "state": "available",
            "missing_source_actions": report["missing_source_actions"]}


def _source_unchanged(data: dict) -> bool:
    folder, _ = service.dataset_path(data["dataset_id"])
    return historical_readiness.source_hashes(folder) == data["source_sha256"]


def execute(protocol_id: str) -> str:
    """Consume once before touching final-test data; record any invalidation."""
    data = read(protocol_id)
    if data["state"] != "available":
        raise ValueError("The frozen protocol was already consumed; create a new version")
    attempt = _path(protocol_id).with_suffix(".use")
    with attempt.open("xb") as file:
        file.write(json.dumps({
            "protocol_sha256": data["sha256"],
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "state": "reserved_single_use",
        }, indent=2).encode("utf-8"))
        file.flush()
        os.fsync(file.fileno())
    if _digest(data["config"]) != data["config_sha256"] or not _source_unchanged(data):
        raise ValueError("Data or configuration changed since freezing; no run was started")
    run_id = service.execute_run(data["dataset_id"], data["config"])
    saved = service._run_path(run_id)
    manifest = json.loads((saved / "research_manifest.json").read_text())
    computed = manifest.get("input_sha256", {})
    # Experiment stores all source CSV hashes. Any mismatched source used by
    # the result invalidates this frozen evaluation receipt.
    same_manifest = all(computed.get(name) == value for name, value
                        in data["source_sha256"].items() if name.endswith(".csv"))
    still_same = _source_unchanged(data)
    okay = same_manifest and still_same
    receipt = {
        "protocol_id": protocol_id, "protocol_sha256": data["sha256"],
        "run_id": run_id, "dataset_id": data["dataset_id"],
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": data["source_sha256"],
        "validation_start": data["validation_start"],
        "final_test_start": data["final_test_start"],
        "manifest_csv_hashes_matched": same_manifest,
        "source_unchanged_after_run": still_same,
        "state": "software_frozen_exploratory" if okay else "invalidated",
        "independent_source_certified": False,
        "independent_holdout_certified": False,
        "publication_certified": False,
        "warning": "One-use software lock, not independent historical or prospective certification.",
    }
    target = saved / "FROZEN_PROTOCOL_RECEIPT.json"
    with target.open("x", encoding="utf-8") as output:
        json.dump(receipt, output, indent=2, allow_nan=False)
    if not okay:
        raise ValueError("Frozen source or calculated manifest changed during execution. "
                         "Run is marked invalidated, not a valid frozen result.")
    return run_id


def run_receipt(run_id: str) -> dict:
    folder = service._run_path(run_id)
    receipt = folder / "FROZEN_PROTOCOL_RECEIPT.json"
    if not receipt.is_file() or receipt.is_symlink():
        return {"run_id": run_id, "state": "not_software_frozen",
                "independent_source_certified": False,
                "independent_holdout_certified": False}
    if receipt.stat().st_size > 100_000:
        raise ValueError("Frozen run receipt exceeds size limit")
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if data.get("run_id") != run_id or not ID.fullmatch(str(data.get("protocol_id", ""))):
        raise ValueError("Invalid frozen run receipt")
    parent = read(data["protocol_id"])
    checked = data.get("protocol_sha256") == parent["sha256"]
    try:
        source_same = _source_unchanged(parent)
    except (OSError, ValueError):
        source_same = False
    return {**data, "receipt_protocol_integrity": checked,
            "source_unchanged_now": source_same,
            "state": data["state"] if checked and source_same
                     else "invalidated",
            "independent_source_certified": False,
            "independent_holdout_certified": False,
            "publication_certified": False}
