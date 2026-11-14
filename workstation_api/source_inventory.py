"""Read-only, bounded inventory of truly byte-identical prepared dataset views.

The original Dhan cache and canonical shared dataset are never deletion
targets. Two datasets are duplicates only when the same allowlisted filenames
have byte-identical contents; price correlations or overlapping calendars
are not deduplication evidence. Dependencies remain the normal deletion gate.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import re

from . import research_library, service

FILES = frozenset({
    "prices.csv", "daily_prices.csv", "membership.csv", "benchmark.csv",
    "fundamentals.csv", "sectors.csv", "corporate_actions.csv", "factor_returns.csv",
    "benchmark_weights.csv", "liquidity.csv", "daily_ohlcv.csv",
})
MAX_DATASETS = 200
MAX_FILE_BYTES = 40_000_000
MAX_SCAN_BYTES = 400_000_000


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
        components = []
        total = 0
        for name in sorted(FILES):
            file = folder / name
            if file.is_symlink():
                skipped.append({"dataset_id":dataset_id,"reason":"Symlink source blocked"})
                components=[];break
            if not file.is_file():
                continue
            size = file.stat().st_size
            if size > MAX_FILE_BYTES or scanned_bytes + size > MAX_SCAN_BYTES:
                skipped.append({"dataset_id":dataset_id,
                                "reason":"File or total hashing limit exceeded"})
                components=[];break
            total += size
            scanned_bytes += size
            components.append((name, size, _hash(file)))
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
            "safe_action":"Review dependencies, then archive or move redundant "
                          "user-owned view to recoverable Trash via Data Library. "
                          "The API never deletes a dataset based on a hash match.",
        })
    return {
        "scanned_dataset_views":inspected,
        "scanned_bytes":scanned_bytes,
        "identical_groups":matches,
        "skipped":skipped[:30],
        "deduplication_method":"SHA-256 of every present allowlisted filename and bytes",
        "warning":"Exact duplicate prepared views only. Does not merge two datasets, "
                  "remove raw original Dhan caches, or certify market-data accuracy. "
                  "Source dependency checks remain mandatory.",
    }
