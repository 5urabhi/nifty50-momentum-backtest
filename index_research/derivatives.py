"""Derivatives/numerical mathematics. Supplemental, not an index backtest engine."""
import numpy as np
from scipy.optimize import brentq
from .math_models import black_scholes


def implied_volatility(price: float, spot: float, strike: float, years: float,
                       rate: float, option: str = "call", dividend_yield: float = 0.,
                       lower: float = 1e-5, upper: float = 5.) -> float:
    """European BSM implied vol using no-arbitrage bounds and Brent root solver."""
    if spot<=0 or strike<=0 or years<=0 or price<0 or option not in ("call","put"):
        raise ValueError("invalid option inputs")
    discount_s=spot*np.exp(-dividend_yield*years)
    discount_k=strike*np.exp(-rate*years)
    intrinsic=max((discount_s-discount_k) if option=="call" else (discount_k-discount_s),0)
    upper_bound=discount_s if option=="call" else discount_k
    if price<=intrinsic or price>=upper_bound:
        raise ValueError("price outside strictly interior European no-arbitrage bounds")
    def residual(vol):
        return black_scholes(spot,strike,years,rate,vol,option,dividend_yield)["price"]-price
    if residual(lower)*residual(upper)>0:
        raise ValueError("volatility not bracketed; expand model bounds")
    return float(brentq(residual,lower,upper,xtol=1e-12))


def monte_carlo_european(spot: float, strike: float, years: float,
                         rate: float, vol: float, paths: int = 100000,
                         option: str = "call", dividend_yield: float = 0.,
                         seed: int = 2026) -> dict:
    """Risk-neutral terminal-price Monte Carlo with antithetic variates."""
    if spot<=0 or strike<=0 or years<=0 or vol<0 or paths<100 or option not in ("call","put"):
        raise ValueError("invalid option parameters")
    pairs=(paths+1)//2
    rng=np.random.default_rng(seed)
    z=rng.standard_normal(pairs)
    drift=(rate-dividend_yield-vol**2/2)*years
    sd=vol*np.sqrt(years)
    a=spot*np.exp(drift+sd*z)
    b=spot*np.exp(drift-sd*z)
    if option=="call":
        values=(np.maximum(a-strike,0)+np.maximum(b-strike,0))/2
    else:
        values=(np.maximum(strike-a,0)+np.maximum(strike-b,0))/2
    discount=np.exp(-rate*years)
    standard_error=float(discount*values.std(ddof=1)/np.sqrt(pairs))
    estimate=float(discount*values.mean())
    return {"price":estimate,"standard_error":standard_error,
            "ci95_lower":estimate-1.96*standard_error,
            "ci95_upper":estimate+1.96*standard_error,
            "independent_pairs":pairs,"seed":seed}


def heston_paths(spot: float, variance: float, years: float,
                 steps: int = 252, paths: int = 1000, rate: float = 0.03,
                 dividend_yield: float = 0., kappa: float = 2.,
                 long_variance: float = 0.04, vol_of_vol: float = 0.4,
                 rho: float = -0.6, seed: int = 2026) -> dict:
    """Heston stochastic-volatility full-truncation Euler simulation.

    dS/S = (r-q)dt + sqrt(v)dW1,
    dv = kappa(theta-v)dt + xi sqrt(v)dW2.
    corr(dW1,dW2)=rho. Discretization is approximate and can be biased.
    """
    if spot<=0 or variance<0 or years<=0 or steps<1 or paths<1 or kappa<=0 or long_variance<0 or vol_of_vol<0 or not -1<=rho<=1:
        raise ValueError("invalid Heston parameters")
    rng=np.random.default_rng(seed)
    dt=years/steps
    s=np.empty((steps+1,paths))
    v=np.empty((steps+1,paths))
    s[0]=spot
    v[0]=variance
    for i in range(steps):
        z1=rng.standard_normal(paths)
        z2=rng.standard_normal(paths)
        correlated=rho*z1+np.sqrt(max(0,1-rho*rho))*z2
        active=np.maximum(v[i],0)
        s[i+1]=s[i]*np.exp((rate-dividend_yield-active/2)*dt+np.sqrt(active*dt)*z1)
        v[i+1]=v[i]+kappa*(long_variance-active)*dt+vol_of_vol*np.sqrt(active*dt)*correlated
    return {"prices":s,"variance":v,
            "warning":"Heston paths use full-truncation Euler; no calibration, bias assessment or option-pricing benchmark."}


def merton_jump_diffusion(spot: float, years: float, steps: int, paths: int,
                          drift: float, vol: float, jump_intensity: float,
                          jump_mean_log: float, jump_std_log: float,
                          seed: int = 2026) -> np.ndarray:
    """Physical-measure jump-diffusion with compensated compound Poisson jumps."""
    if spot<=0 or years<=0 or steps<1 or paths<1 or vol<0 or jump_intensity<0 or jump_std_log<0:
        raise ValueError("invalid jump-diffusion parameters")
    rng=np.random.default_rng(seed)
    dt=years/steps
    k=np.exp(jump_mean_log+0.5*jump_std_log**2)-1
    counts=rng.poisson(jump_intensity*dt,(steps,paths))
    standard=rng.standard_normal((steps,paths))
    jump_shocks=rng.standard_normal((steps,paths))
    jump_log=counts*jump_mean_log+np.sqrt(counts)*jump_std_log*jump_shocks
    increments=(drift-0.5*vol**2-jump_intensity*k)*dt+vol*np.sqrt(dt)*standard+jump_log
    return spot*np.exp(np.vstack([np.zeros((1,paths)),np.cumsum(increments,axis=0)]))


def binomial_option(spot: float, strike: float, years: float, rate: float,
                    vol: float, steps: int=200, option: str="call",
                    exercise: str="american", dividend_yield: float=0.) -> float:
    """Cox-Ross-Rubinstein tree for European or American puts/calls."""
    if (spot<=0 or strike<=0 or years<=0 or vol<=0 or steps<1
            or option not in ("call","put") or exercise not in ("american","european")):
        raise ValueError("invalid binomial-tree parameters")
    dt=years/steps
    up=np.exp(vol*np.sqrt(dt))
    down=1/up
    probability=(np.exp((rate-dividend_yield)*dt)-down)/(up-down)
    if not 0<=probability<=1:
        raise ValueError("risk-neutral transition probability outside [0,1]")
    sign=1 if option=="call" else -1
    nodes=np.arange(steps+1)
    terminals=spot*up**nodes*down**(steps-nodes)
    option_values=np.maximum(sign*(terminals-strike),0)
    disc=np.exp(-rate*dt)
    for level in range(steps-1,-1,-1):
        option_values=disc*(probability*option_values[1:]+(1-probability)*option_values[:-1])
        if exercise=="american":
            j=np.arange(level+1)
            underlying=spot*up**j*down**(level-j)
            option_values=np.maximum(option_values,np.maximum(sign*(underlying-strike),0))
    return float(option_values[0])
