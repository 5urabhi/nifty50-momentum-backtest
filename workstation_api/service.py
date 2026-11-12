"""Local-first research workstation services: explicit data provenance, persistent runs.

Never sends broker orders, invents historical constituents, or publishes API tokens.
All dataset and result lookups are resolved through a server-built allowlist.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import io
import json
import re
import shutil
import tempfile
import uuid
import zipfile

import numpy as np
import pandas as pd

from index_research.data_audit import audit_dataset
from index_research.experiment import ExperimentConfig, run_from_directory
from index_research.fixtures import make_fixture
from index_research.math_models import (
    ewma_covariance, historical_var_es, minimum_variance, sample_covariance,
    shrinkage_covariance,
)
from index_research.pdf_report import generate_pdf_report
from index_research.reports import build_html_report

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results" / "workstation_runs"
REQUIRED = ("prices.csv", "membership.csv", "benchmark.csv")
OPTIONAL = ("fundamentals.csv", "sectors.csv", "corporate_actions.csv", "EVIDENCE_REVIEW.json")
ALLOWED_FILES = set(REQUIRED + OPTIONAL)
ARTIFACTS = {
    "monthly_results.csv", "post_rebalance_weights.csv", "pre_trade_weights.csv",
    "factor_scores.csv", "factor_rank_ic.csv", "portfolio_factor_exposures.csv",
    "concentration.csv", "rolling_metrics.csv", "cost_sensitivity.csv",
    "robustness_grid.csv", "methodology_summary.csv", "methodology_returns.csv",
    "data_quality.json", "dataset_audit.json", "research_manifest.json",
    "research_report.html", "research_paper_draft.pdf",
}
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def _source_dirs():
    yield "synthetic", "Synthetic demonstration", DATA / "synthetic_example", "synthetic"
    yield "research_v1", "Local research data", DATA / "research_v1", "local"
    yield "dhan_monthly", "Dhan monthly close (unadjusted)", DATA / "dhan" / "monthly_research", "dhan"
    for base, prefix, label, kind in (
        (DATA / "workstation_imports", "upload_", "Uploaded", "uploaded"),
        (DATA / "dhan" / "monthly_research", "dhan_", "Dhan prepared", "dhan"),
    ):
        if base.is_dir():
            for path in sorted(base.iterdir()):
                if path.is_dir() and not path.is_symlink() and SAFE_ID.fullmatch(path.name):
                    yield prefix + path.name, label + " · " + path.name, path, kind


def datasets():
    output = []
    for dataset_id, label, folder, kind in _source_dirs():
        missing = [n for n in REQUIRED if not (folder / n).is_file()]
        if kind != "synthetic" and not folder.exists():
            continue
        items = [f.name for f in folder.iterdir() if f.is_file()] if folder.is_dir() else []
        historical = {}
        pit_path = folder / "PIT_MEMBERSHIP_PROVENANCE.json"
        if pit_path.is_file() and not pit_path.is_symlink():
            try:
                historical = json.loads(pit_path.read_text())
                if historical.get("missing_historical_symbols"):
                    missing.append("unresolved_historical_index_prices")
                if historical.get("missing_eligible_price_observations", 0):
                    missing.append("missing_eligible_price_observations")
                if historical.get("source_sha256") is None:
                    missing.append("unverified_membership_source")
            except (ValueError, OSError, TypeError):
                missing.append("unreadable_membership_provenance")
        output.append({
            "id": dataset_id,
            "label": (str(historical.get("index_name")) + " · " + label) if historical else label,
            "kind": kind,
            "ready": not missing, "missing": missing,
            "has_prices": "prices.csv" in items,
            "has_fundamentals": "fundamentals.csv" in items,
            "has_sectors": "sectors.csv" in items,
            "historical_index": historical.get("index_name"),
            "membership_source_commit": historical.get("source_commit"),
            "unresolved_index_symbols": len(historical.get("missing_historical_symbols", [])),
            "files": sorted(items),
            "basis": ("PIT " + str(historical.get("index_name")) +
                      " membership from reconstructed NSE announcements; "
                      "Dhan OHLCV is NOT dividend-reinvested TRI, and provenance is unverified")
                     if historical else
                     "synthetic" if kind == "synthetic" else
                     "raw Dhan monthly closes; not independently total-return adjusted" if kind == "dhan"
                     else "user supplied; source and PIT status unverified",
        })
    return output


def dataset_path(dataset_id: str) -> tuple[Path, dict]:
    if not SAFE_ID.fullmatch(dataset_id):
        raise ValueError("Unknown dataset identifier")
    record = next((item for item in datasets() if item["id"] == dataset_id), None)
    if record is None:
        raise ValueError("Dataset is unavailable")
    for key, _, path, _ in _source_dirs():
        if key == dataset_id:
            return path, record
    raise ValueError("Dataset is unavailable")


def create_synthetic():
    path = DATA / "synthetic_example"
    if not (path / "prices.csv").is_file():
        make_fixture(path)
    return next(item for item in datasets() if item["id"] == "synthetic")


def import_zip(blob: bytes, original_filename: str) -> dict:
    if len(blob) > 30 * 1024 * 1024 or not blob:
        raise ValueError("ZIP must be nonempty and no larger than 30 MiB")
    base = DATA / "workstation_imports"
    base.mkdir(parents=True, exist_ok=True)
    name = "run_" + uuid.uuid4().hex[:12]
    folder = base / name
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        info = archive.infolist()
        names = [entry.filename for entry in info]
        if len(names) > len(ALLOWED_FILES) or len(names) != len(set(names)):
            raise ValueError("ZIP contains duplicate or unexpected entries")
        if not set(REQUIRED).issubset(names) or set(names) - ALLOWED_FILES:
            raise ValueError("ZIP must contain flat prices.csv, membership.csv and benchmark.csv")
        if any(entry.is_dir() or entry.file_size > 25 * 1024 * 1024
               or entry.flag_bits & 1 or (entry.external_attr >> 16) & 0o170000 == 0o120000
               for entry in info):
            raise ValueError("ZIP has an unsafe, encrypted or oversized entry")
        if sum(entry.file_size for entry in info) > 50 * 1024 * 1024:
            raise ValueError("Uncompressed ZIP contents exceed 50 MiB")
        folder.mkdir()
        try:
            for entry in info:
                with archive.open(entry) as source, (folder / entry.filename).open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
            audit = audit_dataset(folder)  # Reject malformed CSVs before making them selectable.
            (folder / "workstation_source.json").write_text(json.dumps({
                "uploaded_filename": Path(original_filename).name[:120],
                "uploaded_utc": datetime.now(timezone.utc).isoformat(),
                "audit_caveat": audit.get("caveat"),
                "status": "unverified",
            }, indent=2))
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return next(item for item in datasets() if item["id"] == "upload_" + name)


def audit(dataset_id: str) -> dict:
    folder, record = dataset_path(dataset_id)
    if not record["ready"]:
        raise ValueError("Dataset missing: " + ", ".join(record["missing"]))
    return audit_dataset(folder)


def preview(dataset_id: str) -> dict:
    folder, record = dataset_path(dataset_id)
    if not record["has_prices"]:
        raise ValueError("Dataset has no prices.csv")
    df = pd.read_csv(folder / "prices.csv", nrows=6000)
    if df.empty or "date" not in df:
        raise ValueError("prices.csv needs a date column")
    return {"dataset": record, "rows": json.loads(df.tail(15).iloc[:, :9].to_json(orient="records")),
            "columns": df.columns.to_list(), "observations_shown": min(15, len(df))}


def _records(path: Path, n: int = 160, columns: list[str] | None = None) -> list[dict]:
    if not path.is_file():
        return []
    df = pd.read_csv(path, nrows=15000)
    if columns:
        df = df[[c for c in columns if c in df.columns]]
    return json.loads(df.tail(n).to_json(orient="records"))


def _json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def _run_path(run_id: str) -> Path:
    if not SAFE_ID.fullmatch(run_id):
        raise ValueError("Unknown run")
    path = RESULTS / run_id
    if not path.is_dir() or path.is_symlink():
        raise ValueError("Unknown run")
    return path


def runs():
    if not RESULTS.is_dir():
        return []
    output = []
    for folder in sorted(RESULTS.iterdir(), reverse=True):
        if not folder.is_dir() or folder.is_symlink() or not SAFE_ID.fullmatch(folder.name):
            continue
        meta = _json(folder / "research_manifest.json")
        status = _json(folder / "workstation_run.json")
        if not meta:
            continue
        output.append({
            "id": folder.name, "created_utc": meta.get("generated_utc"),
            "dataset_id": status.get("dataset_id"),
            "dataset_kind": status.get("dataset_kind", "unknown"),
            "name": meta.get("config", {}).get("name", "Experiment"),
            "metrics_by_split": meta.get("metrics_by_split", {}),
            "coverage": meta.get("coverage", {}),
            "status": meta.get("config", {}).get("dataset_status", "unverified"),
            "first_price_date": meta.get("first_price_date"),
            "last_price_date": meta.get("last_price_date"),
        })
    return output[:100]


def run_details(run_id: str) -> dict:
    path = _run_path(run_id)
    meta = _json(path / "research_manifest.json")
    if not meta:
        raise ValueError("Run has no completed manifest")
    weights = _records(path / "post_rebalance_weights.csv", 1)
    latest_weights = []
    if weights:
        for key, value in weights[-1].items():
            if key not in ("date", "index") and isinstance(value, (float, int)) and value > 0:
                latest_weights.append({"name": key, "weight": value})
    latest_weights.sort(key=lambda x: x["weight"], reverse=True)
    return {
        "id": run_id, "meta": meta, "source": _json(path / "workstation_run.json"),
        "returns": _records(path / "monthly_results.csv", 400),
        "latest_weights": latest_weights[:40],
        "rank_ic": _records(path / "factor_rank_ic.csv", 400),
        "factor_exposures": _records(path / "portfolio_factor_exposures.csv", 400),
        "concentration": _records(path / "concentration.csv", 400),
        "rolling": _records(path / "rolling_metrics.csv", 400),
        "cost_sensitivity": _records(path / "cost_sensitivity.csv", 100),
        "robustness": _records(path / "robustness_grid.csv", 200),
        "methodologies": _records(path / "methodology_summary.csv", 100),
        "audit": _json(path / "dataset_audit.json"),
        "data_quality": _json(path / "data_quality.json"),
        "artifacts": sorted(f.name for f in path.iterdir() if f.is_file() and f.name in ARTIFACTS),
    }


def execute_run(dataset_id: str, params: dict) -> str:
    folder, source = dataset_path(dataset_id)
    if not source["ready"]:
        raise ValueError("Dataset missing: " + ", ".join(source["missing"]))
    factors = {k: float(v) for k, v in params["factor_weights"].items() if float(v) > 0}
    if not factors:
        raise ValueError("Select at least one positive factor weight")
    if params["top_n"] * params["max_weight"] < 1 - 1e-10:
        raise ValueError("Constituent count × maximum weight must be at least 1")
    if params.get("sector_cap") is not None and not source["has_sectors"]:
        raise ValueError("Historical sectors.csv is required to apply a sector cap")
    if set(factors) & {"quality", "value", "size"} and not source["has_fundamentals"]:
        raise ValueError("Value, Quality and Size require publication-dated fundamentals.csv")
    config = ExperimentConfig(
        name=params["name"], factor_weights=factors,
        top_n=params["top_n"], weighting=params["weighting"],
        max_weight=params["max_weight"], rebalance_every=params["rebalance_every"],
        cost_bps=params["cost_bps"], execution_lag=params["execution_lag"],
        momentum_formation=params["momentum_formation"],
        momentum_skip=params["momentum_skip"],
        volatility_lookback=params["volatility_lookback"],
        validation_start=params.get("validation_start") or None,
        final_test_start=params.get("final_test_start") or None,
        dataset_status="static_universe_demo" if source["kind"] == "synthetic" else "unverified",
        benchmark_name="synthetic_market" if source["kind"] == "synthetic" else "user_supplied",
        source_note="SYNTHETIC — not NSE results" if source["kind"] == "synthetic" else
                    "User-supplied research. Historical provenance not independently validated.",
        sector_cap=params.get("sector_cap"),
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    out = RESULTS / run_id
    out.mkdir()
    (out / "workstation_run.json").write_text(json.dumps({
        "dataset_id": dataset_id, "dataset_kind": source["kind"],
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    try:
        run_from_directory(folder, out, config)
    except Exception:
        # Never leave a failed run pretending to have complete artifacts.
        shutil.rmtree(out, ignore_errors=True)
        raise
    return run_id


def generate_reports(run_id: str) -> list[str]:
    path = _run_path(run_id)
    if not (path / "research_manifest.json").is_file():
        raise ValueError("No completed research results")
    build_html_report(path)
    generate_pdf_report(path)
    return sorted(x.name for x in path.iterdir() if x.name in ARTIFACTS)


def artifact_path(run_id: str, file_name: str) -> Path:
    if file_name not in ARTIFACTS:
        raise ValueError("Artifact is not in the export allowlist")
    path = _run_path(run_id) / file_name
    if not path.is_file() or path.is_symlink():
        raise ValueError("Artifact has not been generated")
    return path


def portfolio_model(dataset_id: str, method: str, max_weight: float) -> dict:
    folder, source = dataset_path(dataset_id)
    if not source["has_prices"]:
        raise ValueError("Selected dataset has no prices")
    prices = pd.read_csv(folder / "prices.csv", index_col="date", parse_dates=True)
    if prices.empty or prices.columns.has_duplicates:
        raise ValueError("Price matrix is empty or contains duplicate assets")
    prices = prices.apply(pd.to_numeric, errors="coerce")
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    valid = [col for col in returns.columns if returns[col].notna().sum() >= 20]
    valid = sorted(valid, key=lambda col: (-returns[col].notna().sum(), col))[:12]
    if len(valid) < 2:
        raise ValueError("Need at least two assets with 20 observed monthly returns")
    data = returns[valid].dropna()
    if len(data) < 20:
        raise ValueError("Need at least 20 common monthly returns; no prices were forward-filled")
    if len(valid) * max_weight < 1 - 1e-10:
        raise ValueError("Max weight infeasible for the selected asset count")
    if method == "sample":
        cov = sample_covariance(data)
    elif method == "shrinkage":
        cov = shrinkage_covariance(data, intensity=0.25)
    elif method == "ewma":
        cov = ewma_covariance(data, decay=0.94)
    else:
        raise ValueError("Unknown covariance estimator")
    annual = data.mean() * 12
    solution = minimum_variance(cov, annual, max_weight=max_weight)
    daily = data @ solution.weights  # Inputs are monthly; variable name retained for numeric alignment.
    tail = historical_var_es(daily, confidence=0.95)
    return {
        "dataset_id": dataset_id, "dataset_kind": source["kind"], "method": method,
        "observations": len(data), "assets": list(data.columns),
        "annualized_expected_return": solution.expected_return,
        "annualized_volatility": solution.volatility,
        "historical_monthly_var95": tail["var"],
        "historical_monthly_tail_loss95": tail["expected_shortfall"],
        "weights": [{"name": k, "weight": float(v)} for k, v in solution.weights.items()],
        "correlation": [
            {"asset": label, **{key: float(val) for key, val in row.items()}}
            for label, row in data.corr().iterrows()
        ],
        "warning": "In-sample descriptive optimization on available common monthly observations. Not an out-of-sample result or audited total-return series.",
    }
