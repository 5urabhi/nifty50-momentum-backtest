"""Deterministic, chart-ready mathematical validation cases.

These are *mathematical unit scenarios*, not real backtest results.
Tests are evaluated on computed tolerances, never on chart appearance.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .math_models import black_scholes, simulate_gbm
from .derivatives import binomial_option, monte_carlo_european
from .portfolio_theory import efficient_frontier, risk_contributions, optimize_portfolio
from .model_validation import rolling_volatility_forecasts, variance_forecast_scores


@dataclass(frozen=True)
class VisualCheck:
    name: str
    observed: float
    expected: float
    tolerance: float
    passed: bool
    interpretation: str


def option_price_surface(option: str = "call", rate: float = 0.04,
                         maturity: float = 1.0, dividend_yield: float = 0.0,
                         strikes: np.ndarray | None = None,
                         volatilities: np.ndarray | None = None,
                         spot: float = 100.0) -> pd.DataFrame:
    """Long-form grid: strike, volatility, theoretical European price."""
    if strikes is None:
        strikes = np.linspace(65, 135, 35)
    if volatilities is None:
        volatilities = np.linspace(.08, .65, 30)
    if not 2 <= len(strikes) <= 100 or not 2 <= len(volatilities) <= 100:
        raise ValueError("option surface grid must have 2-100 points per axis")
    rows=[]
    for vol in volatilities:
        for strike in strikes:
            result=black_scholes(spot,float(strike),maturity,rate,float(vol),
                                 option,dividend_yield)
            rows.append({"strike":float(strike),"volatility":float(vol),
                         "price":result["price"],"delta":result["delta"],
                         "vega":result["vega"]})
    return pd.DataFrame(rows)


def portfolio_risk_surface(covariance: pd.DataFrame, resolution: int = 41) -> pd.DataFrame:
    """Three-asset 2D simplex coordinates plus 3D volatility height.

    w3=1-w1-w2; all portfolios are long-only and fully invested.
    """
    if covariance.shape != (3,3) or not covariance.index.equals(covariance.columns):
        raise ValueError("exactly three covariance-aligned assets required")
    c=covariance.to_numpy(dtype=float)
    if not np.isfinite(c).all() or not np.allclose(c,c.T) or np.linalg.eigvalsh(c).min() < -1e-9:
        raise ValueError("covariance must be positive semidefinite")
    if resolution<8 or resolution>100:
        raise ValueError("resolution outside [8,100]")
    rows=[]
    for i in range(resolution):
        for j in range(resolution-i):
            w1=i/(resolution-1)
            w2=j/(resolution-1)
            w3=max(0.,1-w1-w2)
            w=np.array([w1,w2,w3])
            rows.append({"weight_1":w1,"weight_2":w2,"weight_3":w3,
                         "annual_volatility":float(np.sqrt(max(0,w@c@w)))})
    return pd.DataFrame(rows)


def option_convergence(spot: float=100, strike: float=100, years: float=1,
                       rate: float=.04, vol: float=.2, option: str="call",
                       dividend_yield: float=0., steps: tuple[int,...]=(10,20,40,80,160,320),
                       paths: tuple[int,...]=(1000,2000,4000,8000,16000),
                       seed: int=2026) -> tuple[pd.DataFrame,list[VisualCheck]]:
    """Compare CRR lattice and antithetic MC to analytic BSM, fixed parameters."""
    reference=black_scholes(spot,strike,years,rate,vol,option,dividend_yield)["price"]
    rows=[]
    for n in steps:
        estimate=binomial_option(spot,strike,years,rate,vol,int(n),option,
                                 exercise="european",dividend_yield=dividend_yield)
        rows.append({"method":"CRR binomial", "budget":int(n), "price":estimate,
                     "absolute_error":abs(estimate-reference),
                     "ci_lower":np.nan,"ci_upper":np.nan,"reference":reference})
    for n in paths:
        estimate=monte_carlo_european(spot,strike,years,rate,vol,int(n),option,
                                      dividend_yield=dividend_yield,seed=seed)
        rows.append({"method":"Antithetic Monte Carlo","budget":int(n),
                     "price":estimate["price"],
                     "absolute_error":abs(estimate["price"]-reference),
                     "ci_lower":estimate["ci95_lower"],
                     "ci_upper":estimate["ci95_upper"],
                     "reference":reference})
    frame=pd.DataFrame(rows)
    last_crr=frame[frame.method=="CRR binomial"].iloc[-1]
    last_mc=frame[frame.method=="Antithetic Monte Carlo"].iloc[-1]
    crr_tol=.05
    mc_tol=max(.02,4*(last_mc.ci_upper-last_mc.ci_lower)/3.92)
    checks=[
        VisualCheck("CRR vs analytical European price",float(last_crr.price),
                    float(reference),crr_tol,
                    bool(last_crr.absolute_error<=crr_tol),
                    "Finest lattice should approximate the BSM analytical reference."),
        VisualCheck("Monte Carlo vs analytical European price",float(last_mc.price),
                    float(reference),mc_tol,
                    bool(last_mc.absolute_error<=mc_tol),
                    "Numerical simulation error is allowed within a stochastic tolerance."),
    ]
    return frame,checks


def identity_checks(spot: float=100.,strike:float=100.,years:float=1.,
                    rate:float=.04,vol:float=.2,
                    dividend_yield:float=0.) -> list[VisualCheck]:
    """Analytic put-call parity and call/put delta parity."""
    call=black_scholes(spot,strike,years,rate,vol,"call",dividend_yield)
    put=black_scholes(spot,strike,years,rate,vol,"put",dividend_yield)
    parity=spot*np.exp(-dividend_yield*years)-strike*np.exp(-rate*years)
    delta_reference=np.exp(-dividend_yield*years)
    return [
        VisualCheck("Put-call parity",call["price"]-put["price"],
                    float(parity),1e-9,
                    abs((call["price"]-put["price"])-parity)<1e-9,
                    "European call minus put equals discounted spot minus discounted strike."),
        VisualCheck("Call-put delta parity",call["delta"]-put["delta"],
                    float(delta_reference),1e-9,
                    abs((call["delta"]-put["delta"])-delta_reference)<1e-9,
                    "European delta parity under continuous dividend yield."),
    ]


def gbm_moments(spot: float=100.,mu:float=.05,sigma:float=.2,
                years:float=1.,steps:int=36,paths:int=6000,
                seed:int=2026) -> tuple[pd.DataFrame,list[VisualCheck]]:
    """Monte Carlo mean vs analytic GBM mean, with independent path sampling."""
    if paths<1000:
        raise ValueError("minimum 1000 paths for moment visualization")
    sample=simulate_gbm(spot,mu,sigma,years,steps,paths,seed)
    t=np.linspace(0,years,steps+1)
    expectation=spot*np.exp(mu*t)
    empirical=sample.mean(axis=1)
    terminal_sd=float(sample[-1].std(ddof=1))
    se=terminal_sd/np.sqrt(paths)
    tolerance=max(1e-8,4*se)
    check=VisualCheck("GBM terminal expectation",
                      float(empirical[-1]),float(expectation[-1]),
                      tolerance,abs(empirical[-1]-expectation[-1])<=tolerance,
                      "Simulated mean converges toward analytic E[S(T)]=S(0) exp(mu T).")
    levels=np.quantile(sample,[.05,.5,.95],axis=1)
    data=pd.DataFrame({"year":t,"analytical_mean":expectation,
                       "simulated_mean":empirical,
                       "p05":levels[0],"p50":levels[1],"p95":levels[2]})
    return data,[check]


def validation_table(checks: list[VisualCheck]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Test":check.name,"Observed":check.observed,"Reference":check.expected,
        "Tolerance":check.tolerance,"Absolute error":abs(check.observed-check.expected),
        "Status":"PASS" if check.passed else "FAIL",
        "Meaning":check.interpretation
    } for check in checks])


def three_asset_covariance() -> pd.DataFrame:
    """Explicitly illustrative annualized 3-asset covariance, not fitted market data."""
    labels=pd.Index(["Asset A","Asset B","Asset C"])
    vols=np.array([.12,.20,.30])
    corr=np.array([[1.,.25,.15],[.25,1.,.4],[.15,.4,1.]])
    return pd.DataFrame(corr*np.outer(vols,vols),index=labels,columns=labels)


def risk_contribution_test() -> tuple[pd.DataFrame,list[VisualCheck]]:
    """Euler decomposition test on an explicitly synthetic covariance matrix."""
    c=three_asset_covariance()
    weights=pd.Series([.35,.40,.25],index=c.index)
    contributions=risk_contributions(weights,c)
    total=float(contributions["volatility_contribution"].sum())
    expected=float(np.sqrt(weights.to_numpy()@c.to_numpy()@weights.to_numpy()))
    check=VisualCheck("Euler volatility decomposition",total,expected,1e-10,
                      abs(total-expected)<=1e-10,
                      "Sum of component volatility contributions equals total portfolio volatility.")
    return contributions,[check]
