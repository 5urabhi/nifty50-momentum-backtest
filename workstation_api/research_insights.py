"""QuantLab comparison and empirical validation without simulated market evidence.

Model overlays require compatible axes. Walk-forward and holdout statistics
use strictly later observations than calibration, not in-sample fit scores.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import json

import numpy as np
import pandas as pd

from index_research import math_models, portfolio_math
from index_research.data import read_matrix
from . import model_lab, model_registry, research_library, service

MAX_COMPARISON = 8
MAX_SWEEP = 16
ALLOCATION = frozenset({"equal", "inverse_volatility", "min_variance",
                        "risk_parity", "max_diversification"})


def _source_ref(kind, run_id, plot_index=0) -> dict:
    if kind == "model_run":
        result = model_lab.read_saved_model(run_id)
        plots = result.get("plots", [])
        if not 0 <= plot_index < len(plots):
            raise ValueError("Saved model run has no plot at this index")
        return {"plot": plots[plot_index], "title": result["title"],
                "mode": result["mode"], "source": result.get("source"),
                "run_id": run_id, "kind": kind,
                "metrics": result.get("metrics", []),
                "source_sha256": result.get("source_sha256")}
    if kind == "research_run":
        result = service.run_details(run_id)
        rows = result.get("returns", [])
        if not rows:
            raise ValueError("Saved index experiment has no return series")
        values = []
        for row in rows:
            date = str(row.get("date", ""))
            value = row.get("strategy_net")
            if not date or not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            values.append((date, float(value)))
        if len(values) < 2:
            raise ValueError("Insufficient saved index returns")
        level = 100.0
        path = []
        for _, value in values:
            if value <= -1:
                raise ValueError("Saved index return cannot be below -100%")
            level *= 1 + value
            path.append(level)
        name = result["meta"].get("config", {}).get("name", run_id)
        return {"plot": model_lab.xy(name + " · net wealth", [x for x, _ in values],
                         [{"name": "Net strategy (base 100)", "y": path}],
                         "Trading month", "Wealth index (base 100)"),
                "title": name, "mode": "historical",
                "source": result.get("source", {}), "run_id": run_id,
                "kind": kind, "metrics": [], "source_sha256": None}
    raise ValueError("Unsupported comparison source")


def compare(selections: list[dict], *, normalize: str = "none",
            alignment: str = "intersection", title: str = "Saved model comparison") -> dict:
    if not isinstance(selections, list) or not 2 <= len(selections) <= MAX_COMPARISON:
        raise ValueError("Compare between two and eight saved results")
    if normalize not in {"none", "base100", "zscore"}:
        raise ValueError("Unsupported normalization")
    if alignment not in {"intersection", "union"}:
        raise ValueError("Unsupported axis alignment")
    sources = []
    for item in selections:
        if not isinstance(item, dict):
            raise ValueError("Invalid comparison selection")
        sources.append(_source_ref(str(item.get("kind", "model_run")),
                                   str(item.get("run_id", "")),
                                   int(item.get("plot_index", 0))))
    plots = [a["plot"] for a in sources]
    modes = {a["mode"] for a in sources}
    if len(modes) != 1:
        raise ValueError("Do not overlay theoretical, synthetic and observed-market results")
    x_labels = {p.get("x_label") for p in plots}
    y_labels = {p.get("y_label") for p in plots}
    kinds = {p.get("kind") for p in plots}
    if len(x_labels) != 1 or (len(y_labels) != 1 and normalize == "none"):
        raise ValueError("Incompatible axes. Select compatible plots or explicitly standardize the Y values.")
    if not kinds.issubset({"line2d", "fan2d", "bar2d", "histogram2d"}):
        raise ValueError("These saved outputs need split-panel comparison; 3D surfaces cannot be overlaid")
    if any(len(p.get("x", [])) != len(p.get("traces", [{}])[0].get("y", []))
           for p in plots):
        raise ValueError("Saved chart has inconsistent X/Y dimensions")
    def key(x):
        return str(x) if isinstance(x, str) else float(x)
    xs = [set(key(x) for x in plot.get("x", [])) for plot in plots]
    shared = set.intersection(*xs) if alignment == "intersection" else set.union(*xs)
    if len(shared) < 2:
        raise ValueError("Model results have fewer than two matching X observations")
    if len(shared) > 600:
        raise ValueError("Comparison has more than 600 points; narrow the selected range")
    try:
        ordered = sorted(shared)
    except TypeError as exc:
        raise ValueError("Cannot align different X-axis types") from exc
    traces = []
    for source, plot in zip(sources, plots):
        names = {key(x): i for i, x in enumerate(plot["x"])}
        for trace in plot.get("traces", []):
            values = []
            for x in ordered:
                i = names.get(x)
                value = trace["y"][i] if i is not None else None
                values.append(float(value) if value is not None and math.isfinite(value) else None)
            valid = [v for v in values if v is not None]
            if not valid:
                continue
            if normalize == "base100":
                if valid[0] <= 0:
                    raise ValueError("Base-100 normalization requires a positive initial value")
                values = [100*v/valid[0] if v is not None else None for v in values]
            elif normalize == "zscore":
                sd = float(np.std(valid, ddof=1)) if len(valid)>1 else 0
                if sd <= 0:
                    raise ValueError("Standardization requires varying observations")
                mean = float(np.mean(valid))
                values = [(v-mean)/sd if v is not None else None for v in values]
            traces.append({"name": source["title"] + " · " + trace["name"], "y": values})
    if len(traces) > 24:
        raise ValueError("Overlay exceeds 24 curves; select fewer traces or split the models")
    y_label = plots[0].get("y_label", "") if normalize == "none" else (
        "Index (base 100)" if normalize == "base100" else "Standardized z-score")
    kind = "bar2d" if kinds == {"bar2d"} and normalize == "none" else "line2d"
    return {"title": title, "plot": model_lab.xy(title, ordered, traces,
            plots[0].get("x_label") or "Observation", y_label, kind=kind),
            "sources": [{k: a.get(k) for k in ("kind","run_id","title","mode","source_sha256")}
                        for a in sources], "alignment": alignment, "normalization": normalize,
            "warning": "Comparison overlays compatible saved outputs only. Aligned X samples "
                       "are not necessarily independent holdouts or investable backtests."}


def inspect_quality(dataset_id: str, *, max_assets: int = 60) -> dict:
    folder, record = service.dataset_path(dataset_id)
    file_name = "daily_prices.csv" if record.get("has_daily_prices") else "prices.csv"
    if not record.get("has_prices"):
        return {"dataset_id": dataset_id, "ready": False,
                "message": "Dataset has no price observations", "assets": []}
    file = folder / file_name
    raw = pd.read_csv(file)
    if "date" not in raw.columns:
        raise ValueError("Dataset price CSV lacks date column")
    raw_dates = pd.to_datetime(raw["date"], errors="coerce")
    duplicates = int(raw_dates.duplicated().sum())
    invalid_dates = int(raw_dates.isna().sum())
    columns = [name for name in raw if name != "date"]
    if len(columns) > 10000:
        raise ValueError("Unbounded data-quality matrix")
    inspected = []
    for col in columns[:max_assets]:
        series = pd.to_numeric(raw[col], errors="coerce")
        clean = series.dropna()
        returns = clean.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
        gaps = int(series.isna().sum())
        nonpositive = int((clean <= 0).sum())
        finite_returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
        extreme = int((finite_returns.abs() > .40).sum())
        stalled = bool(len(clean) >= 10 and clean.iloc[-10:].nunique() == 1)
        inspected.append({"symbol": col, "prices": len(clean),
                          "missing_prices": gaps, "invalid_prices": nonpositive,
                          "returns_gt_40pct": extreme, "last_10_constant": stalled})
    return {"dataset_id": dataset_id, "label": record["label"], "source_file": file_name,
            "price_dates": len(raw), "asset_count": len(columns),
            "assessed_assets": len(inspected), "duplicate_dates": duplicates,
            "invalid_dates": invalid_dates, "assets": inspected,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            "warning": "Large daily moves may be genuine or unadjusted corporate actions. "
                       "A structural data audit is not an independent total-return certification."}


def _selected_returns(dataset_id: str, assets: int, minimum: int) -> tuple[pd.DataFrame, dict]:
    if not 2 <= assets <= 18:
        raise ValueError("Select 2-18 assets")
    return model_lab._historical_input(dataset_id, minimum, assets)


def _weights(method: str, train: pd.DataFrame, cap: float, annual: int) -> pd.Series:
    if method not in ALLOCATION:
        raise ValueError("Unsupported portfolio allocation model")
    n = train.shape[1]
    if not 1/n <= cap <= 1:
        raise ValueError("Max weight makes portfolio infeasible")
    if method == "equal":
        return pd.Series(1/n, index=train.columns)
    if method == "inverse_volatility":
        vol = train.std(ddof=1)
        if (vol <= 1e-10).any():
            raise ValueError("Constant asset volatility")
        weights = 1/vol
        weights /= weights.sum()
        if weights.max() > cap + 1e-10:
            raise ValueError("Inverse-volatility weights violate cap; raise cap or change model")
        return weights
    cov = math_models.shrinkage_covariance(train, .25, annual)
    if method == "min_variance":
        return math_models.minimum_variance(cov, max_weight=cap).weights
    if method == "risk_parity":
        return portfolio_math.risk_parity(cov, max_weight=cap)
    return portfolio_math.maximum_diversification(cov, max_weight=cap)


def _metrics(series: pd.Series, annual: int) -> dict:
    values = series.to_numpy(dtype=float)
    if len(values) < 2 or not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("Invalid out-of-sample return observations")
    sd = float(np.std(values, ddof=1))
    compounded = np.cumprod(1 + values)
    years = len(values)/annual
    cagr = float(compounded[-1] ** (1/years) - 1) if compounded[-1]>0 else None
    sharpe = float(np.mean(values)/sd*math.sqrt(annual)) if sd>1e-12 else None
    dd = compounded / np.maximum.accumulate(np.r_[1., compounded])[1:] - 1
    losses = -values
    var95 = float(np.quantile(losses,.95))
    tail = losses[losses >= var95]
    return {"observations": len(values), "annualized_return": cagr,
            "annualized_volatility": sd*math.sqrt(annual),
            "sharpe_zero_rf": sharpe, "max_drawdown": float(np.min(dd)),
            "historical_var95_loss": var95, "historical_tail_mean95_loss": float(tail.mean())}


def _bootstrap(values: pd.Series, annual: int, *, seed: int = 2026) -> dict:
    x = values.to_numpy(dtype=float)
    n = len(x)
    if n < 12:
        return {"available": False, "reason": "At least 12 holdout observations needed"}
    block = min(5, max(2, int(math.sqrt(n))))
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(300):
        sample = []
        while len(sample) < n:
            start = int(rng.integers(0, n))
            sample.extend(x[(start + np.arange(block)) % n].tolist())
        means.append(float(np.mean(sample[:n])))
    low, high = np.quantile(means, [.025,.975])
    return {"available": True, "method": "circular moving-block bootstrap",
            "block_size": block, "replications": 300, "seed": seed,
            "mean_return_95ci": [float(low),float(high)],
            "annualized_arithmetic_mean_95ci": [float(low*annual),float(high*annual)],
            "note": "Exploratory dependence-aware CI; model selection and multiple testing "
                    "may invalidate nominal coverage."}


def validate_out_of_sample(dataset_id: str, *, model: str = "min_variance",
                           assets: int = 8, train_window: int = 180,
                           test_step: int = 20, max_weight: float = .3,
                           mode: str = "walk_forward", seed: int = 2026) -> dict:
    if mode not in {"walk_forward", "single_holdout"}:
        raise ValueError("Choose walk-forward or single frozen holdout")
    if not 30 <= train_window <= 1500 or not 1 <= test_step <= 252:
        raise ValueError("Invalid training or testing sample length")
    data, meta = _selected_returns(dataset_id, assets, train_window + max(12,test_step))
    count = len(data)
    if train_window + 12 > count:
        raise ValueError("Insufficient observations for chronological holdout")
    annual = meta["periods_per_year"]
    test_values, benchmark_values, rows, folds = [], [], [], []
    # Training window always ends strictly before the first evaluated return.
    i = train_window
    while i < count:
        end = count if mode == "single_holdout" else min(count, i + test_step)
        training = data.iloc[i-train_window:i]
        testing = data.iloc[i:end]
        if len(training) != train_window or testing.empty:
            break
        weights = _weights(model, training, max_weight, annual)
        test_r = testing.dot(weights)
        eq_r = testing.mean(axis=1)
        folds.append({"train_from": training.index[0].date().isoformat(),
                      "train_to": training.index[-1].date().isoformat(),
                      "test_from": testing.index[0].date().isoformat(),
                      "test_to": testing.index[-1].date().isoformat(),
                      "weights": {k: float(v) for k,v in weights.items()}})
        for stamp, value, bench in zip(testing.index, test_r, eq_r):
            rows.append({"date": stamp.date().isoformat(),
                         "strategy": float(value), "equal_weight": float(bench)})
        test_values.extend(test_r.tolist())
        benchmark_values.extend(eq_r.tolist())
        if mode == "single_holdout":
            break
        i = end
        if len(folds) >= 40:
            break
    if len(rows) < 12:
        raise ValueError("Insufficient post-formation observations for holdout statistics")
    results = pd.Series(test_values, dtype=float)
    benchmark = pd.Series(benchmark_values, dtype=float)
    observed = _metrics(results, annual)
    baseline = _metrics(benchmark, annual)
    portfolio = (100*(1+results).cumprod()).tolist()
    equal = (100*(1+benchmark).cumprod()).tolist()
    plot = model_lab.xy("Strictly later observations · " + model, [r["date"] for r in rows],
                        [{"name": model, "y": portfolio},
                         {"name": "Equal-weight benchmark", "y": equal}],
                        "Observed trading period", "Wealth index (base 100)")
    report = {"mode": mode, "model": model, "source": meta, "train_window": train_window,
              "test_step": test_step, "max_weight": max_weight,
              "folds": folds, "test_observations": len(results),
              "metrics": observed, "baseline_metrics": baseline,
              "uncertainty": _bootstrap(results - benchmark, annual, seed=seed),
              "plot": plot, "rows": rows,
              "warning": "Training and test periods do not overlap; this is descriptive "
                         "historical OOS evaluation, not prospective or investable validation. "
                         "Prices may omit corporate actions, dividends, delistings and costs."}
    record = research_library.create("study", "Validation: " + model + " / " + mode,
                                     {k: report[k] for k in ("model","mode","source",
                                         "train_window","test_step","max_weight",
                                         "metrics","baseline_metrics","uncertainty",
                                         "folds","plot","warning")})
    return {**report, "study_id": record["id"]}


def sweep(model_id: str, dataset_id: str | None, params: dict,
          parameter: str, values: list[float | int], *, metric_label: str = "") -> dict:
    spec = model_registry.CATALOG.get(model_id)
    if spec is None or not isinstance(values, list) or not 2 <= len(values) <= MAX_SWEEP:
        raise ValueError("Choose 2-16 valid parameter values for a registered model")
    spec_param = next((p for p in spec["parameters"] if p["key"] == parameter), None)
    if spec_param is None or spec_param["type"] not in {"number","integer"}:
        raise ValueError("Parameter must be numeric and registered for this model")
    if len({float(v) for v in values if isinstance(v, (float,int)) and not isinstance(v,bool)}) != len(values):
        raise ValueError("Values must be distinct finite numbers")
    results = []
    for value in values:
        current = dict(params or {})
        current[parameter] = value
        validated = model_registry.validate_parameters(model_id, current)
        result = model_lab.run_model(model_id, dataset_id, validated)
        archived = model_lab.save_result(result)
        entries = {x["label"]: x["value"] for x in result["metrics"]
                   if isinstance(x["value"], (int,float)) and math.isfinite(x["value"])}
        results.append({"parameter_value": value, "run_id": archived["run_id"],
                        "metrics": entries})
    candidates = set.intersection(*(set(x["metrics"]) for x in results)) if results else set()
    selected = metric_label or (sorted(candidates)[0] if candidates else "")
    if selected and selected not in candidates:
        raise ValueError("Selected metric unavailable across all parameter values")
    plot = (model_lab.xy("Parameter sensitivity — " + parameter,
            [x["parameter_value"] for x in results],
            [{"name": selected, "y": [x["metrics"][selected] for x in results]}],
            parameter, selected) if selected else None)
    report = {"model_id": model_id, "dataset_id": dataset_id, "parameter": parameter,
              "metric_label": selected, "runs": results, "plot": plot,
              "note": "A parameter sweep evaluates observed in-sample fits or theoretical "
                      "outputs; best-looking variants are not validated on untouched holdouts."}
    record = research_library.create("study", "Parameter sweep: " + spec["title"], report)
    return {**report, "study_id": record["id"]}


def scenario(run_id: str, shocks: dict[str, float]) -> dict:
    run = model_lab.read_saved_model(run_id)
    source = run.get("source")
    if not source or not source.get("assets"):
        raise ValueError("Choose a saved empirical portfolio model with observed assets")
    names = source["assets"]
    if not isinstance(shocks, dict) or not shocks or any(
            key not in names or not isinstance(value, (int,float)) or isinstance(value,bool)
            or not math.isfinite(value) or abs(value) > 1 for key,value in shocks.items()):
        raise ValueError("Shocks must be finite decimal returns between -1 and +1 for selected assets")
    weights = {}
    if run["model_id"] in {"min_variance","risk_parity","max_diversification","cvar"}:
        for plot in run.get("plots", []):
            if plot.get("kind") == "bar2d" and plot.get("x") == names and plot.get("traces"):
                weights = dict(zip(names, plot["traces"][0]["y"]))
                break
    if not weights:
        weights = {name: 1/len(names) for name in names}
        basis = "equal-weight illustrative basket (not saved optimized weights)"
    else:
        basis = "saved portfolio model weights"
    rows = [{"asset": name, "weight": float(weights[name]),
             "hypothetical_return": float(shocks.get(name,0)),
             "contribution": float(weights[name]*shocks.get(name,0))}
            for name in names]
    return {"run_id": run_id, "basis": basis, "rows": rows,
            "portfolio_shock_return": sum(x["contribution"] for x in rows),
            "warning": "Instantaneous first-order spot-price shock only; excludes "
                       "correlation shifts, nonlinear options, slippage and rebalancing."}


def verify_reproducibility(run_id: str, *, recompute: bool = False) -> dict:
    saved = model_lab.read_saved_model(run_id)
    source = saved.get("source")
    current_hash = None
    matches = None
    if source:
        folder, _record = service.dataset_path(source["dataset_id"])
        file = folder / source["source_file"]
        if not file.is_file() or file.is_symlink():
            raise ValueError("Saved source file is no longer available")
        current_hash = hashlib.sha256(file.read_bytes()).hexdigest()
        matches = current_hash == saved.get("source_sha256")
    recomputed = None
    if recompute and matches is not False:
        candidate = model_lab.run_model(saved["model_id"],
                                        source["dataset_id"] if source else None,
                                        saved.get("params", {}))
        # Ignore timestamps, source labels, side effects; compare numerical content.
        expected = json.dumps(saved.get("plots", []), sort_keys=True, allow_nan=False)
        actual = json.dumps(candidate.get("plots", []), sort_keys=True, allow_nan=False)
        recomputed = expected == actual
    return {"run_id": run_id, "source_sha256": saved.get("source_sha256"),
            "current_source_sha256": current_hash, "source_unchanged": matches,
            "recomputed_figure_match": recomputed,
            "reproducible": matches is not False and recomputed is not False,
            "message": ("Source changed since the saved run. Historical results remain frozen."
                        if matches is False else
                        "Source integrity checked. Recompute optionally verifies chart determinism."),
            "warning": "Exact reproduction may depend on Python, SciPy and BLAS versions; "
                       "a matching checksum does not independently certify the data."}
