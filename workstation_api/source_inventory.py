"""Bounded byte-identical prepared-dataset inspection and opt-in recoverable cleanup.

Each signature covers *every* regular file, its relative path and exact bytes
(including metadata / nested files). Never compare only prices while ignoring
different historical provenance. Original shared Dhan caches are untouchable.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import re

from . import research_library, service

MAX_DATASETS = 200
MAX_FILES_PER_DATASET = 1000
MAX_FILE_BYTES = 40_000_000
MAX_SCAN_BYTES = 400_000_000
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _hash(path: Path) -> str:
    dig = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            dig.update(block)
    return dig.hexdigest()


def scan() -> dict:
    eligible = [r for r in service.datasets(include_archived=True)
                if (r["id"].startswith("upload_") or r["id"].startswith("dhan_batch_"))]
    if len(eligible) > MAX_DATASETS:
        raise ValueError(f"Inspect up to {MAX_DATASETS} user-created dataset views "
                         "per request. Archive or narrow the local library.")
    groups = {}
    inspected = 0
    skipped = []
    scanned_bytes = 0
    for record in eligible:
        dataset_id = str(record["id"])
        folder, _ = service.dataset_path(dataset_id)
        if not folder.is_dir() or folder.is_symlink():
            skipped.append({"dataset_id": dataset_id, "reason": "Unsafe or absent view folder"})
            continue
        contents = sorted(folder.rglob("*"), key=lambda p: p.relative_to(folder).as_posix())
        if len(contents) > MAX_FILES_PER_DATASET:
            skipped.append({"dataset_id":dataset_id,"reason":"Too many files for bounded scan"})
            continue
        components = []
        total = 0
        skipped_reason = None
        for file in contents:
            if file.is_symlink():
                skipped_reason = "Symlink source blocked"
                break
            if file.is_dir():
                continue
            if not file.is_file():
                skipped_reason = "Non-regular dataset content"
                break
            size = file.stat().st_size
            if size > MAX_FILE_BYTES or scanned_bytes + size > MAX_SCAN_BYTES:
                skipped_reason = "File or total hashing limit exceeded"
                break
            total += size
            scanned_bytes += size
            components.append((file.relative_to(folder).as_posix(), size, _hash(file)))
        if skipped_reason:
            skipped.append({"dataset_id": dataset_id, "reason": skipped_reason})
            continue
        if not components:
            continue
        inspected += 1
        canonical = json.dumps(components, separators=(",",":"))
        key = sha256(canonical.encode("utf-8")).hexdigest()
        deps = research_library.resource_dependencies("dataset", dataset_id)
        groups.setdefault(key, []).append({
            "dataset_id":dataset_id,"title":record["label"],
            "file_count":len(components),"file_bytes":total,
            "dependencies":len(deps),"can_trash_without_dependencies":not bool(deps),
            "protected_raw_market_cache":True,
        })
    matches=[]
    for fingerprint, items in sorted(groups.items()):
        if len(items)<2:
            continue
        matches.append({
            "signature_sha256":fingerprint,
            "datasets":items,
            "potential_view_bytes_reclaimable":sum(x["file_bytes"] for x in items[1:]),
            "safe_action":"Keep the first original prepared view. Explicitly move only "
                          "another hash-identical, dependency-free prepared view to "
                          "recoverable Trash. Never modify shared Dhan source candles.",
        })
    return {
        "scanned_dataset_views":inspected,
        "scanned_bytes":scanned_bytes,
        "identical_groups":matches,
        "skipped":skipped[:30],
        "deduplication_method":"SHA-256 of ALL regular files, relative paths and bytes",
        "warning":"Prepared-view identity only. Does not merge datasets or validate "
                  "market prices. All original shared Dhan cache remains protected.",
    }


def trash_exact_duplicate(dataset_id: str, expected_signature: str,
                          *, confirm: bool = False) -> dict:
    """Move an exact redundant view to reversible Trash after complete re-hash.

    Recheck all bytes and saved dependencies on each explicit request. Keep the
    deterministic first view and never remove the final usable dataset copy.
    """
    if not confirm:
        raise ValueError("Confirm moving an exact duplicate to recoverable Trash")
    if not (dataset_id.startswith("upload_") or dataset_id.startswith("dhan_batch_")):
        raise ValueError("Only removable user-owned prepared views can be deduplicated")
    if not DIGEST.fullmatch(expected_signature):
        raise ValueError("Invalid expected dataset fingerprint")
    with research_library.LOCK:
        inventory = scan()
        matching = next((g for g in inventory["identical_groups"]
                         if g["signature_sha256"] == expected_signature), None)
        if matching is None:
            raise ValueError("Dataset comparison changed; rescan before cleaning up")
        rows = matching["datasets"]
        if len(rows) < 2 or dataset_id == rows[0]["dataset_id"]:
            raise ValueError("Keep at least one canonical prepared dataset view")
        selected = next((r for r in rows[1:] if r["dataset_id"] == dataset_id), None)
        if selected is None:
            raise ValueError("Requested dataset is not an exact redundant copy")
        if not selected["can_trash_without_dependencies"]:
            raise ValueError("Saved studies reference this dataset; archive instead")
        result = research_library.resource_action("dataset", dataset_id, "trash", confirm=True)
        return {"dataset_id":dataset_id,"action":"moved_to_recoverable_trash",
                "verified_signature":expected_signature,
                "source_preserved":rows[0]["dataset_id"],
                "original_dhan_cache_untouched":True,
                "resource":result}
