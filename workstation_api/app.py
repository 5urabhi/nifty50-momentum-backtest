"""Loopback-only FastAPI server for the React quantitative research workstation.

All operations are local, read-only with respect to broker APIs, and never send
credentials to the browser. This is a research UI, not an execution service.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock
from typing import Literal
from urllib.request import Request as UrlRequest, urlopen
import os
import json
import uuid

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from index_research.dhan_data import (
    MASTER_URL, Instrument, build_monthly_close, download_candles, save_download,
)
from . import dhan_workspace, service

load_dotenv(service.ROOT / ".env", override=False)

app = FastAPI(title="Local Quantitative Research Workstation", version="0.1.0",
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

RUNNER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research")
JOBS: dict[str, dict] = {}
JOBS_LOCK = Lock()
MAX_UPLOAD = 30 * 1024 * 1024

# Enforce local-only Host and Origin, including against DNS-rebinding. Vite
# proxies same-origin /api requests; localhost clients may call API directly.
HOSTS = {"127.0.0.1", "localhost", "[::1]"}
ORIGINS = {
    "http://127.0.0.1:5173", "http://localhost:5173",
    "http://127.0.0.1:8765", "http://localhost:8765",
}


@app.middleware("http")
async def local_guard(request: Request, call_next):
    from fastapi.responses import JSONResponse
    host = request.headers.get("host", "").split(":")[0]
    if request.headers.get("host", "").startswith("[::1]"):
        host = "[::1]"
    if host not in HOSTS:
        return JSONResponse({"detail": "Local-only workstation: invalid host"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in ORIGINS:
        return JSONResponse({"detail": "Local-only workstation: invalid origin"}, status_code=403)
    return await call_next(request)


def bad(exc: Exception):
    if isinstance(exc, (ValueError, FileNotFoundError, KeyError)):
        raise HTTPException(400, str(exc)) from exc
    raise exc


def _spawn(kind: str, action, *args):
    task_id = uuid.uuid4().hex[:16]
    with JOBS_LOCK:
        active = any(task["status"] in {"queued", "running"} for task in JOBS.values())
        if active:
            raise HTTPException(409, "A research or data job is already in progress")
        JOBS[task_id] = {
            "id": task_id, "kind": kind, "status": "queued",
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
        for old in list(JOBS)[:-50]:
            if JOBS[old]["status"] not in {"queued", "running"}:
                JOBS.pop(old, None)

    def work():
        with JOBS_LOCK:
            JOBS[task_id]["status"] = "running"
        try:
            result = action(*args)
        except Exception as exc:
            # Do not expose vendor responses or secrets in browser logs.
            message = str(exc)
            token = os.getenv("DHAN_ACCESS_TOKEN", "")
            if token:
                message = message.replace(token, "[REDACTED]")
            with JOBS_LOCK:
                JOBS[task_id].update(status="error", error=message[:350])
        else:
            with JOBS_LOCK:
                JOBS[task_id].update(status="complete", result=result)
    RUNNER.submit(work)
    return {"job_id": task_id, "status": "queued"}


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    name: str = Field(default="workstation_experiment", min_length=1, max_length=100)
    factor_weights: dict[Literal["momentum", "low_volatility", "value", "quality", "size"], float] = Field(default_factory=lambda: {"momentum": 1.0})
    top_n: int = Field(default=10, ge=2, le=300)
    weighting: Literal["equal", "score", "inverse_volatility", "minimum_variance", "risk_parity"] = "equal"
    max_weight: float = Field(default=.20, gt=0, le=1)
    rebalance_every: int = Field(default=3, ge=1, le=12)
    cost_bps: float = Field(default=10, ge=0, le=500)
    execution_lag: Literal[0, 1] = 1
    momentum_formation: int = Field(default=12, ge=2, le=60)
    momentum_skip: int = Field(default=1, ge=0, le=12)
    volatility_lookback: int = Field(default=12, ge=3, le=60)
    sector_cap: float | None = Field(default=None, gt=0, le=1)
    validation_start: str | None = None
    final_test_start: str | None = None

    @field_validator("factor_weights")
    @classmethod
    def valid_factors(cls, weights):
        if not weights or not all(0 <= v <= 1 for v in weights.values()):
            raise ValueError("Each selected factor weight must be between 0 and 1")
        if not any(v > 0 for v in weights.values()):
            raise ValueError("Select a positive factor weight")
        return weights

    @field_validator("validation_start", "final_test_start")
    @classmethod
    def date_or_none(cls, value):
        if value in ("", None):
            return None
        from datetime import date
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def feasible(self):
        if self.top_n * self.max_weight < 1 - 1e-10:
            raise ValueError("top_n × max_weight must be at least 1")
        if self.momentum_skip >= self.momentum_formation:
            raise ValueError("momentum_skip must be shorter than momentum_formation")
        if self.validation_start and self.final_test_start and self.validation_start >= self.final_test_start:
            raise ValueError("Validation must precede final test")
        return self


class ModelRequest(BaseModel):
    dataset_id: str
    method: Literal["sample", "shrinkage", "ewma"] = "shrinkage"
    max_weight: float = Field(default=0.3, gt=0, le=1)


class DhanInstrumentRequest(BaseModel):
    label: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    security_id: str = Field(pattern=r"^\d{1,12}$")
    exchange_segment: str = Field(default="NSE_EQ", max_length=25)
    instrument: str = Field(default="EQUITY", max_length=25)
    expiry_code: int = Field(default=0, ge=0, le=9)


class DhanDownloadRequest(BaseModel):
    instruments: list[DhanInstrumentRequest] = Field(min_length=1, max_length=25)
    from_date: str
    to_date: str
    interval: Literal[1, 5, 15, 25, 60] | None = None

    @model_validator(mode="after")
    def dates_are_valid(self):
        from datetime import date, timedelta
        start = date.fromisoformat(self.from_date)
        end = date.fromisoformat(self.to_date)
        if not start < end <= date.today() + timedelta(days=1):
            raise ValueError("Dates must be in chronological order and not in the future")
        if (end - start).days > 365 * 15:
            raise ValueError("Limit downloads to 15 years per job")
        if len({x.label for x in self.instruments}) != len(self.instruments):
            raise ValueError("Instrument labels must be unique")
        return self


@app.get("/api/health")
def health():
    return {
        "ok": True, "mode": "local", "framework": "React/Vite + FastAPI",
        "read_only_market_data": True, "broker_orders_enabled": False,
        "dhan_token_configured": bool(os.getenv("DHAN_ACCESS_TOKEN")),
        "datasets": len(service.datasets()), "completed_runs": len(service.runs()),
    }


@app.get("/api/datasets")
def datasets():
    return {"datasets": service.datasets()}


@app.post("/api/datasets/synthetic")
def synthetic():
    return service.create_synthetic()


@app.post("/api/datasets/import")
async def import_dataset(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Upload a ZIP containing the required flat CSV files")
    try:
        buffer = await file.read(MAX_UPLOAD + 1)
        return service.import_zip(buffer, file.filename)
    except (ValueError, OSError, RuntimeError, __import__("zipfile").BadZipFile) as exc:
        bad(exc)


@app.get("/api/datasets/{dataset_id}/preview")
def preview(dataset_id: str):
    try:
        return service.preview(dataset_id)
    except Exception as exc:
        bad(exc)


@app.get("/api/datasets/{dataset_id}/audit")
def audit(dataset_id: str):
    try:
        return service.audit(dataset_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/experiments")
def experiment(body: RunRequest):
    return _spawn("experiment", service.execute_run, body.dataset_id, body.model_dump(exclude={"dataset_id"}))


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    with JOBS_LOCK:
        status = JOBS.get(job_id)
        if status is None:
            raise HTTPException(404, "Unknown job ID")
        return dict(status)


@app.get("/api/runs")
def runs():
    return {"runs": service.runs()}


@app.get("/api/runs/{run_id}")
def details(run_id: str):
    try:
        return service.run_details(run_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/runs/{run_id}/reports")
def reports(run_id: str):
    return _spawn("reports", service.generate_reports, run_id)


@app.get("/api/runs/{run_id}/files/{file_name}")
def file(run_id: str, file_name: str):
    try:
        path = service.artifact_path(run_id, file_name)
        return FileResponse(path, filename=file_name)
    except Exception as exc:
        bad(exc)


@app.post("/api/models/minimum-variance")
def portfolio_model(body: ModelRequest):
    try:
        return service.portfolio_model(body.dataset_id, body.method, body.max_weight)
    except Exception as exc:
        bad(exc)


@app.get("/api/dhan/status")
def dhan_status():
    master = service.DATA / "dhan" / "instrument_master.csv"
    return {
        "token_configured": bool(os.getenv("DHAN_ACCESS_TOKEN")),
        "instrument_master_available": master.is_file(),
        "instrument_master_bytes": master.stat().st_size if master.is_file() else 0,
        "read_only": True,
    }


def _download_master():
    path = service.DATA / "dhan" / "instrument_master.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    req = UrlRequest(MASTER_URL, headers={"User-Agent": "LocalQuantResearch/1.0"})
    with urlopen(req, timeout=45) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if not data or len(data) > 100 * 1024 * 1024 or b"," not in data[:500]:
        raise ValueError("Dhan instrument master failed content/size validation")
    destination = path.parent / ("instrument_master." + uuid.uuid4().hex[:12] + ".tmp")
    try:
        destination.write_bytes(data)
        # Validate CSV before atomically replacing the existing master.
        frame = pd.read_csv(destination, dtype=str, nrows=5)
        if frame.empty or len(frame.columns) < 5:
            raise ValueError("Instrument master contains no usable records")
        destination.replace(path)
    finally:
        destination.unlink(missing_ok=True)
    return {"path": "data/dhan/instrument_master.csv", "bytes": len(data)}


@app.post("/api/dhan/instruments/refresh")
def refresh_master():
    return _spawn("dhan_master", _download_master)


@app.get("/api/dhan/instruments")
def instruments(query: str = "", limit: int = 35):
    if not 2 <= len(query.strip()) <= 80 or not 1 <= limit <= 100:
        raise HTTPException(400, "Search must be 2-80 characters, limit 1-100")
    path = service.DATA / "dhan" / "instrument_master.csv"
    if not path.is_file():
        raise HTTPException(404, "Download the instrument master first")
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    columns = [column for column in frame if any(name in column.upper() for name in (
        "SYMBOL", "SECURITY", "DISPLAY", "SERIES", "INSTRUMENT", "EXCH", "SEGMENT", "NAME",
    ))]
    if not columns:
        raise HTTPException(400, "Dhan master columns unrecognized")
    selected = frame[columns].fillna("").astype(str)
    mask = selected.apply(lambda col: col.str.contains(query, case=False, regex=False)).any(axis=1)
    return {"columns": columns, "rows": json.loads(selected.loc[mask].head(limit).to_json(orient="records"))}


def _download(request: DhanDownloadRequest):
    instruments = [Instrument(**i.model_dump()) for i in request.instruments]
    folder = service.DATA / "dhan" / "raw" / ("download_" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True)
    saved = []
    for instrument in instruments:
        frame = download_candles(instrument, request.from_date, request.to_date,
                                 interval=request.interval)
        path, manifest = save_download(frame, instrument, folder, request.from_date,
                                       request.to_date, request.interval)
        saved.append({"label": instrument.label, "rows": len(frame),
                      "file": str(path.relative_to(service.ROOT)),
                      "manifest": str(manifest.relative_to(service.ROOT))})
    return {"download_id": folder.name, "files": saved,
            "warning": "Raw Dhan candles are not independently validated total returns."}


@app.post("/api/dhan/download")
def download(body: DhanDownloadRequest):
    if not os.getenv("DHAN_ACCESS_TOKEN"):
        raise HTTPException(400, "Set DHAN_ACCESS_TOKEN in the project .env and restart the workstation")
    return _spawn("dhan_download", _download, body)

class DhanPrepareRequest(BaseModel):
    download_id: str = Field(pattern=r"^download_[0-9a-f]{12}$")


def _prepare_dhan(body: DhanPrepareRequest):
    raw = service.DATA / "dhan" / "raw" / body.download_id
    if not raw.is_dir() or raw.is_symlink():
        raise ValueError("Unknown Dhan download directory")
    manifests = sorted(raw.glob("*_daily.manifest.json"))
    if not manifests or len(manifests) > 25:
        raise ValueError("Prepare requires a nonempty DAILY OHLCV download")
    instruments = []
    for path in manifests:
        if path.is_symlink():
            raise ValueError("Unsafe manifest file")
        record = json.loads(path.read_text())
        if record.get("interval_minutes") is not None or record.get("source") != "DhanHQ REST API v2":
            raise ValueError("Only reviewed local Dhan daily manifests can be prepared")
        instrument = Instrument(**record["instrument"])
        instruments.append(instrument)
    output = service.DATA / "dhan" / "monthly_research" / body.download_id
    if (output / "prices.csv").exists():
        raise ValueError("Prepared price matrix exists; refusing to overwrite")
    target = build_monthly_close(raw, instruments, output)
    return {"dataset_id": "dhan_" + body.download_id, "prices": str(target.relative_to(service.ROOT)),
            "status": "incomplete",
            "warning": "Dhan monthly close alone is NOT benchmark or historical membership evidence. Import separately sourced CSVs before backtesting."}


@app.post("/api/dhan/prepare")
def prepare_dhan(body: DhanPrepareRequest):
    return _spawn("dhan_prepare", _prepare_dhan, body)

class BlackScholesRequest(BaseModel):
    spot: float = Field(gt=0, le=100000000)
    strike: float = Field(gt=0, le=100000000)
    years_to_expiry: float = Field(gt=0, le=100)
    risk_free_rate: float = Field(ge=-1, le=1)
    volatility: float = Field(gt=0, le=5)
    dividend_yield: float = Field(default=0, ge=-1, le=1)
    option_type: Literal["call", "put"] = "call"


@app.post("/api/models/black-scholes")
def price_option(body: BlackScholesRequest):
    from index_research.math_models import black_scholes
    solution = black_scholes(
        s=body.spot, k=body.strike, t=body.years_to_expiry,
        r=body.risk_free_rate, sigma=body.volatility,
        option=body.option_type, dividend_yield=body.dividend_yield,
    )
    return {
        **solution, "kind": "theoretical",
        "warning": "European Black-Scholes-Merton assumptions; prices/Greeks are mathematical estimates, not executable option quotes.",
    }


class GbmRequest(BaseModel):
    initial_price: float = Field(default=100, gt=0, le=10000000)
    annual_drift: float = Field(default=.08, ge=-2, le=2)
    annual_volatility: float = Field(default=.2, ge=0, le=5)
    years: float = Field(default=1, gt=0, le=10)
    steps: int = Field(default=100, ge=10, le=260)
    paths: int = Field(default=150, ge=10, le=500)
    seed: int = Field(default=2026, ge=0, le=2147483647)


@app.post("/api/models/gbm")
def simulate_paths(body: GbmRequest):
    import numpy as np
    from index_research.math_models import simulate_gbm
    paths = simulate_gbm(
        s0=body.initial_price, mu=body.annual_drift,
        sigma=body.annual_volatility, years=body.years,
        steps=body.steps, paths=body.paths, seed=body.seed,
    )
    if not np.isfinite(paths).all():
        raise HTTPException(422, "Simulation exceeded finite numerical range")
    levels = np.percentile(paths, [5, 50, 95], axis=1)
    rows = [{"time": float(i * body.years / body.steps),
             "p05": float(levels[0, i]), "median": float(levels[1, i]),
             "p95": float(levels[2, i])} for i in range(body.steps + 1)]
    return {
        "rows": rows, "paths": body.paths, "seed": body.seed,
        "kind": "synthetic_simulation",
        "warning": "Synthetic geometric Brownian motion generated by Python; not a prediction or calibrated historical result.",
    }


# ====================== Bulk historical data workspace ======================
# The current Dhan master gives tradeable securities, not historical index
# membership. All API requests resolve requested securities server-side.


class DhanBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection: Literal["all_nse", "all_bse", "selected", "watchlist"]
    ids: list[str] = Field(default_factory=list, max_length=6000)
    tickers: list[str] = Field(default_factory=list, max_length=6000)
    from_date: str
    to_date: str
    interval: Literal[1, 5, 15, 25, 60] | None = None
    acknowledged_bulk: bool = False


BATCH_CANCEL_EVENTS: dict[str, Event] = {}


@app.get("/api/dhan/catalog")
def dhan_catalog(query: str = "", exchange: Literal["NSE", "BSE"] = "NSE",
                 page: int = 1, per_page: int = 60, regular_only: bool = True):
    try:
        return dhan_workspace.search_catalog(
            query=query, exchange=exchange, page=page,
            per_page=per_page, regular_only=regular_only,
        )
    except Exception as exc:
        bad(exc)


@app.get("/api/dhan/batches")
def dhan_batches():
    return {"batches": dhan_workspace.list_batches()}


@app.get("/api/dhan/batches/{batch_id}")
def dhan_batch(batch_id: str, page: int = 1, per_page: int = 60,
               status: str = "all"):
    if status not in {"all", "pending", "downloading", "complete", "cached", "no_data", "failed"}:
        raise HTTPException(400, "Unknown status filter")
    try:
        return dhan_workspace.batch_details(batch_id, page, per_page, status)
    except Exception as exc:
        bad(exc)


def _run_bulk(batch_id: str, cancel: Event):
    try:
        return dhan_workspace.run_batch(batch_id, cancel_event=cancel)
    finally:
        BATCH_CANCEL_EVENTS.pop(batch_id, None)


@app.post("/api/dhan/batches")
def create_dhan_batch(body: DhanBatchCreate):
    if not os.getenv("DHAN_ACCESS_TOKEN"):
        raise HTTPException(400, "Set DHAN_ACCESS_TOKEN in the project .env and restart")
    # Refuse a simultaneous second batch before creating its manifest.
    with JOBS_LOCK:
        if any(task["status"] in {"queued", "running"} for task in JOBS.values()):
            raise HTTPException(409, "A research or data job is already running")
    try:
        created = dhan_workspace.create_batch(**body.model_dump())
    except Exception as exc:
        bad(exc)
    batch_id = created["id"]
    cancel = Event()
    BATCH_CANCEL_EVENTS[batch_id] = cancel
    job = _spawn("dhan_bulk", _run_bulk, batch_id, cancel)
    return {**job, "batch": created}


@app.post("/api/dhan/batches/{batch_id}/resume")
def resume_dhan_batch(batch_id: str):
    if not os.getenv("DHAN_ACCESS_TOKEN"):
        raise HTTPException(400, "Dhan token is not configured")
    try:
        state = dhan_workspace.batch_details(batch_id)
    except Exception as exc:
        bad(exc)
    if state["status"] in {"queued", "running"} and batch_id in BATCH_CANCEL_EVENTS:
        raise HTTPException(409, "Batch is already running")
    cancel = Event()
    BATCH_CANCEL_EVENTS[batch_id] = cancel
    try:
        job = _spawn("dhan_bulk", _run_bulk, batch_id, cancel)
    except Exception:
        BATCH_CANCEL_EVENTS.pop(batch_id, None)
        raise
    return {**job, "batch": state}


@app.post("/api/dhan/batches/{batch_id}/cancel")
def cancel_dhan_batch(batch_id: str):
    try:
        dhan_workspace.batch_details(batch_id)
    except Exception as exc:
        bad(exc)
    cancel = BATCH_CANCEL_EVENTS.get(batch_id)
    if cancel is None:
        raise HTTPException(409, "This batch is not running")
    cancel.set()
    return {"batch_id": batch_id, "cancellation_requested": True,
            "warning": "The current instrument request completes before cancellation takes effect"}


@app.post("/api/dhan/batches/{batch_id}/prepare")
def prepare_dhan_batch(batch_id: str):
    try:
        state = dhan_workspace.batch_details(batch_id)
    except Exception as exc:
        bad(exc)
    if state["interval"] is not None:
        raise HTTPException(400, "Only daily candles can be prepared as monthly prices")
    if not state["counts"]["complete"] + state["counts"]["cached"]:
        raise HTTPException(400, "No successfully downloaded daily candles")
    return _spawn("dhan_prepare_batch", dhan_workspace.prepare_batch, batch_id)


@app.get("/api/dhan/history")
def downloaded_candle_preview(instrument_id: str, interval: str = "daily",
                              limit: int = 140):
    if interval not in {"daily", "1", "5", "15", "25", "60"}:
        raise HTTPException(400, "Unknown candle interval")
    try:
        return dhan_workspace.preview_history(
            instrument_id, None if interval == "daily" else int(interval), limit,
        )
    except Exception as exc:
        bad(exc)
