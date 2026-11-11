"""Downside risk, stochastic distribution assumptions, and scenario mathematics.

Return units: simple decimals. Covariance units: per holding period unless
otherwise explicitly documented. Returns from simulated distributions are not
forecasts of future losses without appropriate calibration and validation.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm, t as student_t, genpareto


def gaussian_var_es(mean: float, volatility: float, confidence: float=0.95) -> dict:
    """One-period Gaussian VaR/ES in *positive loss* sign convention.

    VaR = -mu + sigma Phi^-1(alpha);
    ES = -mu + sigma phi(Phi^-1(alpha))/(1-alpha).
    """
    if not np.isfinite([mean,volatility]).all() or volatility<=0 or not 0<confidence<1:
        raise ValueError("finite mean, positive volatility and confidence in (0,1)")
    z=norm.ppf(confidence)
    return {"var":float(-mean+volatility*z),
            "expected_shortfall":float(-mean+volatility*norm.pdf(z)/(1-confidence)),
            "confidence":confidence,"model":"gaussian_one_period"}


def student_t_var_es(location: float, scale: float, df: float,
                     confidence: float=0.95) -> dict:
    """One-period Student-t location-scale loss VaR/ES, df>1.

    Scale is Student-t distribution *scale* not its standard deviation.
    """
    if not np.isfinite([location,scale,df]).all() or scale<=0 or df<=1 or not 0<confidence<1:
        raise ValueError("Student-t requires scale>0, df>1, valid confidence")
    z=student_t.ppf(confidence,df)
    density=student_t.pdf(z,df)
    tail_mean=(df+z*z)/((df-1)*(1-confidence))*density
    return {"var":float(-location+scale*z),
            "expected_shortfall":float(-location+scale*tail_mean),
            "confidence":confidence,"model":"student_t_one_period","df":df}


def correlated_gaussian_scenarios(expected_returns: pd.Series,
                                  covariance: pd.DataFrame,
                                  draws: int=10000,seed: int=2026) -> pd.DataFrame:
    """Simulate correlated one-period returns using eigenvalue-clipped PSD factor.

    Zero/near-zero numerical eigenvalues are permitted. Does NOT imply normal
    market returns or calibrated tail dependence.
    """
    if not expected_returns.index.equals(covariance.index) or not covariance.index.equals(covariance.columns):
        raise ValueError("series and covariance security identifiers must exactly align")
    if draws<100 or not np.isfinite(expected_returns.to_numpy(dtype=float)).all():
        raise ValueError("draws >= 100 and finite expected returns required")
    c=covariance.to_numpy(dtype=float)
    if not np.isfinite(c).all() or not np.allclose(c,c.T,atol=1e-10):
        raise ValueError("covariance must be finite symmetric")
    ev,q=np.linalg.eigh((c+c.T)/2)
    if ev.min() < -1e-9:
        raise ValueError("negative covariance eigenvalue")
    root=q@np.diag(np.sqrt(np.maximum(ev,0)))
    rng=np.random.default_rng(seed)
    simulated=rng.standard_normal((draws,len(ev)))@root.T+expected_returns.to_numpy(dtype=float)
    return pd.DataFrame(simulated,columns=expected_returns.index)


def portfolio_monte_carlo_risk(weights: pd.Series, expected_returns: pd.Series,
                               covariance: pd.DataFrame,confidence: float=0.95,
                               draws: int=10000,seed: int=2026) -> dict:
    """Gaussian scenario VaR/ES of linear portfolio, using empirical quantiles."""
    if not weights.index.equals(expected_returns.index):
        raise ValueError("weight labels mismatch")
    w=weights.to_numpy(dtype=float)
    if not np.isfinite(w).all() or (w<-1e-10).any() or abs(w.sum()-1)>1e-7:
        raise ValueError("portfolio weights must sum to one and be long-only")
    if not 0<confidence<1:
        raise ValueError("invalid confidence")
    sample=correlated_gaussian_scenarios(expected_returns,covariance,draws,seed)
    losses=-(sample.to_numpy()@w)
    quant=float(np.quantile(losses,confidence))
    return {"var":quant,"expected_shortfall":float(losses[losses>=quant].mean()),
            "simulations":draws,"model":"correlated_gaussian"}


def historical_scenario_impact(weights: pd.Series, shocks: pd.DataFrame) -> pd.DataFrame:
    """Scenario contribution: each shock row is asset return under one scenario.

    Simple linear shocks do not capture nonlinear options, price limits or
    second-round effects. Shock matrix is explicit user input.
    """
    if weights.empty or weights.index.has_duplicates or not np.isfinite(weights.to_numpy(dtype=float)).all():
        raise ValueError("invalid portfolio weights")
    if (weights<0).any() or abs(weights.sum()-1)>1e-7:
        raise ValueError("long-only weights must sum to one")
    if not shocks.columns.equals(weights.index) or shocks.isna().any().any() or not np.isfinite(shocks.to_numpy(dtype=float)).all():
        raise ValueError("scenario security columns must align and be finite")
    contributions=shocks.mul(weights,axis=1)
    result=contributions.copy()
    result["portfolio_return"]=contributions.sum(axis=1)
    return result


def parametric_expected_shortfall_backtest(returns: pd.Series, var_forecasts: pd.Series,
                                           confidence: float=0.95) -> dict:
    """Simple VaR exceedance diagnostics with exact-aligned one-period forecasts.

    Forecast for return at t must be constructed using data strictly before t.
    Provides exceedance fraction and Kupiec LRuc (chi-square asymptotic),
    NOT an independence/conditional coverage validation.
    """
    if not returns.index.equals(var_forecasts.index):
        raise ValueError("forecasts must share return timestamps")
    x=returns.to_numpy(dtype=float)
    limits=var_forecasts.to_numpy(dtype=float)
    if len(x)<30 or not np.isfinite(x).all() or not np.isfinite(limits).all() or not 0<confidence<1:
        raise ValueError("at least 30 aligned finite observations required")
    hits=-x>limits
    n=len(x)
    k=int(hits.sum())
    expected=1-confidence
    # Numerically safe likelihood on boundary exceedance rates.
    observed=k/n
    def binlog(p):
        return (k*np.log(p) if k else 0.)+((n-k)*np.log1p(-p) if n-k else 0.)
    unrestricted=binlog(observed) if 0<observed<1 else 0.
    restricted=binlog(expected)
    lr=max(0.,float(2*(unrestricted-restricted)))
    from scipy.stats import chi2
    return {"observations":n,"exceedances":k,
            "exceedance_rate":float(observed),
            "expected_rate":float(expected),
            "kupiec_lruc":lr,
            "kupiec_p_value_asymptotic":float(chi2.sf(lr,1))}


def evt_peak_over_threshold(losses: pd.Series, threshold_quantile: float=0.90,
                            confidence: float=0.99) -> dict:
    """Exploratory peaks-over-threshold GPD approximation on upper loss tail.

    Small samples, dependence and unstable threshold choice can make this
    estimator unreliable. Fit only on training data; no regulatory claim.
    """
    x=pd.Series(losses,dtype=float).dropna().to_numpy()
    if len(x)<100 or not np.isfinite(x).all() or not 0.5<threshold_quantile<confidence<1:
        raise ValueError("require >=100 losses and ordered threshold/confidence")
    threshold=float(np.quantile(x,threshold_quantile))
    exceedances=x[x>threshold]-threshold
    if len(exceedances)<20:
        raise ValueError("insufficient exceedances to fit GPD")
    shape,_,scale=genpareto.fit(exceedances,floc=0)
    tail_fraction=len(exceedances)/len(x)
    if scale<=0 or not np.isfinite([shape,scale]).all():
        raise ValueError("invalid fitted tail")
    target_survival=(1-confidence)/tail_fraction
    if not 0<target_survival<1:
        raise ValueError("target confidence below empirical tail start")
    if abs(shape)<1e-8:
        extra=-scale*np.log(target_survival)
    else:
        extra=scale/shape*(target_survival**(-shape)-1)
    q=threshold+extra
    return {"loss_quantile":float(q),"threshold":threshold,
            "tail_fraction":float(tail_fraction),
            "gpd_shape":float(shape),"gpd_scale":float(scale),
            "exceedance_count":len(exceedances),
            "method":"exploratory_peaks_over_threshold"}
