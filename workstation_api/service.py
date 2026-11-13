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
OPTIONAL = ("fundamentals.csv", "sectors.csv", "corporate_actions.csv", "EVIDENCE_REVIEW.json",
            "factor_returns.csv", "benchmark_weights.csv", "liquidity.csv")
ALLOWED_FILES = set(REQUIRED + OPTIONAL)
ARTIFACTS = {
    "monthly_results.csv", "post_rebalance_weights.csv", "pre_trade_weights.csv",
    "factor_scores.csv", "factor_rank_ic.csv", "portfolio_factor_exposures.csv",
    "concentration.csv", "rolling_metrics.csv", "cost_sensitivity.csv",
    "robustness_grid.csv", "methodology_summary.csv", "methodology_returns.csv",
    "data_quality.json", "dataset_audit.json", "research_manifest.json",
    "research_report.html", "research_paper_draft.pdf", "liquidity_capacity.csv",
}
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def _source_dirs():
    yield "synthetic", "Synthetic demonstration", DATA / "synthetic_example", "synthetic"
    yield "research_v1", "Local research data", DATA / "research_v1", "local"
    yield "dhan_monthly", "Dhan monthly close (unadjusted)", DATA / "dhan" / "monthly_research", "dhan"
    shared = DATA / "dhan" / "monthly_research" / "shared"
    if (shared / "daily_prices.csv").is_file() and not shared.is_symlink():
        yield "dhan_shared", "Shared Dhan market history (all index universes)", shared, "dhan"
    for base, prefix, label, kind in (
        (DATA / "workstation_imports", "upload_", "Uploaded", "uploaded"),
        (DATA / "dhan" / "monthly_research", "dhan_", "Dhan prepared", "dhan"),
    ):
        if base.is_dir():
            for path in sorted(base.iterdir()):
                if (path.is_dir() and not path.is_symlink() and SAFE_ID.fullmatch(path.name)
                        and not (prefix == "dhan_" and path.name == "shared")):
                    yield prefix + path.name, label + " · " + path.name, path, kind


def datasets(include_archived: bool = False):
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
        aggregation = {}
        aggregation_path = folder / "DAILY_AGGREGATION_PROVENANCE.json"
        if aggregation_path.is_file() and not aggregation_path.is_symlink():
            try:
                aggregation = json.loads(aggregation_path.read_text())
            except (ValueError, OSError, TypeError):
                missing.append("unreadable_daily_aggregation_provenance")
        benchmark_evidence = {}
        benchmark_meta_path = folder / "BENCHMARK_PROVENANCE.json"
        if benchmark_meta_path.is_file() and not benchmark_meta_path.is_symlink():
            try:
                benchmark_evidence = json.loads(benchmark_meta_path.read_text())
            except (OSError, ValueError, TypeError):
                missing.append("invalid_benchmark_provenance")
        # Monthly index simulation needs an explicit pre-formation sample-size
        # gate. A file existing on disk is NOT sufficient information.
        monthly_observations = 0
        price_file = folder / "prices.csv"
        if price_file.is_file() and not price_file.is_symlink():
            try:
                monthly_observations = len(pd.read_csv(price_file, usecols=["date"]))
            except (OSError,ValueError):
                monthly_observations = 0
        output.append({
            "id": dataset_id,
            "label": (str(historical.get("index_name")) + " · " + label) if historical else label,
            "kind": kind,
            "ready": not missing, "missing": missing,
            "has_prices": "prices.csv" in items,
            "monthly_price_observations": monthly_observations,
            "benchmark_kind": benchmark_evidence.get("basis") or
                              ("unclassified" if "benchmark.csv" in items else "missing"),
            "benchmark_is_total_return": benchmark_evidence.get("is_total_return_index", False),
            "independently_verified": benchmark_evidence.get("is_independently_verified", False),
            "has_daily_prices": "daily_prices.csv" in items,
            "source_interval_minutes": aggregation.get("source_interval_minutes"),
            "daily_session_count": aggregation.get("total_daily_observed_dates"),
            "has_daily_ohlcv": (folder / "daily_ohlcv").is_dir(),
            "has_fundamentals": "fundamentals.csv" in items,
            "has_sectors": "sectors.csv" in items,
            "historical_index": historical.get("index_name"),
            "membership_source_commit": historical.get("source_commit"),
            "unresolved_index_symbols": len(historical.get("missing_historical_symbols", [])),
            "files": sorted(items),
            "basis": ("PIT " + str(historical.get("index_name")) +
                      " membership reconstructed from dated NSE announcements; "
                      "daily/monthly observations derived from original Dhan " +
                      (str(aggregation.get("source_interval_minutes")) + "-minute candles; "
                       if aggregation.get("source_interval_minutes") is not None else
                       "daily candles; ") +
                      "corporate-action adjusted total returns and a compatible benchmark "
                      "are NOT independently validated")
                     if historical else
                     "synthetic" if kind == "synthetic" else
                     "raw Dhan monthly closes; not independently total-return adjusted" if kind == "dhan"
                     else "user supplied; source and PIT status unverified",
        })
    if not include_archived:
        from . import research_library
        states = research_library.resource_state_map()
        output = [r for r in output if not states.get("dataset:"+r["id"],{}).get("archived",False)]
    return output


def dataset_path(dataset_id: str) -> tuple[Path, dict]:
    if not SAFE_ID.fullmatch(dataset_id):
        raise ValueError("Unknown dataset identifier")
    record = next((item for item in datasets(include_archived=True) if item["id"] == dataset_id), None)
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
    return next(item for item in datasets(include_archived=True) if item["id"] == "synthetic")


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
            if (folder / "factor_returns.csv").is_file():
                from .active_risk_lab import _read_factor_returns
                _read_factor_returns(folder / "factor_returns.csv")
            if (folder / "benchmark_weights.csv").is_file():
                weights = pd.read_csv(folder / "benchmark_weights.csv")
                if not {"date","ticker","weight"}.issubset(weights.columns) or weights.empty:
                    raise ValueError("benchmark_weights.csv requires dated ticker and weight rows")
                dates=pd.to_datetime(weights["date"],errors="raise")
                values=pd.to_numeric(weights["weight"],errors="raise")
                if (dates.isna().any() or weights[["date","ticker"]].isna().any().any()
                    or weights[["date","ticker"]].duplicated().any()
                    or values.isna().any() or not np.isfinite(values).all()
                    or (values<0).any()
                    or not np.allclose(values.groupby(dates).sum().to_numpy(),1.,atol=1e-6)):
                    raise ValueError("Dated benchmark weight snapshots must be complete, "
                                     "nonnegative and sum to one for each recorded date")
            if (folder / "liquidity.csv").is_file():
                from index_research.liquidity import read_liquidity
                read_liquidity(folder / "liquidity.csv")
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



def attach_tri_benchmark(dataset_id: str, original_csv: bytes, filename: str,
                         *, date_column: str = "Date",
                         level_column: str = "Total Returns Index",
                         index_name: str = "NIFTY 50 TRI",
                         convention: str = "gross_total_return") -> dict:
    """Derive a NEW auditable research view; never mutate Dhan or certified data.

    The uploaded data must be original, lawfully obtained index *levels*.
    A source file without a prior monthly level cannot be used to fabricate
    a first return. Successful structural compatibility is NOT certification.
    """
    from index_research.benchmark_ingestion import normalize_benchmark
    from index_research.data import load_research_inputs
    if not original_csv or len(original_csv) > 30 * 1024 * 1024:
        raise ValueError("Select an original TRI CSV smaller than 30 MB.")
    if not filename.lower().endswith(".csv") or not 1 <= len(filename) <= 200:
        raise ValueError("Upload a CSV containing original total-return index levels.")
    if any(not isinstance(x, str) or not 1 <= len(x.strip()) <= 120
           for x in (date_column, level_column, index_name)):
        raise ValueError("Provide the actual CSV date column, TRI level column and index name.")
    if convention not in {"gross_total_return", "net_total_return"}:
        raise ValueError("Only a clearly identified total-return index is supported here; "
                         "Dhan spot price-index data are not TRI.")
    folder, record = dataset_path(dataset_id)
    if record["kind"] == "synthetic":
        raise ValueError("Synthetic fixtures cannot be converted into real market research.")
    if (folder / "benchmark.csv").exists():
        raise ValueError("This dataset already has a benchmark. Choose its original "
                         "preparation method or start a separate new dataset version.")
    if any(not (folder / f).is_file() or (folder / f).is_symlink()
           for f in ("prices.csv", "membership.csv")):
        raise ValueError("Prepare stock prices and historical membership first.")
    # Source is never removed; even referenced original datasets remain stable.
    if (folder / "DO_NOT_CITE.txt").exists():
        raise ValueError("A synthetic demonstration cannot be relabeled as observed "
                         "research by uploading an unrelated benchmark.")
    if folder.is_symlink() or any(p.is_symlink() for p in folder.iterdir()):
        raise ValueError("Dataset source contains an unsafe link.")
    base = DATA / "workstation_imports"
    base.mkdir(parents=True, exist_ok=True)
    ident = "run_" + uuid.uuid4().hex[:12]
    pending = base / (".pending_" + ident)
    dest = base / ident
    pending.mkdir(mode=0o700)
    try:
        for name in (
            "prices.csv", "membership.csv", "daily_prices.csv", "sectors.csv",
            "fundamentals.csv", "corporate_actions.csv", "liquidity.csv",
            "factor_returns.csv", "benchmark_weights.csv",
            "PIT_MEMBERSHIP_PROVENANCE.json", "DAILY_AGGREGATION_PROVENANCE.json",
            "RETURN_METHODOLOGY.json", "CALENDAR_ALIGNMENT_PROVENANCE.json",
            "OBSERVED_MARKET_SESSIONS.csv",
            "PER_SECURITY_LAST_OBSERVED_SESSIONS.csv",
            "EVIDENCE_REVIEW.json", "FUNDAMENTAL_METHODS.json",
        ):
            file = folder / name
            if file.is_file() and not file.is_symlink():
                shutil.copy2(file, pending / name)
        # The original vendor CSV stays local; do not export or redistribute it
        # through research report ZIPs or the browser dataset download API.
        vendor = pending / "_tri_uploaded_source.csv"
        vendor.write_bytes(original_csv)
        tri, receipt = normalize_benchmark(
            vendor, pending, date_column=date_column,
            level_column=level_column, index_name=index_name,
            return_convention=convention,
        )
        prices = pd.read_csv(pending / "prices.csv", usecols=["date"])
        dates = pd.DatetimeIndex(pd.to_datetime(prices["date"], errors="raise"))
        if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
            raise ValueError("Stock price calendar is invalid.")
        benchmark = pd.read_csv(tri)
        benchmark["date"] = pd.to_datetime(benchmark["date"], errors="raise")
        aligned = benchmark.set_index("date").reindex(dates)
        if aligned["return"].isna().any() or not np.isfinite(aligned["return"]).all():
            gaps = dates[aligned["return"].isna()].strftime("%Y-%m").tolist()
            raise ValueError("TRI levels do not cover every stock month or the "
                             "preceding month. Missing: " + ", ".join(gaps[:8]))
        pd.DataFrame({
            "date": dates,
            "return": aligned["return"].to_numpy(),
        }).to_csv(tri, index=False)
        source = json.loads(receipt.read_text())
        source["source_file"] = "User-uploaded original TRI CSV (kept private and local)"
        source["uploaded_filename"] = Path(filename).name
        source["parent_dataset_id"] = dataset_id
        source["source_is_independently_verified"] = False
        receipt.write_text(json.dumps(source, indent=2))
        (pending / "BENCHMARK_PROVENANCE.json").write_text(json.dumps({
            "basis": "user_supplied_total_return_index",
            "index_name": index_name,
            "return_convention": convention,
            "is_total_return_index": True,
            "is_independently_verified": False,
            "source_sha256": source["source_sha256"],
            "warning": "Structurally aligned user-supplied TRI, NOT independently "
                       "verified against the exchange or source licensed for publication.",
        }, indent=2))
        (pending / "workstation_source.json").write_text(json.dumps({
            "parent_dataset_id": dataset_id,
            "benchmark_uploaded_filename": Path(filename).name,
            "benchmark_sha256": source["source_sha256"],
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "unverified",
            "warning": "No corporate actions, delisting payouts, holdings or "
                       "publication-dated fundamentals were invented.",
        }, indent=2))
        vendor.unlink()  # the original CSV is not an exported dataset artifact
        load_research_inputs(pending)
        dest_parent = dest.parent
        if dest.exists():
            raise FileExistsError("Research view exists; retry to create a new version.")
        pending.rename(dest)
    except Exception:
        shutil.rmtree(pending, ignore_errors=True)
        raise
    result = next(x for x in datasets(include_archived=True)
                  if x["id"] == "upload_" + ident)
    return {**result, "source_dataset_id": dataset_id,
            "benchmark_caveat": "Historical source and dividend-adjusted stock returns "
                                "are not independently verified."}

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


def runs(include_archived: bool = False, limit: int = 100, offset: int = 0):
    if not 1<=limit<=1000 or not 0<=offset<=100000:
        raise ValueError("Invalid research-run paging")
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
    if not include_archived:
        from . import research_library
        states = research_library.resource_state_map()
        output = [r for r in output if not states.get(
            "research_run:"+r["id"],{}).get("archived",False)]
    return output[offset:offset+limit]


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
        "liquidity_capacity": _records(path / "liquidity_capacity.csv", 150),
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
    if set(factors) & {"quality", "value", "size", "yield"} and not source["has_fundamentals"]:
        raise ValueError("Value, Quality, Size and Yield require publication-dated fundamentals.csv")
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
        optimizer_risk_aversion=params.get("optimizer_risk_aversion",3.),
        optimizer_turnover_penalty=params.get("optimizer_turnover_penalty",.02),
        optimizer_tracking_error_limit=params.get("optimizer_tracking_error_limit"),
        optimizer_max_trade_weight=params.get("optimizer_max_trade_weight"),
        liquidity_aum=params.get("liquidity_aum"),
        liquidity_max_participation=params.get("liquidity_max_participation",.05),
        liquidity_execution_days=params.get("liquidity_execution_days",3),
        liquidity_impact_coefficient_bps=params.get("liquidity_impact_coefficient_bps",50.),
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
