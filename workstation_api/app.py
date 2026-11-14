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
import logging
import inspect
import uuid

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from index_research.dhan_data import (
    MASTER_URL, Instrument, build_monthly_close, download_candles, save_download,
)
from . import dhan_auth, dhan_benchmark, dhan_workspace, model_data_manager, model_lab, model_registry, option_quotes, model_readiness, model_input_selector, dhan_option_chain, pit_index, service, shared_market_data, research_library, research_insights, research_advanced, project_bundles, research_integrity, dhan_live_verification, research_learning, research_next, active_risk_lab, research_publication, result_evidence, research_assistant, selection_diagnostics, evidence_bundle, source_inventory, historical_readiness, frozen_study, corporate_action_import, job_recovery

load_dotenv(service.ROOT / ".env", override=False)
# Explicit terminal sink for QuantLab diagnostics. It logs operation names,
# status codes and instrument IDs only; never dump tokens or vendor bodies.
quantlab_logger = logging.getLogger("quantlab")
quantlab_logger.setLevel(logging.INFO)
if not any(getattr(h, "_quantlab_terminal", False) for h in quantlab_logger.handlers):
    terminal_handler = logging.StreamHandler()
    terminal_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    terminal_handler._quantlab_terminal = True
    quantlab_logger.addHandler(terminal_handler)
quantlab_logger.propagate = False
LOG = logging.getLogger("quantlab.api")

app = FastAPI(title="Local Quantitative Research Workstation", version="0.1.0",
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

RUNNER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research")
MAX_ACTIVE_LOCAL_JOBS = 6  # Single worker, bounded queue, never parallel vendor/source writes
JOBS: dict[str, dict] = {}
JOBS_LOCK = Lock()
JOB_FUTURES: dict[str, object] = {}
JOB_RETRY_SPECS: dict[str, tuple] = {}
JOB_STOP_SIGNALS: dict[str, Event] = {}
CANCELLABLE_TASKS = {"workspace_parameter_sweep","workspace_grid_sweep","workspace_validation","workspace_learning","lab_shared_data_extension"}
# Only idempotent, local calculations may be explicitly retried after a restart.
# Never serialize or replay Dhan access, order activity, or single-use frozen tests.
RECOVERABLE_ACTIONS = {
    "workspace_parameter_sweep": research_insights.sweep,
    "workspace_grid_sweep": research_advanced.grid_sweep,
    "workspace_validation": research_insights.validate_out_of_sample,
    "workspace_report": research_library.render_notebook_report,
    "workspace_learning": research_learning.run,
}


class JobCancelled(RuntimeError):
    """Raised only between completed, atomic model or validation steps."""



def _persist_job(snapshot: dict):
    try:
        research_library.store_job(snapshot)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        LOG.warning("Job summary persistence failed for %s: %s", snapshot.get("id"),
                    type(exc).__name__)

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


def _spawn(kind: str, action, *args, **kwargs):
    task_id = uuid.uuid4().hex[:16]
    with JOBS_LOCK:
        active_count = sum(task["status"] in {"queued", "running"} for task in JOBS.values())
        if active_count >= MAX_ACTIVE_LOCAL_JOBS:
            raise HTTPException(409,
                "Local research queue is full (6 pending/running tasks). "
                "Review job progress or cancel an unused queued task.")
        JOBS[task_id] = {
            "id": task_id, "kind": kind, "status": "queued",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "stage": "Waiting for compute worker", "percent": 0,
            "cancellable": kind in CANCELLABLE_TASKS,
        }
        JOB_STOP_SIGNALS[task_id] = Event()
        for old in list(JOBS)[:-50]:
            if JOBS[old]["status"] not in {"queued", "running"}:
                JOBS.pop(old, None)
                JOB_FUTURES.pop(old, None)
                JOB_RETRY_SPECS.pop(old, None)
                JOB_STOP_SIGNALS.pop(old, None)
        if kind in {"workspace_parameter_sweep", "workspace_grid_sweep",
                    "workspace_validation", "workspace_report", "workspace_learning"}:
            JOB_RETRY_SPECS[task_id] = (kind, action, args, kwargs)
        queued_snapshot = dict(JOBS[task_id])
    _persist_job(queued_snapshot)
    if RECOVERABLE_ACTIONS.get(kind) is action:
        try:
            job_recovery.save(task_id, kind, args, kwargs)
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            LOG.warning("Persistent restart retry unavailable: kind=%s reason=%s",
                        kind, type(exc).__name__)

    def work():
        LOG.info("QuantLab background job started: kind=%s job_id=%s", kind, task_id)
        with JOBS_LOCK:
            JOBS[task_id]["status"] = "running"
            JOBS[task_id]["stage"] = "Preparing research inputs"
            starting_snapshot = dict(JOBS[task_id])
        _persist_job(starting_snapshot)

        def progress(percent: float, stage: str):
            signal=JOB_STOP_SIGNALS.get(task_id)
            if signal is not None and signal.is_set():
                raise JobCancelled("Research cancelled safely between numerical operations")
            if not isinstance(percent,(int,float)) or not 0<=percent<=100:
                raise ValueError("Invalid computational progress")
            with JOBS_LOCK:
                JOBS[task_id]["percent"] = round(float(percent),1)
                JOBS[task_id]["stage"] = str(stage)[:140]

        try:
            options=dict(kwargs)
            if "progress" in inspect.signature(action).parameters:
                options["progress"]=progress
            result = action(*args, **options)
        except JobCancelled as exc:
            with JOBS_LOCK:
                JOBS[task_id].update(status="cancelled",stage=str(exc),cancellable=False)
                stopped=dict(JOBS[task_id])
            _persist_job(stopped)
        except Exception as exc:
            # Do not expose vendor responses or secrets in browser logs.
            message = str(exc)
            token = os.getenv("DHAN_ACCESS_TOKEN", "")
            if token:
                message = message.replace(token, "[REDACTED]")
            LOG.error("QuantLab background job failed: kind=%s job_id=%s message=%s",
                      kind, task_id, message[:350])
            with JOBS_LOCK:
                JOBS[task_id].update(status="error", error=message[:350])
                failure_snapshot = dict(JOBS[task_id])
            _persist_job(failure_snapshot)
        else:
            LOG.info("QuantLab background job completed: kind=%s job_id=%s", kind, task_id)
            with JOBS_LOCK:
                JOBS[task_id].update(status="complete", result=result, percent=100,
                                     stage="Output saved", cancellable=False)
                success_snapshot = dict(JOBS[task_id])
            _persist_job(success_snapshot)
    future = RUNNER.submit(work)
    with JOBS_LOCK:
        JOB_FUTURES[task_id] = future
    return {"job_id": task_id, "status": "queued"}


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    name: str = Field(default="workstation_experiment", min_length=1, max_length=100)
    factor_weights: dict[Literal["momentum", "low_volatility", "value", "quality", "size", "yield"], float] = Field(default_factory=lambda: {"momentum": 1.0})
    top_n: int = Field(default=10, ge=2, le=300)
    weighting: Literal["equal", "score", "inverse_volatility", "minimum_variance", "risk_parity", "benchmark_relative"] = "equal"
    max_weight: float = Field(default=.20, gt=0, le=1)
    rebalance_every: int = Field(default=3, ge=1, le=12)
    cost_bps: float = Field(default=10, ge=0, le=500)
    execution_lag: Literal[0, 1] = 1
    momentum_formation: int = Field(default=12, ge=2, le=60)
    momentum_skip: int = Field(default=1, ge=0, le=12)
    volatility_lookback: int = Field(default=12, ge=3, le=60)
    sector_cap: float | None = Field(default=None, gt=0, le=1)
    optimizer_risk_aversion: float = Field(default=3., ge=0, le=100)
    optimizer_turnover_penalty: float = Field(default=.02, ge=0, le=100)
    optimizer_tracking_error_limit: float | None = Field(default=None, gt=0, le=5)
    optimizer_max_trade_weight: float | None = Field(default=None, gt=0, le=1)
    liquidity_aum: float | None = Field(default=None, gt=0, le=1e15)
    liquidity_max_participation: float = Field(default=.05, gt=0, le=1)
    liquidity_execution_days: int = Field(default=3, ge=1, le=30)
    liquidity_impact_coefficient_bps: float = Field(default=50., ge=0, le=10000)
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



@app.post("/api/datasets/{dataset_id}/add-actions")
async def dataset_attach_corporate_action_total_returns(
    dataset_id: str, file: UploadFile = File(...),
    price_basis: Literal["split_bonus_adjusted","raw_unadjusted"] = Form("split_bonus_adjusted"),
    acknowledge_unverified: bool = Form(False),
):
    """Build new research wealth view from original daily closes + cited event CSV.

    Does not change original Dhan data or treat declared events as certified.
    """
    if not acknowledge_unverified:
        raise HTTPException(400, "Confirm that market-event completeness remains independently unverified")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Choose an original action ledger CSV with actual ex-date evidence")
    try:
        payload = await file.read(corporate_action_import.MAX_ACTION_BYTES + 1)
        return corporate_action_import.import_adjusted(
            dataset_id, payload, price_basis=price_basis)
    except (ValueError, OSError, RuntimeError) as exc:
        bad(exc)


@app.post("/api/datasets/{dataset_id}/add-tri")
async def dataset_add_total_return_benchmark(
    dataset_id: str, file: UploadFile = File(...),
    confirmed_tri: bool = Form(...),
    date_column: str = Form("Date"),
    level_column: str = Form("Total Returns Index"),
    index_name: str = Form("NIFTY 50 TRI"),
    convention: str = Form("gross_total_return"),
):
    """Make a new, explicitly unverified dataset from user-sourced TRI levels."""
    if not confirmed_tri:
        raise HTTPException(400, "Confirm this file contains actual TRI levels, not spot prices")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Choose a permitted original TRI levels CSV")
    try:
        payload = await file.read(MAX_UPLOAD + 1)
        return service.attach_tri_benchmark(
            dataset_id, payload, file.filename,
            date_column=date_column, level_column=level_column,
            index_name=index_name, convention=convention,
        )
    except (OSError, ValueError, RuntimeError) as exc:
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
def runs(limit: int = 100, offset: int = 0):
    if not 1<=limit<=500 or not 0<=offset<=100000:
        raise HTTPException(400,"Invalid research-run page")
    return {"runs": service.runs(limit=limit,offset=offset)}


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


class LabRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=2, max_length=45, pattern=r"^[a-z_]+$")
    dataset_id: str | None = Field(default=None, max_length=120)
    params: dict[str, float | int | str] = Field(default_factory=dict)


GUIDE_FILES = {
    "user-guide": "QUANTLAB_USER_GUIDE.md",
    "model-catalog": "MODEL_LABORATORY_GUIDE.md",
    "reproducibility": "QUANTLAB_REPRODUCIBILITY.md",
    "workspace": "RESEARCH_WORKSPACE_GUIDE.md",
    "metrics": "METRIC_REFERENCE.md",
}


@app.get("/api/guide/{topic}", response_class=PlainTextResponse)
def research_guide_document(topic: Literal["user-guide", "model-catalog", "reproducibility", "workspace", "metrics"]):
    """Read one allowlisted repository document; no filesystem path input."""
    doc=service.ROOT / "docs" / GUIDE_FILES[topic]
    if not doc.is_file() or doc.is_symlink():
        raise HTTPException(404, "QuantLab guide document not installed")
    return PlainTextResponse(doc.read_text(encoding="utf-8"),
                             media_type="text/plain; charset=utf-8")


@app.get("/api/lab/catalog")
def research_model_catalog():
    return {"models": model_registry.MODELS,
            "version": "model-laboratory-v1",
            "warning": "Synthetic experiments, theoretical curves and observed fits are separately labeled."}


@app.get("/api/lab/readiness")
def research_model_readiness(dataset_id: str):
    try:
        return model_lab.readiness(dataset_id)
    except Exception as exc:
        bad(exc)




@app.get("/api/lab/model-inputs")
def lab_specific_historical_inputs(dataset_id: str, model_id: str):
    """Exact per-stock eligibility, not availability-ranked auto substitution."""
    try:
        return model_input_selector.inspect(dataset_id, model_id)
    except (ValueError, OSError, FileNotFoundError, KeyError) as exc:
        bad(exc)


@app.get("/api/lab/model-readiness")
def lab_model_readiness_overview(dataset_id: str = ""):
    """One-pass model-specific source checklist; math-only is not empirical."""
    try:
        return model_readiness.overview(dataset_id or None)
    except (ValueError, OSError, TypeError) as exc:
        bad(exc)


@app.post("/api/lab/option-quotes/import")
async def lab_import_original_option_quotes(
    dataset_id: str = Form(...), file: UploadFile = File(...),
    confirm_original_quote: bool = Form(False),
):
    if not confirm_original_quote:
        raise HTTPException(400, "Confirm that this CSV is an original provider option bid/ask snapshot")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload an original option quote CSV file")
    try:
        raw=await file.read(option_quotes.MAX_BYTES+1)
        return option_quotes.import_quotes(dataset_id, raw)
    except (ValueError, OSError) as exc:
        bad(exc)



class DhanOptionChainRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    dataset_id: str = Field(min_length=1,max_length=120)
    underlying: Literal["NIFTY50","BANKNIFTY"] = "NIFTY50"
    confirm_readonly: bool = False


@app.post("/api/lab/option-quotes/dhan")
def lab_capture_dhan_live_option_chain(body: DhanOptionChainRequest):
    """Opted-in, local-token only, rate-limited Dhan QUOTE read. No order API."""
    if not body.confirm_readonly:
        raise HTTPException(400,"Confirm the authorized read-only Dhan option-chain data request")
    try:
        service.dataset_path(body.dataset_id)
        if not os.getenv("DHAN_ACCESS_TOKEN","").strip():
            raise ValueError("Configure DHAN_ACCESS_TOKEN in your local ignored .env and restart QuantLab")
        return _spawn("lab_dhan_optionchain", dhan_option_chain.capture,
                      body.dataset_id,body.underlying)
    except (ValueError,OSError) as exc:
        bad(exc)


@app.get("/api/lab/option-quotes")
def lab_list_option_quote_snapshots(dataset_id: str):
    try:
        return {"snapshots": option_quotes.list_for(dataset_id)}
    except (ValueError, OSError) as exc:
        bad(exc)


@app.post("/api/lab/run")
def research_model_run(body: LabRunRequest):
    try:
        result = model_lab.run_model(body.model_id, body.dataset_id, body.params)
        return model_lab.save_result(result)
    except (ValueError, FileNotFoundError, KeyError, RuntimeError, FloatingPointError) as exc:
        # Numerical nonconvergence is a user-actionable calculation failure,
        # not an opaque 500 or an invented model result.
        raise HTTPException(400, str(exc)) from exc



class LabDataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(pattern=r"^[a-z_]+$", min_length=2, max_length=45)
    dataset_id: str = Field(min_length=1, max_length=120)
    params: dict[str, float | int | str] = Field(default_factory=dict)
    confirm_download: bool = False


@app.get("/api/lab/data-requirements")
def research_lab_requirements(model_id: str, dataset_id: str = "",
                              assets: int = 8, train_window: int = 60,
                              target: str = "", ticker: str = "",
                              quote: str = ""):
    try:
        if model_id not in model_registry.CATALOG:
            raise ValueError("Unknown registered model")
        spec = model_registry.CATALOG[model_id]
        # Only the two readiness-relevant values enter this read-only query.
        params = {}
        if any(p["key"] == "assets" for p in spec["parameters"]):
            params["assets"] = assets
        if model_id == "rolling_vol":
            params["train_window"] = train_window
        if model_id in {"gbm_fit","ou_fit","merton_fit","heston_proxy"}:
            params["target"] = target or ("benchmark_tri" if model_id=="gbm_fit" else "stock")
            params["ticker"] = ticker
        if model_registry.CATALOG[model_id]["mode"] == "market":
            params["quote"] = quote
        plan = model_data_manager.inspect(model_id, dataset_id or None, params)
        return {**plan, "next_action": model_data_manager.recommend_next_action(plan)}
    except Exception as exc:
        bad(exc)


@app.post("/api/lab/data-requirements/extend")
def extend_research_lab_data(body: LabDataRequest):
    if not body.confirm_download:
        raise HTTPException(400, "Explicit download confirmation is required")
    try:
        plan = model_data_manager.inspect(body.model_id, body.dataset_id, body.params)
        if not plan.get("can_download"):
            raise ValueError(plan.get("download_explanation") or "No download needed or unavailable")
        return {**_spawn("lab_shared_data_extension", model_data_manager.execute,
                         body.model_id, body.dataset_id, body.params),
                "planned": plan, "destination_dataset_id": shared_market_data.SHARED_ID}
    except Exception as exc:
        bad(exc)


@app.post("/api/lab/data-requirements/reuse-cached")
def reuse_research_lab_cache():
    """User-confirmed offline migration from existing Dhan cache only."""
    def migrate():
        count = 0
        results = []
        for row in dhan_workspace.catalog():
            reused = shared_market_data.reuse_cached(row)
            count += reused["rows_appended"]
            if reused["rows_appended"]:
                results.append(row["id"])
        summary = shared_market_data.publish_views()
        return {**summary, "rows_appended": count, "instruments_updated": results}
    return _spawn("lab_shared_cache_migration", migrate)


@app.get("/api/lab/runs")
def research_model_runs(limit: int = 30, offset: int = 0):
    if not 1<=limit<=500 or not 0<=offset<=100000:
        raise HTTPException(400,"Invalid model-run page")
    return {"runs": model_lab.list_saved_models(limit=limit,offset=offset)}


@app.get("/api/lab/runs/{run_id}")
def research_model_run_details(run_id: str):
    try:
        return model_lab.read_saved_model(run_id)
    except Exception as exc:
        bad(exc)


# ---------------------- Research workspace ----------------------
# All files remain local. Only allowlisted metadata is exchanged with React.
class LibraryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["configuration","project","notebook","chart","comparison","dashboard","note","report","study"]
    title: str = Field(min_length=1, max_length=120)
    payload: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=20)


class LibraryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    payload: dict | None = None
    tags: list[str] | None = None
    favorite: bool | None = None
    archived: bool | None = None


class LibraryAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["archive","unarchive","trash","restore","favorite","unfavorite","purge"]
    confirm: bool = False


class LibraryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=50)
    action: Literal["archive","unarchive","trash","restore","favorite","unfavorite"]


class ResourceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["dataset","model_run","research_run"]
    item_id: str = Field(min_length=1, max_length=90)
    action: Literal["archive","unarchive","trash","restore","purge"]
    confirm: bool = False


class SavedComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[dict] = Field(min_length=2, max_length=8)
    normalize: Literal["none","base100","zscore"] = "none"
    alignment: Literal["intersection","union"] = "intersection"
    title: str = Field(default="Saved model comparison", max_length=120)
    layout: Literal["overlay","split"] = "overlay"


class SweepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(pattern=r"^[a-z_]+$")
    dataset_id: str | None = None
    params: dict = Field(default_factory=dict)
    parameter: str
    values: list[float] = Field(min_length=2, max_length=16)
    metric_label: str = Field(default="", max_length=120)


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    model: Literal["equal","inverse_volatility","min_variance","risk_parity","max_diversification"] = "min_variance"
    assets: int = Field(default=8, ge=2, le=18)
    train_window: int = Field(default=180, ge=30, le=1500)
    test_step: int = Field(default=20, ge=1, le=252)
    max_weight: float = Field(default=.3, gt=0, le=1)
    mode: Literal["walk_forward","single_holdout"] = "walk_forward"
    seed: int = Field(default=2026, ge=0, le=2147483647)


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    shocks: dict[str, float]


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notebook_id: str
    format: Literal["html","markdown"] = "html"


@app.get("/api/workspace/records")
def workspace_records(kind: str | None = None, q: str = "",
                      archived: bool = False, trashed: bool = False):
    try:
        return {"records": research_library.list_items(kind, q, archived=archived, trashed=trashed)}
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/records")
def workspace_create(body: LibraryCreate):
    try:
        return research_library.create(**body.model_dump())
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/records/{item_id}")
def workspace_get(item_id: str):
    try:
        return research_library.get(item_id)
    except Exception as exc:
        bad(exc)


@app.patch("/api/workspace/records/{item_id}")
def workspace_update(item_id: str, body: LibraryUpdate):
    try:
        return research_library.update(item_id, **body.model_dump(exclude_unset=True))
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/records/{item_id}/action")
def workspace_record_action(item_id: str, body: LibraryAction):
    try:
        return research_library.action(item_id, body.action, confirm=body.confirm)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/batch")
def workspace_batch(body: LibraryBatch):
    try:
        return research_library.batch_action(body.ids, body.action)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/resources")
def workspace_resources(include_trashed: bool = False):
    return {"resources": research_library.resource_listing(include_trashed=include_trashed)}


@app.get("/api/workspace/resources/dependencies")
def workspace_dependencies(kind: Literal["dataset","model_run","research_run"], item_id: str):
    try:
        return {"dependencies": research_library.resource_dependencies(kind, item_id)}
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/resources/action")
def workspace_resource_action(body: ResourceAction):
    try:
        return research_library.resource_action(body.kind, body.item_id, body.action,
                                                confirm=body.confirm)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/storage")
def workspace_disk_usage():
    return research_library.disk_usage()


@app.get("/api/workspace/search")
def workspace_search(q: str):
    try:
        return {"results": research_library.global_search(q)}
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/quality/{dataset_id}")
def workspace_data_quality(dataset_id: str):
    try:
        return research_insights.inspect_quality(dataset_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/compare")
def workspace_compare(body: SavedComparison):
    try:
        return research_insights.compare(**body.model_dump())
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/sweep")
def workspace_sweep(body: SweepRequest):
    if body.model_id not in model_registry.CATALOG:
        raise HTTPException(400, "Unknown registered research model")
    return _spawn("workspace_parameter_sweep", research_insights.sweep,
                  body.model_id, body.dataset_id, body.params, body.parameter, body.values,
                  metric_label=body.metric_label)


@app.post("/api/workspace/validate")
def workspace_validate(body: ValidationRequest):
    return _spawn("workspace_validation", research_insights.validate_out_of_sample,
                  **body.model_dump())


@app.post("/api/workspace/scenario")
def workspace_scenario(body: ScenarioRequest):
    try:
        return research_insights.scenario(body.run_id, body.shocks)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/studies/{study_id}/returns.csv")
def workspace_study_returns(study_id: str):
    try:
        path = research_insights.study_returns_path(study_id)
        return FileResponse(path, filename="quantlab_" + study_id + "_returns.csv",
                            media_type="text/csv")
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/reproducibility/{run_id}")
def workspace_reproducibility(run_id: str, recompute: bool = False):
    try:
        return research_insights.verify_reproducibility(run_id, recompute=recompute)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/reports")
def workspace_reports(body: ReportRequest):
    return _spawn("workspace_report", research_library.render_notebook_report,
                  body.notebook_id, format=body.format)



class ReportEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=90000)


@app.get("/api/workspace/reports/{report_id}/source")
def workspace_report_source(report_id: str):
    try:
        return research_library.report_source(report_id)
    except Exception as exc:
        bad(exc)


@app.put("/api/workspace/reports/{report_id}/source")
def workspace_report_edit(report_id: str, body: ReportEdit):
    try:
        return research_library.edit_report(report_id, body.content)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/reports/{report_id}/{format}")
def workspace_report_file(report_id: str, format: Literal["html","markdown","pdf"]):
    try:
        path = research_library.report_path(report_id, format)
        return FileResponse(path, filename=path.name)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/data-maintenance/duplicates")
def inspect_duplicate_datasets():
    """Manual bounded hash inventory; never modifies or deletes sources."""
    try:
        return source_inventory.scan()
    except (ValueError, OSError, FileNotFoundError, KeyError) as exc:
        bad(exc)

class DuplicateTrashRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signature_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm: bool = False


@app.post("/api/workspace/data-maintenance/duplicates/{dataset_id}/trash")
def trash_verified_duplicate(dataset_id: str, body: DuplicateTrashRequest):
    try:
        return source_inventory.trash_exact_duplicate(
            dataset_id, body.signature_sha256, confirm=body.confirm)
    except (ValueError, OSError, FileNotFoundError, KeyError) as exc:
        bad(exc)



def _job_next_action(job: dict) -> str:
    status = job.get("status")
    if status == "queued":
        return "This job will start automatically in queue order when the local compute worker is free."
    if status == "running":
        return ("Request cancellation at the next safe checkpoint."
                if job.get("cancellable") else
                "This numerical operation cannot be interrupted safely while running.")
    if status == "complete":
        return "Inspect saved outputs in Results Studio or download this job's result artifact."
    if status == "cancelled":
        return "No more work is running. Check partial data in Data Library, then explicitly re-run if needed."
    if status == "interrupted":
        if job.get("retryable"):
            return ("Python restarted. Click Retry to recheck original file hashes and "
                    "explicitly rerun the same calculation; never auto-resume.")
        return "Python restarted. Reopen your saved configuration and explicitly rerun; no completion is implied."
    if status != "error":
        return "Inspect the job details and associated local research evidence."
    message = str(job.get("error") or "").lower()
    if any(x in message for x in ("token", "401", "authorization", "unauthorized", "credentials")):
        return "Refresh the local ignored Dhan .env credential, then verify read-only provider access."
    if any(x in message for x in ("429", "rate limit", "quota", "too many requests")):
        return "Provider throttling: respect its cooldown and retry only after the source allows more requests."
    if any(x in message for x in ("missing", "insufficient", "not enough", "no common", "source")):
        return "Open Model Laboratory readiness or Data Library to resolve the exact original-source shortfall."
    if any(x in message for x in ("option", "quote", "bid", "ask")):
        return "Fetch authorized read-only original option quotes or import a source-dated provider CSV."
    return "Inspect the saved job error and local Python terminal logs; update inputs before retrying."


@app.get("/api/workspace/jobs")
def workspace_jobs():
    with JOBS_LOCK:
        live = [dict(row) for row in list(JOBS.values())[-75:][::-1]]
        queued_ids = [id for id, row in JOBS.items() if row["status"] == "queued"]
        retry_ids = set(JOB_RETRY_SPECS)
    seen = {row["id"] for row in live}
    historical = [row for row in research_library.list_job_history(100)
                  if row["id"] not in seen]
    all_jobs = (live + historical)[:100]
    for row in all_jobs:
        row["retryable"] = row.get("status") in {"error", "cancelled", "interrupted"} and (
            row["id"] in retry_ids or job_recovery.available(row["id"]))
        row["queue_position"] = (
            queued_ids.index(row["id"]) + 1 if row["id"] in queued_ids else None)
        row["next_action"] = _job_next_action(row)
    return {"jobs": all_jobs, "max_pending_or_running": MAX_ACTIVE_LOCAL_JOBS,
            "worker_concurrency": 1}


@app.post("/api/workspace/jobs/{job_id}/cancel")
def workspace_cancel_job(job_id: str):
    with JOBS_LOCK:
        status = JOBS.get(job_id)
        if not status:
            raise HTTPException(404, "Unknown research job")
        if status["status"] == "running":
            if not status.get("cancellable"):
                raise HTTPException(409,"This operation cannot be safely interrupted while running")
            JOB_STOP_SIGNALS[job_id].set()
            status["stage"]="Cancellation requested; waiting for a safe checkpoint"
            return dict(status)
        if status["status"] != "queued":
            raise HTTPException(409, "Only queued or checkpoint-cancellable running jobs can be cancelled")
        future = JOB_FUTURES.get(job_id)
        if future is None or not future.cancel():
            raise HTTPException(409, "Job is already starting")
        status["status"] = "cancelled"
        status["cancellable"] = False
        completed_snapshot = dict(status)
    _persist_job(completed_snapshot)
    return completed_snapshot


@app.post("/api/workspace/jobs/{job_id}/retry")
def workspace_retry_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        spec = JOB_RETRY_SPECS.get(job_id)
        if job and job["status"] not in {"error", "cancelled"}:
            raise HTTPException(409, "Only failed, cancelled or interrupted jobs can be retried")
    if spec and job:
        kind, action, args, kwargs = spec
        if job_recovery.available(job_id):
            try:
                job_recovery.restore(job_id)  # Refuse changed data or code even within one process.
            except (ValueError, OSError) as exc:
                raise HTTPException(409, str(exc)) from exc
        return _spawn(kind, action, *args, **kwargs)
    record = next((row for row in research_library.list_job_history(100)
                   if row["id"] == job_id), None)
    if record is None or record["status"] not in {"interrupted", "error", "cancelled"}:
        raise HTTPException(409, "No interrupted/failed research job available for explicit retry")
    try:
        kind, args, kwargs = job_recovery.restore(job_id)
    except (ValueError, OSError, TypeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    action = RECOVERABLE_ACTIONS.get(kind)
    if action is None:
        raise HTTPException(409, "This job cannot be safely retried after restart")
    return _spawn(kind, action, *args, **kwargs)


# -------------------------- Advanced research -------------------------
class PlotBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str = Field(min_length=1,max_length=120)
    fields: list[str] = Field(min_length=1,max_length=18)
    kind: Literal["line","scatter","histogram","kde","qq","drawdown",
                  "cumulative","rolling_volatility","correlation"] = "line"
    transform: Literal["price","return","log_return","base100","zscore"] = "return"
    first: str | None = None
    last: str | None = None
    lookback: int = Field(default=20,ge=2,le=252)
    title: str | None = Field(default=None,max_length=120)


class DiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    asset: str
    start: str | None = None
    end: str | None = None


class FactorAttributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    target: str
    factors: list[str] = Field(min_length=1,max_length=6)
    training_fraction: float = Field(default=.7,ge=.5,le=.85)


class SignificanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_ids: list[str] = Field(min_length=1,max_length=6)
    seed: int = Field(default=2026,ge=0,le=2147483647)


class GridResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(pattern=r"^[a-z_]+$")
    dataset_id: str | None = None
    axes: dict[str,list[float]] = Field(min_length=1,max_length=2)
    params: dict = Field(default_factory=dict)
    metric_name: str | None = Field(default=None,max_length=120)
    confirm_run: bool = False


class ResourceMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None,max_length=120)
    description: str | None = Field(default=None,max_length=2500)
    tags: list[str] | None = Field(default=None,max_length=20)
    favorite: bool | None = None


class NotebookAttachmentRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    kind: Literal["chart","run"]
    source_id: str = Field(min_length=1,max_length=120)


@app.post("/api/workspace/notebooks/{notebook_id}/attach")
def workspace_notebook_attach(notebook_id: str,body:NotebookAttachmentRequest):
    try:
        return research_library.attach_notebook_reference(notebook_id,body.kind,body.source_id)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/plot-builder/columns/{dataset_id}")
def research_plot_builder_columns(dataset_id: str):
    try:
        return research_advanced.columns(dataset_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/plot-builder")
def research_plot_builder(body: PlotBuildRequest):
    try:
        return research_advanced.build_plot(**body.model_dump())
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/diagnostics")
def research_diagnostics(body: DiagnosticRequest):
    try:
        return research_advanced.diagnose(**body.model_dump())
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/factor-attribution")
def research_factor_attribution(body: FactorAttributionRequest):
    try:
        return research_advanced.factor_proxy_attribution(**body.model_dump())
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/significance")
def research_significance(body: SignificanceRequest):
    try:
        return research_advanced.significance(**body.model_dump())
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/grid/estimate")
def research_grid_estimate(body: GridResearchRequest):
    try:
        preview=research_advanced.grid_estimate(body.model_id,body.axes,body.params)
        return {k:v for k,v in preview.items() if k!="configurations"}
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/grid/run")
def research_grid_run(body: GridResearchRequest):
    if not body.confirm_run:
        raise HTTPException(400,"Explicitly confirm the estimated experiment grid")
    try:
        research_advanced.grid_estimate(body.model_id,body.axes,body.params)
        return _spawn("workspace_grid_sweep",research_advanced.grid_sweep,
                      body.model_id,body.dataset_id,body.axes,body.params,
                      metric_name=body.metric_name)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/guided/{goal}")
def research_guided(goal: Literal["portfolio_allocation","volatility","tail_risk",
                  "stochastic_models","derivatives","factor_exposures"],
                    dataset_id: str = ""):
    try:
        return research_advanced.guided(goal,dataset_id or None)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/resources/metadata")
def research_resource_metadata(kind: Literal["dataset","model_run","research_run"],item_id: str):
    try:
        return research_library.resource_info(kind,item_id)
    except Exception as exc:
        bad(exc)


@app.patch("/api/workspace/resources/metadata")
def research_resource_edit(kind: Literal["dataset","model_run","research_run"],
                           item_id: str,body: ResourceMetadataRequest):
    try:
        return research_library.set_resource_info(kind,item_id,
                            **body.model_dump(exclude_unset=True))
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/resources/duplicate-model/{run_id}")
def research_resource_duplicate_model(run_id: str):
    try:
        return research_library.duplicate_model_run(run_id)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/projects/{project_id}/bundle.zip")
def research_project_export(project_id: str):
    try:
        path=project_bundles.bundle_path(project_id)
        return FileResponse(path,filename="quantlab_project_"+project_id+".zip",
                            media_type="application/zip")
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/projects/import-bundle")
async def research_project_import_bundle(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400,"Upload a QuantLab .zip project bundle")
    try:
        content=await file.read(project_bundles.MAX_BUNDLE+1)
        return project_bundles.import_bundle(content)
    except Exception as exc:
        bad(exc)


# ---------------------- Remaining research integrity ----------------------
class ResearchEvidenceReference(BaseModel):
    model_config=ConfigDict(extra="forbid")
    category: Literal["prices","membership","actions","benchmark","delistings",
                      "fundamentals","costs","execution"]
    source_url: str = Field(min_length=12,max_length=500)
    as_of: str = Field(min_length=10,max_length=10)
    explanation: str = Field(default="",max_length=1200)


class LiveDhanProbeRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    dataset_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    column: str = Field(min_length=1,max_length=80)
    confirm: bool = False


class LearningStudyRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    dataset_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    asset: str = Field(min_length=1,max_length=100)
    method: Literal["ridge","random_forest","hist_gradient_boosting","tabular_q"] = "ridge"
    train_fraction: float = Field(default=.70,ge=.60,le=.85)
    cost_bps: float = Field(default=8.,ge=0.,le=250.)
    seed: int = Field(default=2026,ge=0,le=2147483647)
    confirm: bool = False


@app.get("/api/workspace/integrity/{dataset_id}")
def workstation_integrity(dataset_id: str):
    try:
        return research_integrity.inspect(dataset_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/integrity/{dataset_id}/sources")
def workstation_source_reference(dataset_id: str,body: ResearchEvidenceReference):
    try:
        return research_integrity.add_source(dataset_id,**body.model_dump())
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/dhan-live/plan")
def workstation_live_dhan_plan(dataset_id: str, column: str = ""):
    try:
        return dhan_live_verification.plan(dataset_id,column or None)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/dhan-live/previous")
def workstation_live_dhan_previous(dataset_id: str):
    try:
        return dhan_live_verification.previous(dataset_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/dhan-live/probe")
def workstation_live_dhan_probe(body: LiveDhanProbeRequest):
    if not body.confirm:
        raise HTTPException(400,"Explicit permission is required for a live Dhan history probe")
    try:
        plan=dhan_live_verification.plan(body.dataset_id,body.column)
        if not plan.get("available"):
            raise ValueError(plan.get("reason","Live probe cannot be prepared"))
        return _spawn("dhan_readonly_probe",dhan_live_verification.probe,
                      body.dataset_id,body.column,confirm=True)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/learning/readiness")
def workstation_learning_readiness(dataset_id: str,asset: str):
    try:
        return research_learning.readiness(dataset_id,asset)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/learning/run")
def workstation_learning_run(body: LearningStudyRequest):
    if not body.confirm:
        raise HTTPException(400,"Confirm the chronological CPU research run and assumptions")
    try:
        report=research_learning.readiness(body.dataset_id,body.asset)
        if not report["ready"]:
            raise ValueError("Insufficient observations; inspect minimum and 20% data buffer")
        return _spawn("workspace_learning",research_learning.run,
            body.dataset_id,body.asset,method=body.method,
            train_fraction=body.train_fraction,cost_bps=body.cost_bps,seed=body.seed)
    except Exception as exc:
        bad(exc)


@app.get("/api/dhan/credentials/check")
def dhan_credentials_check():
    """Explicit user-requested, read-only live Dhan profile check.

    Does not expose account information or access-token values.
    """
    LOG.info("Dhan credentials verification requested from local UI")
    result = dhan_auth.check_profile()
    LOG.info("Dhan credentials verification finished: code=%s ok=%s", result.get("code"), result.get("ok"))
    return result


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
        expected = {"SEM_EXM_EXCH_ID", "SEM_SEGMENT", "SEM_SMST_SECURITY_ID",
                    "SEM_INSTRUMENT_NAME", "SEM_TRADING_SYMBOL"}
        if frame.empty or not expected.issubset(
                {str(col).strip().upper() for col in frame.columns}):
            raise ValueError(
                "Downloaded Dhan master is not the compact CSV with exchange "
                "trading symbols. Existing catalog was preserved.")
        destination.replace(path)
        dhan_workspace._catalog_cached.cache_clear()
        health = dhan_workspace.catalog_health()
        if not health["ready"]:
            raise ValueError("Compact Dhan master downloaded, but its NSE ticker "
                             "mapping failed validation: " + health["message"])
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
    selection: Literal["all_nse", "all_bse", "selected", "watchlist", "nifty50_pit", "banknifty_pit"]
    ids: list[str] = Field(default_factory=list, max_length=6000)
    tickers: list[str] = Field(default_factory=list, max_length=6000)
    from_date: str
    to_date: str
    interval: Literal[1, 5, 15, 25, 60] | None = None
    acknowledged_bulk: bool = False
    acknowledged_gaps: bool = False
    include_index_spot: bool = True


BATCH_CANCEL_EVENTS: dict[str, Event] = {}


@app.get("/api/dhan/catalog/health")
def dhan_catalog_health():
    return dhan_workspace.catalog_health()


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


@app.get("/api/indices/status")
def index_history_status():
    try:
        return pit_index.status()
    except Exception as exc:
        bad(exc)


@app.post("/api/indices/sync")
def sync_index_history():
    return _spawn("index_membership_sync", pit_index.sync)


@app.get("/api/indices/preview")
def preview_historical_index(index_id: Literal["nifty50_pit", "banknifty_pit"],
                             from_date: str, to_date: str, as_of_date: str | None = None):
    try:
        try:
            master = dhan_workspace.catalog()
        except FileNotFoundError:
            master = []
        preview = pit_index.query(index_id, from_date, to_date, master, as_of=as_of_date)
        return {k: value for k, value in preview.items() if k != "raw_intervals"}
    except Exception as exc:
        bad(exc)


@app.get("/api/dhan/batches")
def dhan_batches():
    return {"batches": dhan_workspace.list_batches()}


@app.get("/api/dhan/batches/trash")
def dhan_trashed_batches():
    return {"batches": dhan_workspace.list_trashed_batches()}


def _require_no_active_dhan_jobs():
    with JOBS_LOCK:
        if any(job.get("status") in {"queued", "running"}
               and job.get("kind") in {
                   "dhan_bulk", "dhan_prepare_batch", "dhan_index_price_benchmark"
               } for job in JOBS.values()):
            raise HTTPException(409, "A Dhan download/preparation is active. Stop it and "
                                "let it finish before deleting a batch.")


@app.delete("/api/dhan/batches/trash/{batch_id}")
def dhan_purge_batch(batch_id: str, confirm: bool = False):
    if not confirm:
        raise HTTPException(400, "Permanent deletion requires confirmation")
    _require_no_active_dhan_jobs()
    try:
        return dhan_workspace.purge_trashed_batch(batch_id)
    except (ValueError, OSError) as exc:
        bad(exc)


@app.post("/api/dhan/batches/trash/{batch_id}/restore")
def dhan_restore_batch(batch_id: str):
    _require_no_active_dhan_jobs()
    try:
        return dhan_workspace.restore_trashed_batch(batch_id)
    except (ValueError, OSError) as exc:
        bad(exc)


@app.delete("/api/dhan/batches/{batch_id}")
def dhan_trash_batch(batch_id: str, confirm: bool = False):
    if not confirm:
        raise HTTPException(400, "Deleting a download requires confirmation")
    _require_no_active_dhan_jobs()
    try:
        return dhan_workspace.trash_batch(batch_id)
    except (ValueError, OSError) as exc:
        bad(exc)


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
    if not state["counts"]["complete"] + state["counts"]["cached"]:
        raise HTTPException(400, "No successfully downloaded candles")
    return _spawn("dhan_prepare_batch", dhan_workspace.prepare_batch, batch_id)


@app.post("/api/dhan/batches/{batch_id}/prepare-price-benchmark")
def prepare_dhan_index_price_benchmark(batch_id: str):
    try:
        state = dhan_workspace.batch_details(batch_id)
    except Exception as exc:
        bad(exc)
    if not state.get("prepared_dataset_id"):
        raise HTTPException(400, "Prepare the stock research dataset before its price benchmark")
    return _spawn("dhan_index_price_benchmark", dhan_benchmark.prepare_price_benchmark, batch_id)


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


# ---------- Source-exact explainability, index methodology and publication ----------
class StudioRunSubmission(BaseModel):
    model_config=ConfigDict(extra="forbid")
    experiment: RunRequest
    confirm: bool = False


class ResearchHypothesisRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    question: str = Field(min_length=12,max_length=360)
    rationale: str = Field(min_length=12,max_length=2500)
    planned_dataset_id: str = Field(min_length=1,max_length=80)
    primary_metric: str = Field(min_length=2,max_length=100)
    success_criterion: str = Field(min_length=4,max_length=500)
    design: str = Field(min_length=20,max_length=4000)


@app.get("/api/workspace/passports/{dataset_id}")
def research_data_passport(dataset_id: str):
    try:
        return research_next.passport(dataset_id)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/source-coverage/{dataset_id}")
def research_source_coverage(dataset_id: str,
                             validation_start: str | None = None,
                             final_test_start: str | None = None):
    """Read-only empirical source gaps; source truth is NEVER auto-certified."""
    try:
        from index_research.evidence_coverage import inspect_empirical_coverage
        folder, _ = service.dataset_path(dataset_id)
        selected = {
            "validation_start":validation_start,
            "final_test_start":final_test_start,
        }
        report=inspect_empirical_coverage(folder,selected)
        missing=report.pop("missing_security_observation_rows",[])
        report["missing_security_observations_total"]=len(missing)
        report["first_missing_security_observations"]=missing[:80]
        report["missing_observation_list_truncated"]=len(missing)>80
        return report
    except Exception as exc:
        bad(exc)



class PairedResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_id: str = Field(min_length=1, max_length=80)
    challenger_ids: list[str] = Field(min_length=1, max_length=7)


class ResearchAssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=400)
    level: Literal["beginner", "researcher", "mathematical"] = "beginner"


@app.get("/api/workspace/evidence-bundles/{kind}/{run_id}.zip")
def export_archived_reproducible_evidence(
        kind: Literal["model_run", "research_run"], run_id: str):
    """Export only saved results and derived evidence, not original licensed candles."""
    try:
        path = evidence_bundle.bundle_path(kind, run_id)
        return FileResponse(path, media_type="application/zip",
                            filename="quantlab_"+kind+"_"+run_id+"_evidence.zip")
    except (ValueError, OSError, FileNotFoundError, KeyError) as exc:
        bad(exc)


@app.get("/api/workspace/results/{kind}/{run_id}/evidence")
def research_saved_result_evidence(kind: Literal["model_run", "research_run"], run_id: str):
    """No broker calls: reproducible diagnostics of already saved local artifacts."""
    try:
        return result_evidence.summarize(kind, run_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/results/{kind}/{run_id}/ask")
def ask_research_assistant(kind: Literal["model_run", "research_run"],
                           run_id: str, body: ResearchAssistantRequest):
    """Offline answers from one archived run; never request broker data or place orders."""
    try:
        return research_assistant.answer(kind, run_id, body.question, body.level)
    except (ValueError, FileNotFoundError, KeyError, OSError) as exc:
        bad(exc)


class SelectionAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_ids: list[str] = Field(min_length=2,max_length=8)
    folds: Literal[4,6,8] = 4
    declared_trials: int | None = Field(default=None,ge=2,le=10000)
    benchmark_trail: Literal[3,6,12] = 6


@app.post("/api/workspace/results/selection-audit")
def research_model_selection_audit(body: SelectionAuditRequest):
    """Conservative retrospective CSCV/PBO, deflated Sharpe and regime audit."""
    try:
        return selection_diagnostics.audit(
            body.run_ids, folds=body.folds, declared_trials=body.declared_trials,
            benchmark_trail=body.benchmark_trail)
    except (ValueError, OSError, FileNotFoundError, KeyError, TypeError) as exc:
        bad(exc)


@app.post("/api/workspace/results/paired-comparison")
def research_paired_results_comparison(body: PairedResultsRequest):
    """Same dataset/hash, common calendar and benchmark; explicit Holm adjustment."""
    try:
        return result_evidence.paired_comparison(body.baseline_id, body.challenger_ids)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/explain/{kind}/{run_id}")
def explain_archived_research(kind:Literal["model_run","research_run"],
                             run_id:str,level:Literal["beginner","researcher","mathematical"]="researcher"):
    try:
        return research_next.explain_saved(kind,run_id,level)
    except Exception as exc:
        bad(exc)



class FrozenStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool = False


@app.get("/api/workspace/historical-readiness/{dataset_id}")
def inspect_historical_readiness(dataset_id: str,
                                 validation_start: str | None = None,
                                 final_test_start: str | None = None,
                                 factors: str = ""):
    """Structural source cross-check, NOT market or independent auditor approval."""
    try:
        selected = [f.strip() for f in factors.split(",") if f.strip()]
        if len(selected) > 6:
            raise ValueError("Too many requested factors")
        return historical_readiness.inspect(dataset_id,
            validation_start=validation_start, final_test_start=final_test_start,
            selected_factors=selected)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/frozen/create")
def create_frozen_study_protocol(body: RunRequest):
    """Pin a software-only single-use historical dataset, configuration and split."""
    try:
        return frozen_study.create(body.dataset_id,
                                  body.model_dump(exclude={"dataset_id"}))
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/frozen/{protocol_id}")
def inspect_frozen_study_protocol(protocol_id: str):
    try:
        return frozen_study.read(protocol_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/frozen/{protocol_id}/execute")
def execute_single_use_frozen_study(protocol_id: str, body: FrozenStartRequest):
    if not body.confirm:
        raise HTTPException(400, "Explicit confirmation required before consuming the frozen test")
    try:
        frozen_study.read(protocol_id)
        return _spawn("frozen_evaluation", frozen_study.execute, protocol_id)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/frozen/runs/{run_id}/receipt")
def frozen_study_run_receipt(run_id: str):
    try:
        return frozen_study.run_receipt(run_id)
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/index-studio/preflight")
def index_methodology_preflight(body: RunRequest):
    try:
        return research_next.index_preflight(body.dataset_id,body.model_dump())
    except Exception as exc:
        bad(exc)


@app.post("/api/workspace/index-studio/run")
def execute_index_methodology(body: StudioRunSubmission):
    if not body.confirm:
        raise HTTPException(400,"Explicit consent required before running index research")
    try:
        config=body.experiment
        preflight=research_next.index_preflight(config.dataset_id,config.model_dump())
        if preflight["blockers"]:
            raise ValueError("Index methodology blocked: "+"; ".join(preflight["blockers"]))
        return _spawn("workspace_index_studio",service.execute_run,
                      config.dataset_id,config.model_dump())
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/index-studio/decisions/{run_id}")
def explain_index_constituents(run_id:str,decision_date:str|None=None,
                               ticker:str|None=None):
    try:
        return research_next.index_decisions(run_id,decision_date,ticker)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/active-risk/{run_id}")
def index_factor_active_risk(run_id:str,as_of:str|None=None,lookback:int=36):
    try:
        return active_risk_lab.attribution(run_id,as_of,lookback)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/methodology/{run_id}")
def index_paper_methodology(run_id:str):
    try:
        return research_publication.methodology(run_id)
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/publications/{run_id}.zip")
def index_paper_download(run_id:str):
    try:
        source=research_publication.bundle_path(run_id)
        return FileResponse(source,filename="quantlab_"+run_id+"_research.zip",
                            media_type="application/zip")
    except Exception as exc:
        bad(exc)


@app.get("/api/workspace/hypotheses")
def research_preregistrations():
    return {"hypotheses":research_publication.list_hypotheses()}


@app.post("/api/workspace/hypotheses")
def register_research_hypothesis(body:ResearchHypothesisRequest):
    try:
        return research_publication.preregister(body.question,body.rationale,
            body.planned_dataset_id,body.primary_metric,body.success_criterion,body.design)
    except Exception as exc:
        bad(exc)
