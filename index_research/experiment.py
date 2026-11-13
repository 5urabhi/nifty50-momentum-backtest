"""Reproducible research experiment with explicit data provenance and holdout."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from .data import load_research_inputs
from .factors import composite_scores, information_coefficient
from .index import construct_weights, backtest_index, IndexBacktest
from .sector_data import read_sector_history, asof_sectors, sector_exposure, concentration_metrics
from .research_analytics import rolling_relative_metrics, cost_sensitivity


@dataclass(frozen=True)
class ExperimentConfig:
    name: str = "momentum_research"
    factor_weights: dict[str, float] | None = None
    top_n: int = 10
    weighting: str = "equal"
    max_weight: float = 0.20
    rebalance_every: int = 3
    cost_bps: float = 10.0
    execution_lag: int = 1
    momentum_formation: int = 12
    momentum_skip: int = 1
    volatility_lookback: int = 12
    validation_start: str | None = None
    final_test_start: str | None = None
    dataset_status: str = "unverified"
    benchmark_name: str = "user_supplied"
    source_note: str = "No source note provided"
    sector_cap: float | None = None
    optimizer_risk_aversion: float = 3.
    optimizer_turnover_penalty: float = .02
    optimizer_tracking_error_limit: float | None = None
    optimizer_max_trade_weight: float | None = None
    liquidity_aum: float | None = None
    liquidity_max_participation: float = .05
    liquidity_execution_days: int = 3
    liquidity_impact_coefficient_bps: float = 50.

    def __post_init__(self):
        if self.dataset_status not in {"verified_point_in_time", "static_universe_demo", "unverified"}:
            raise ValueError("dataset_status must be explicit")
        if self.execution_lag not in (0,1):
            raise ValueError("execution_lag must be 0 or 1")
        if self.sector_cap is not None and not 0 < self.sector_cap <= 1:
            raise ValueError("sector cap must be in (0,1]")
        if self.top_n < 1 or self.rebalance_every < 1 or not 0 < self.max_weight <= 1:
            raise ValueError("invalid index configuration")
        if self.weighting not in {"equal","score","inverse_volatility",
                                 "minimum_variance","risk_parity","benchmark_relative"}:
            raise ValueError("Unsupported index weighting methodology")
        if not np.isfinite(self.optimizer_risk_aversion) or self.optimizer_risk_aversion<0:
            raise ValueError("Risk aversion must be finite and nonnegative")
        if not np.isfinite(self.optimizer_turnover_penalty) or self.optimizer_turnover_penalty<0:
            raise ValueError("Optimizer turnover penalty must be finite and nonnegative")
        if (self.optimizer_tracking_error_limit is not None and
            not 0<self.optimizer_tracking_error_limit<=5):
            raise ValueError("Tracking error cap must be positive")
        if (self.optimizer_max_trade_weight is not None and
            not 0<self.optimizer_max_trade_weight<=1):
            raise ValueError("Maximum trade weight must be positive")
        if self.liquidity_aum is not None and (
            not np.isfinite(self.liquidity_aum) or self.liquidity_aum<=0):
            raise ValueError("Liquidity AUM must be finite, positive and in ADV's currency")
        if (not 0<self.liquidity_max_participation<=1 or
            not 1<=self.liquidity_execution_days<=30 or
            not np.isfinite(self.liquidity_impact_coefficient_bps) or
            self.liquidity_impact_coefficient_bps<0):
            raise ValueError("Liquidity scenario parameters must be valid")


def performance_metrics(returns: pd.Series, benchmark: pd.Series,
                        turnover: pd.Series, periods_per_year: int = 12) -> dict:
    a = pd.concat([returns.rename("r"),benchmark.rename("b"),
                   turnover.rename("turn")],axis=1).dropna()
    if len(a) < 12:
        return {"observations":int(len(a)), "status":"insufficient_history"}
    r,b = a["r"],a["b"]
    if (r <= -1).any() or (b <= -1).any():
        return {"observations":len(a),"status":"invalid_bankruptcy_return"}
    years = len(r) / periods_per_year
    value = (1+r).cumprod()
    bvalue = (1+b).cumprod()
    excess = r-b
    te=excess.std(ddof=1)*np.sqrt(periods_per_year)
    vol=r.std(ddof=1)*np.sqrt(periods_per_year)
    bvol=b.std(ddof=1)*np.sqrt(periods_per_year)
    return {
        "observations":int(len(r)), "status":"descriptive_not_verified",
        "strategy_cagr":float(value.iloc[-1]**(1/years)-1),
        "benchmark_cagr":float(bvalue.iloc[-1]**(1/years)-1),
        "strategy_volatility":float(vol),
        "benchmark_volatility":float(bvol),
        "tracking_error":float(te),
        "annualized_arithmetic_active_return":float(excess.mean()*periods_per_year),
        "information_ratio":float(excess.mean()*periods_per_year/te) if te>1e-12 else None,
        "max_drawdown":float((value/value.cummax()-1).min()),
        "annualized_turnover":float(a["turn"].sum()/years),
        "positive_month_ratio":float((r>0).mean()),
    }


def _split_mask(dates: pd.DatetimeIndex, cfg: ExperimentConfig) -> dict[str,pd.Series]:
    validation = pd.Timestamp(cfg.validation_start) if cfg.validation_start else None
    test = pd.Timestamp(cfg.final_test_start) if cfg.final_test_start else None
    if validation is not None and test is not None and validation >= test:
        raise ValueError("validation_start must precede final_test_start")
    masks={}
    if validation is None:
        masks["full_history"] = pd.Series(True,index=dates)
    else:
        masks["development"] = pd.Series(dates<validation,index=dates)
        if test is None:
            masks["validation"] = pd.Series(dates>=validation,index=dates)
        else:
            masks["validation"] = pd.Series((dates>=validation)&(dates<test),index=dates)
            masks["final_test"] = pd.Series(dates>=test,index=dates)
    return masks


def run_experiment(prices: pd.DataFrame, membership: pd.DataFrame,
                   benchmark: pd.Series, fundamentals: pd.DataFrame | None,
                   config: ExperimentConfig,
                   sectors: pd.DataFrame | None = None,
                   benchmark_history: pd.DataFrame | None = None,
                   liquidity_records: pd.DataFrame | None = None) -> tuple[IndexBacktest, pd.DataFrame, dict]:
    factors = config.factor_weights or {"momentum":1.0}
    if factors.get("yield",0)>0 and (
        fundamentals is None or "yield" not in fundamentals.columns or
        int(fundamentals["yield"].notna().sum())<2):
        raise ValueError("Yield factor requires >=2 genuine publication-dated dividend yield observations")
    scores = composite_scores(
        prices, membership, factors, fundamentals,
        momentum_formation=config.momentum_formation,
        momentum_skip=config.momentum_skip,
        volatility_lookback=config.volatility_lookback,
    )
    targets = construct_weights(scores,membership,top_n=config.top_n,
        weighting=config.weighting,cap=config.max_weight,
        rebalance_every=config.rebalance_every,prices=prices,
        vol_lookback=config.volatility_lookback,
        sectors=sectors,sector_cap=config.sector_cap,
        benchmark_history=benchmark_history,
        optimizer_risk_aversion=config.optimizer_risk_aversion,
        optimizer_turnover_penalty=config.optimizer_turnover_penalty,
        optimizer_tracking_error_limit=config.optimizer_tracking_error_limit,
        optimizer_max_trade_weight=config.optimizer_max_trade_weight)
    result = backtest_index(prices, targets, benchmark,
                            cost_bps=config.cost_bps,execution_lag=config.execution_lag)
    liquidity_details=None
    if config.liquidity_aum is not None:
        if liquidity_records is None:
            raise ValueError("Capacity scenario requires source liquidity.csv; no volume is fabricated")
        from .liquidity import capacity_overlay
        result,liquidity_details=capacity_overlay(
            result,prices.index,liquidity_records,capital=config.liquidity_aum,
            max_participation=config.liquidity_max_participation,
            execution_days=config.liquidity_execution_days,
            impact_coefficient_bps=config.liquidity_impact_coefficient_bps)
    ic = information_coefficient(scores, prices, membership)
    parts={}
    for name,mask in _split_mask(result.returns.index,config).items():
        periods=result.returns.index[mask.to_numpy()]
        parts[name]=performance_metrics(result.returns.loc[periods],
            result.benchmark_returns.loc[periods],result.turnover.loc[periods])
    concentration=concentration_metrics(result.weights)
    meta={"config":asdict(config),"factor_weights_used":factors,
          "metrics_by_split":parts,
          "first_price_date":str(prices.index.min().date()),
          "last_price_date":str(prices.index.max().date()),
          "observations":int(len(prices)),
          "coverage":{
              "membership_rows":int(membership.shape[0]),
              "eligible_fraction":float(membership.to_numpy().mean()),
              "scored_fraction":float(scores.notna().to_numpy().mean()),
              "rank_ic_mean_descriptive":float(ic.mean()) if ic.notna().any() else None,
              "mean_hhi":float(concentration["hhi"].mean()),
              "mean_effective_names":float(concentration["effective_names"].mean()) if concentration["effective_names"].notna().any() else None,
              "historical_sector_classification":sectors is not None,
          },
          "limitations":[
              "Dataset status is a user declaration, not independently audited.",
              "Returns and benchmark must be compatible adjusted total returns.",
              "Monthly execution, transaction costs and cash handling are approximations.",
              "Factor score definitions are transparent research approximations, not MSCI methodologies.",
              "No historical result is independently validated by this program."
          ]}
    if liquidity_details is not None:
        meta["liquidity_costs_by_period"]=liquidity_details.to_dict(orient="records")
        meta["liquidity_disclosure"]=(
            "Dated source ADV/spreads and square-root impact scenario; fixed base cost "
            "must exclude spread to prevent double charging. Not realized fills or market capacity certification.")
    return result,scores,meta


def sha256_file(path: Path) -> str:
    checksum=hashlib.sha256()
    with path.open("rb") as handle:
        while chunk:=handle.read(1024*1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def save_experiment(result: IndexBacktest, scores: pd.DataFrame,
                    meta: dict, output_dir: str | Path, input_dir: str | Path | None = None,
                    sectors: pd.DataFrame | None = None) -> Path:
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    frame=pd.DataFrame({
        "strategy_net":result.returns,
        "strategy_gross":result.gross_returns,
        "benchmark":result.benchmark_returns,
        "turnover":result.turnover,
        "transaction_cost_fraction":result.costs,
    })
    frame.to_csv(out/"monthly_results.csv",index_label="date",float_format="%.12g")
    if "liquidity_costs_by_period" in meta:
        pd.DataFrame(meta["liquidity_costs_by_period"]).to_csv(
            out/"liquidity_capacity.csv",index=False)
    result.weights.to_csv(out/"post_rebalance_weights.csv",index_label="date")
    result.pre_trade_weights.to_csv(out/"pre_trade_weights.csv",index_label="date")
    scores.to_csv(out/"factor_scores.csv",index_label="decision_date")
    concentration_metrics(result.weights).to_csv(out/"concentration.csv",index_label="date")
    rolling_relative_metrics(result.returns,result.benchmark_returns).to_csv(out/"rolling_metrics.csv",index_label="date")
    try:
        cost_sensitivity(result.gross_returns,result.turnover).to_csv(out/"cost_sensitivity.csv",index=False)
    except ValueError:
        # Short experimental samples are allowed; detailed cost reporting awaits history.
        pass
    if sectors is not None:
        aligned=sectors.reindex(index=result.weights.index,columns=result.weights.columns)
        sector_exposure(result.weights,aligned).to_csv(out/"sector_exposure.csv",index_label="date")
    hashes={}
    if input_dir is not None:
        for file in sorted(Path(input_dir).glob("*.csv")):
            hashes[file.name]=sha256_file(file)
    meta={**meta,"input_sha256":hashes,
          "generated_utc":datetime.now(timezone.utc).isoformat()}
    with (out/"research_manifest.json").open("w") as f:
        json.dump(meta,f,indent=2,allow_nan=False)
    return out


def run_from_directory(input_dir: str | Path, output_dir: str | Path,
                       config: ExperimentConfig) -> tuple[IndexBacktest,dict]:
    prices, membership, benchmark, fundamentals = load_research_inputs(input_dir)
    if config.dataset_status == "verified_point_in_time":
        from .empirical_validation import evidence_gate
        declaration=Path(input_dir)/"EVIDENCE_REVIEW.json"
        assessment=evidence_gate(input_dir,declaration)
        if assessment["status"]=="BLOCKED":
            raise ValueError("verified_point_in_time requires complete explicit "
                "source declarations and input evidence. See EVIDENCE_REVIEW.json; "
                "file presence alone cannot establish an external audit.")
    sectors=None
    sectors_file=Path(input_dir)/"sectors.csv"
    if sectors_file.exists():
        sectors=asof_sectors(read_sector_history(str(sectors_file)),prices.index,prices.columns)
    benchmark_history=None
    if config.weighting=="benchmark_relative":
        from .institutional_index import read_benchmark_history
        benchmark_history=read_benchmark_history(Path(input_dir)/"benchmark_weights.csv")
    liquidity_records=None
    if config.liquidity_aum is not None:
        from .liquidity import read_liquidity
        liquidity_records=read_liquidity(Path(input_dir)/"liquidity.csv")
    result,scores,meta=run_experiment(prices,membership,benchmark,fundamentals,config,
                                     sectors=sectors,benchmark_history=benchmark_history,
                                     liquidity_records=liquidity_records)
    out=save_experiment(result,scores,meta,output_dir,input_dir,sectors=sectors)
    from .diagnostics import evaluate_factor_panel, exposure_panel, data_quality_report
    from .comparison import compare_index_methods
    from .data_audit import audit_dataset
    from .robustness import sensitivity_grid
    factor_ic, factor_scores=evaluate_factor_panel(
        prices,membership,fundamentals,
        momentum_formation=config.momentum_formation,
        momentum_skip=config.momentum_skip,
        volatility_lookback=config.volatility_lookback)
    holding_exposures,_=exposure_panel(result.weights,factor_scores,sectors=sectors)
    factor_ic.to_csv(out/"factor_rank_ic.csv",index_label="date")
    holding_exposures.to_csv(out/"portfolio_factor_exposures.csv",index_label="date")
    quality=data_quality_report(prices,membership,fundamentals,sectors)
    (out/"data_quality.json").write_text(json.dumps(quality,indent=2,allow_nan=False))
    audit=audit_dataset(input_dir)
    (out/"dataset_audit.json").write_text(json.dumps(audit,indent=2,allow_nan=False))
    try:
        grid=sensitivity_grid(prices,membership,benchmark,fundamentals,config,
            sectors=sectors,benchmark_history=benchmark_history,
            liquidity_records=liquidity_records,
            segment="validation" if config.validation_start else "full_history")
        grid.to_csv(out/"robustness_grid.csv",index=False)
    except (ValueError,RuntimeError) as exc:
        (out/"robustness_unavailable.txt").write_text(str(exc))
    try:
        variant_returns,variant_summary=compare_index_methods(
            prices,membership,benchmark,fundamentals,config,sectors=sectors,
            benchmark_history=benchmark_history,liquidity_records=liquidity_records)
        variant_returns.to_csv(out/"methodology_returns.csv",index_label="date")
        variant_summary.to_csv(out/"methodology_summary.csv",index_label="methodology")
    except (ValueError,RuntimeError) as exc:
        (out/"methodology_comparison_unavailable.txt").write_text(str(exc))
    return result,meta
