"""Typed, auditable catalog for the QuantLab research model workbench.

The model catalog is the SINGLE source for labels, input bounds, status and
mathematical assumptions in both the React UI and Python dispatch. A model
not listed here cannot be invoked through the local research API.
"""
from __future__ import annotations
import math
import re


def numeric(name: str, default: float, low: float, high: float, step: float,
            *, integer: bool = False, description: str = "") -> dict:
    return {"key": name, "type": "integer" if integer else "number",
            "default": default, "min": low, "max": high,
            "step": step, "description": description}


def choice(name: str, default: str, options: list[str], description: str = "") -> dict:
    return {"key": name, "type": "select", "default": default,
            "options": options, "description": description}


def symbol_input(name: str, default: str = "", description: str = "") -> dict:
    """Constrained market symbol, never a file path or unchecked expression."""
    return {"key": name, "type": "symbol", "default": default, "description": description}


SEED = numeric("seed", 2026, 0, 2147483647, 1, integer=True)
PATHS = numeric("paths", 180, 20, 600, 20, integer=True)
STEPS = numeric("steps", 100, 12, 260, 10, integer=True)
YEARS = numeric("years", 1.0, 0.05, 5, 0.25)
SPOT = numeric("spot", 100, 1, 100000, 1)
VOL = numeric("volatility", 0.20, 0.01, 3, 0.01)
DRIFT = numeric("drift", 0.07, -1, 1, 0.01)
STRIKE = numeric("strike", 100, 1, 100000, 1)
RATE = numeric("risk_free_rate", 0.05, -0.25, 0.5, 0.005)
OPTION = choice("option_type", "call", ["call", "put"])
CAP = numeric("max_weight", .30, .05, 1, .05)
ASSETS = numeric("assets", 8, 2, 18, 1, integer=True)
CONFIDENCE = numeric("confidence", .95, .8, .995, .005)


def model(key: str, group: str, title: str, mode: str, observations: int,
          description: str, formula: str, parameters: list[dict],
          chart: str, status: str = "runnable") -> dict:
    return dict(id=key, group=group, title=title, mode=mode,
                min_observations=observations, description=description,
                formula=formula, parameters=parameters,
                chart=chart, status=status)


MODELS = [
    model("gbm", "Stochastic Processes", "Geometric Brownian Motion", "synthetic", 0,
          "Seeded lognormal price-path simulation; no calibration or forward forecast.",
          "dS/S = μ dt + σ dW", [SPOT, DRIFT, VOL, YEARS, STEPS, PATHS, SEED], "fan2d"),
    model("gbm_fit", "Stochastic Processes", "GBM · Fit to Historical Data",
          "historical", 10,
          "Estimate GBM drift and volatility from observed NIFTY TRI or one named stock; "
          "reserve the final 20% for chronological holdout diagnostics. "
          "Any forward paths are seeded illustrative scenarios, not predictions.",
          "log(Pₜ/Pₜ₋₁) ~ N((μ-σ²/2)Δt, σ²Δt)",
          [choice("target", "benchmark_tri", ["benchmark_tri", "stock"],
                  "Choose original NIFTY total-return benchmark or one stock symbol."),
           symbol_input("ticker", "",
                        "Required only when target=stock. Choose a symbol from the available dataset list."),
           YEARS, STEPS, PATHS, SEED], "fan2d"),
    model("ou", "Stochastic Processes", "Ornstein–Uhlenbeck Process", "synthetic", 0,
          "Mean-reverting Gaussian process using the exact discrete-time transition.",
          "dX = κ(θ-X)dt + σ dW",
          [numeric("initial", 1, -1000, 1000, .1),
           numeric("mean", 0, -1000, 1000, .1),
           numeric("reversion", 2, .01, 50, .1),
           numeric("diffusion", .3, 0, 10, .05), YEARS, STEPS, PATHS, SEED], "fan2d"),
    model("heston", "Stochastic Processes", "Heston Stochastic Volatility", "synthetic", 0,
          "Correlated price/variance paths using full-truncation Euler; uncalibrated, discretization-sensitive.",
          "dS/S=(r-q)dt+√v dW₁; dv=κ(θ-v)dt+ξ√v dW₂",
          [SPOT, YEARS, STEPS, PATHS,
           numeric("initial_variance", .04, .0001, 2, .01),
           numeric("mean_reversion", 2, .01, 20, .1),
           numeric("long_variance", .04, .0001, 2, .01),
           numeric("vol_of_vol", .4, 0, 3, .05),
           numeric("rho", -.6, -.99, .99, .05), RATE, SEED], "fan2d"),
    model("merton", "Stochastic Processes", "Merton Jump Diffusion", "synthetic", 0,
          "Physical-measure stochastic paths with compensated Poisson lognormal jumps.",
          "dS/S=(μ-λk)dt+σdW+(eʸ-1)dN",
          [SPOT, DRIFT, VOL, YEARS, STEPS, PATHS,
           numeric("jump_intensity", 1, 0, 20, .1),
           numeric("jump_mean_log", -.08, -2, 2, .02),
           numeric("jump_std_log", .15, 0, 2, .02), SEED], "fan2d"),
    model("ou_fit", "Stochastic Processes", "OU · Historical Volatility Fit", "historical", 90,
          "Fit an exact AR(1)/OU mean-reverting process to 20-session log-realized stock volatility; "
          "evaluate on a separate final 20%. An OU process is NOT blindly fitted to trending stock prices.",
          "log RVₜ = a + φ log RVₜ₋₁ + εₜ; κ = −252 log φ",
          [choice("target","stock",["stock"],"Original Dhan daily stock closes only"),
           symbol_input("ticker","", "Select one exact stock symbol"),
           YEARS,STEPS,PATHS,SEED], "line2d"),
    model("merton_fit", "Stochastic Processes", "Merton · Historical Jump Proxy", "historical", 120,
          "Measure robust-threshold tail-event frequency and Gaussian diffusion from historical "
          "log returns; examine untouched 20% and simulate illustrative jump paths. "
          "Threshold events are NOT identified market jumps or risk-neutral option calibration.",
          "r = Gaussian diffusion + compound-Poisson jump proxy",
          [choice("target","stock",["stock","benchmark_tri"],"Original stock or NIFTY TRI"),
           symbol_input("ticker","", "Required for a stock target"),
           YEARS,STEPS,PATHS,SEED], "line2d"),
    model("heston_proxy", "Stochastic Processes",
          "Heston · Historical Variance Proxy (not option calibrated)", "historical", 252,
          "Fit a stationary rolling realized-variance proxy from daily stock closes. "
          "Latent Heston risk-neutral parameters CANNOT be identified from stock closes alone; "
          "use option-chain quotes for genuine option-surface calibration.",
          "ΔRV ≈ κ(θ−RV)dt + ξ√RV dW; RV is an observed proxy, not latent v",
          [choice("target","stock",["stock"],"Original daily stock candles"),
           symbol_input("ticker","", "Select one exact stock symbol"),
           YEARS,STEPS,PATHS,SEED], "line2d"),
    model("garch", "Volatility & Econometrics", "Gaussian GARCH(1,1)", "historical", 60,
          "In-sample conditional variance maximum likelihood on the observed return sample.",
          "hₜ=ω+αε²ₜ₋₁+βhₜ₋₁", [ASSETS], "line2d"),
    model("pca", "Volatility & Econometrics", "Principal Components", "historical", 30,
          "Standardized-return PCA, trained on the entire selected sample; not an out-of-sample forecast.",
          "Z = UΣVᵀ", [ASSETS, numeric("components", 3, 2, 3, 1, integer=True)], "bar2d"),
    model("covariance", "Volatility & Econometrics", "Covariance Estimator Comparison", "historical", 60,
          "Sample, fixed diagonal shrinkage and EWMA covariance from the same observed input.",
          "Σ̂ᴬ = (1-λ)Σ_sample + λ diag(Σ_sample)",
          [ASSETS, numeric("shrinkage", .25, 0, 1, .05),
           numeric("decay", .94, .5, .995, .005)], "bar2d"),
    model("rolling_vol", "Volatility & Econometrics", "Walk-Forward Volatility", "historical", 90,
          "One-step variance forecasts from strictly preceding observations, with a later holdout.",
          "ĥₜ|ₜ₋₁ = f(rₜ₋ₗ,...,rₜ₋₁)",
          [ASSETS, numeric("train_window", 60, 24, 180, 12, integer=True)], "line2d"),
    model("black_scholes", "Derivatives & Options", "Black–Scholes–Merton & Greeks", "theoretical", 0,
          "European option model under constant volatility, continuous dividends, frictionless assumptions.",
          "C = S e⁻ᵠᵀ N(d₁) − K e⁻ʳᵀ N(d₂)",
          [SPOT, STRIKE, YEARS, RATE, VOL, OPTION,
           numeric("dividend_yield", .0, -.2, .4, .01)], "line2d"),
    model("binomial", "Derivatives & Options", "CRR Binomial Pricing", "theoretical", 0,
          "European or American option valuation with a converging binomial tree.",
          "Vₜ = e⁻ʳΔᵗ[pVᵘ+(1-p)Vᵈ]",
          [SPOT, STRIKE, YEARS, RATE, VOL, OPTION,
           choice("exercise", "american", ["american", "european"]),
           numeric("steps", 160, 20, 400, 20, integer=True)], "line2d"),
    model("implied_vol", "Derivatives & Options", "Implied Volatility", "theoretical", 0,
          "Brent root-solve of the BSM price against a user-supplied option price (not a live quote).",
          "Find σ*: BSM(σ*)=observed premium", [SPOT, STRIKE, YEARS, RATE, OPTION,
           numeric("market_price", 10, .0001, 100000, .5)], "line2d"),
    model("mc_option", "Derivatives & Options", "Antithetic Monte Carlo Option", "synthetic", 0,
          "Risk-neutral European option estimate with standard error and 95% Monte Carlo CI.",
          "C ≈ e⁻ʳᵀ (1/N) Σ max(Sₜ−K,0)",
          [SPOT, STRIKE, YEARS, RATE, VOL, OPTION, SEED], "line2d"),
    model("option_surface", "3D Visual Laboratory", "3D BSM Price Surface", "theoretical", 0,
          "Interactive theoretical option-price surface over underlying spot and volatility.",
          "V(S,σ)=BSM(S,K,T,r,σ)", [SPOT, STRIKE, YEARS, RATE, OPTION], "surface3d"),
    model("risk_surface", "3D Visual Laboratory", "3D Correlation Stress Surface", "historical", 60,
          "Observed two-asset volatilities with a hypothetical stressed correlation and weight grid.",
          "σₚ²=w²σ₁²+(1−w)²σ₂²+2w(1−w)ρσ₁σ₂",
          [ASSETS], "surface3d"),
    model("min_variance", "Portfolio Optimization", "Minimum Variance", "historical", 60,
          "Long-only constrained quadratic program; in-sample, not a backtest.",
          "min wᵀΣw  s.t. Σw=1, 0≤wᵢ≤cap", [ASSETS, CAP], "bar2d"),
    model("risk_parity", "Portfolio Optimization", "Equal Risk Contribution", "historical", 60,
          "Long-only equal variance-contribution approximation; numerical convergence checked.",
          "wᵢ(Σw)ᵢ ≈ (wᵀΣw)/N", [ASSETS, CAP], "bar2d"),
    model("max_diversification", "Portfolio Optimization", "Maximum Diversification", "historical", 60,
          "Maximize weighted individual volatilities divided by portfolio volatility.",
          "max (Σwᵢσᵢ)/√(wᵀΣw)", [ASSETS, CAP], "bar2d"),
    model("cvar", "Portfolio Optimization", "Historical CVaR Optimizer", "historical", 60,
          "Rockafellar–Uryasev historical scenario linear program; fit in-sample.",
          "min z+(1/N(1−α))Σuᵢ", [ASSETS, CAP, CONFIDENCE], "bar2d"),
    model("black_litterman", "Portfolio Optimization", "Black–Litterman Posterior", "historical", 60,
          "Hypothetical view on the first two assets; does not infer alpha or market equilibrium weights.",
          "μ_post=π+τΣPᵀ(PτΣPᵀ+Ω)⁻¹(Q−Pπ)",
          [ASSETS, numeric("view_spread", .02, -.3, .3, .01),
           numeric("risk_aversion", 3, .2, 15, .2)], "bar2d"),
    model("efficient_frontier", "Portfolio Optimization", "Efficient Frontier", "historical", 60,
          "Constrained in-sample expected return versus minimum risk tradeoff.",
          "min wᵀΣw  s.t. μᵀw=target", [ASSETS, CAP], "line2d"),
    model("historical_tail", "Tail Risk & Inference", "Historical VaR & Tail Mean", "historical", 60,
          "Observed equal-weight basket loss distribution, empirical VaR and tail mean.",
          "VaRα=quantileα(−r); ES=E[loss|loss≥VaR]", [ASSETS, CONFIDENCE], "histogram2d"),
    model("gaussian_tail", "Tail Risk & Inference", "Gaussian VaR & ES", "historical", 60,
          "Normal approximation using observed mean and volatility of an equal-weight basket.",
          "VaRα=−μ+σΦ⁻¹(α)", [ASSETS, CONFIDENCE], "histogram2d"),
    model("student_t_tail", "Tail Risk & Inference", "Student-t VaR & ES", "historical", 60,
          "Fixed degrees-of-freedom Student-t approximation; df is a user assumption, not an MLE.",
          "VaRα=−μ+s·t⁻¹_ν(α)", [ASSETS, CONFIDENCE, numeric("df", 5, 2.1, 30, .5)], "histogram2d"),
    model("evt", "Tail Risk & Inference", "Extreme Value (POT/GPD)", "historical", 180,
          "Exploratory peak-over-threshold fit; unstable without extensive tail history.",
          "P(L>x|L>u) ≈ GPD(ξ,β)", [ASSETS, numeric("threshold_quantile", .85, .65, .94, .01),
          numeric("confidence", .98, .9, .995, .005)], "histogram2d"),
    model("newey_west", "Tail Risk & Inference", "Newey–West HAC Mean Test", "historical", 60,
          "HAC z-test on observed equal-weight basket returns; asymptotic p-value.",
          "z = mean(r) / HAC-SE(mean)", [ASSETS], "line2d"),
    model("bootstrap_sharpe", "Tail Risk & Inference", "Block Bootstrap Sharpe", "historical", 60,
          "Circular moving-block bootstrap interval; in-sample and stationarity-dependent.",
          "Sharpe = √K·mean(r)/sd(r)", [ASSETS, SEED,
           numeric("block_length", 5, 2, 20, 1, integer=True)], "line2d"),
]

CATALOG = {item["id"]: item for item in MODELS}


def validate_parameters(model_id: str, supplied: dict | None) -> dict:
    if model_id not in CATALOG:
        raise ValueError("Unknown model; choose a registered research algorithm")
    if not isinstance(supplied, dict):
        raise ValueError("parameters must be a JSON object")
    definitions = {item["key"]: item for item in CATALOG[model_id]["parameters"]}
    unknown = sorted(set(supplied) - set(definitions))
    if unknown:
        raise ValueError("Unexpected model parameter(s): " + ", ".join(unknown))
    result = {}
    for key, spec in definitions.items():
        value = supplied.get(key, spec["default"])
        if spec["type"] == "select":
            if value not in spec["options"]:
                raise ValueError(key + " must be one of " + ", ".join(spec["options"]))
        elif spec["type"] == "symbol":
            if not isinstance(value, str) or len(value) > 32 or (
                    value and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._&-]{0,31}", value)):
                raise ValueError(key + " must be an exact dataset stock symbol, max 32 characters")
        else:
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(key + " must be a finite number")
            if value < spec["min"] or value > spec["max"]:
                raise ValueError(key + " outside supported bounds")
            if spec["type"] == "integer":
                if int(value) != value:
                    raise ValueError(key + " must be an integer")
                value = int(value)
        result[key] = value
    if model_id == "gbm_fit" and result["target"] == "stock" and not result["ticker"]:
        raise ValueError("Choose a stock symbol when target=stock")
    if model_id == "pca" and result["components"] > result["assets"]:
        raise ValueError("PCA components cannot exceed selected assets")
    if model_id in {"min_variance","risk_parity","max_diversification","cvar","efficient_frontier"}:
        if result["assets"] * result["max_weight"] < 1 - 1e-10:
            raise ValueError("The asset count and max weight cannot sum to a fully invested portfolio")
    return result
