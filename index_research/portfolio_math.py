"""Institutional-style portfolio mathematics; annualized covariances/returns.

Research estimators only. Run rolling/holdout evaluation before performance claims.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize


def _aligned(covariance: pd.DataFrame, expected: pd.Series | None = None):
    c = covariance.astype(float)
    if c.empty or not c.index.equals(c.columns) or c.columns.has_duplicates:
        raise ValueError("covariance must have matching ordered unique identifiers")
    a = c.to_numpy()
    if not np.isfinite(a).all() or not np.allclose(a, a.T, atol=1e-10):
        raise ValueError("covariance must be finite and symmetric")
    if np.linalg.eigvalsh(a).min() < -1e-9:
        raise ValueError("covariance must be positive semidefinite")
    mu = None if expected is None else expected.reindex(c.index)
    if mu is not None and (mu.isna().any() or not np.isfinite(mu.to_numpy()).all()):
        raise ValueError("expected returns must align and be finite")
    return c, a, mu


def portfolio_risk_contributions(weights: pd.Series, covariance: pd.DataFrame) -> pd.DataFrame:
    """Euler decomposition: RC_i = w_i*(Sigma*w)_i / sigma_p; sum RC = sigma_p."""
    c, a, _ = _aligned(covariance)
    w = weights.reindex(c.index)
    if w.isna().any() or not np.isfinite(w.to_numpy()).all():
        raise ValueError("nonfinite or missing weights")
    v = w.to_numpy(dtype=float)
    sigma = float(np.sqrt(max(0, v @ a @ v)))
    if sigma <= 1e-14:
        raise ValueError("risk decomposition undefined at zero portfolio volatility")
    marginal = a @ v / sigma
    absolute = v * marginal
    return pd.DataFrame({
        "weight": v, "marginal_volatility": marginal,
        "volatility_contribution": absolute,
        "fraction_of_total_risk": absolute / sigma,
    }, index=c.index)


def _solve(objective, gradient, n: int, max_weight: float,
           constraints: list | None = None, initial: np.ndarray | None = None):
    if not (0 < max_weight <= 1) or n * max_weight < 1 - 1e-9:
        raise ValueError("max_weight constraint infeasible")
    cons = [{"type": "eq", "fun": lambda w: np.sum(w)-1,
             "jac": lambda w: np.ones(n)}]
    if constraints:
        cons.extend(constraints)
    x0 = np.full(n, 1/n) if initial is None else initial
    ans = minimize(objective, x0, jac=gradient, method="SLSQP",
                   bounds=[(0, max_weight)]*n, constraints=cons,
                   options={"maxiter": 3000, "ftol": 1e-12})
    if not ans.success or not np.isfinite(ans.x).all() or abs(ans.x.sum()-1)>1e-6 or ans.x.max()>max_weight+1e-6:
        raise ValueError(f"optimization failed or infeasible: {ans.message}")
    return ans.x


def efficient_frontier(expected_annual: pd.Series, covariance_annual: pd.DataFrame,
                       targets: list[float], max_weight: float = 1.) -> pd.DataFrame:
    """Minimum portfolio variance at each annual expected-return equality target."""
    c, a, mu = _aligned(covariance_annual, expected_annual)
    m = mu.to_numpy()
    rows = []
    for target in targets:
        if not np.isfinite(target):
            raise ValueError("target returns must be finite")
        constraints = [{"type":"eq","fun":lambda w,target=target: w@m-target,
                        "jac":lambda w: m}]
        try:
            w = _solve(lambda v: float(v@a@v), lambda v: 2*a@v, len(m),
                       max_weight, constraints)
            rows.append({"target_return":float(target), "realized_expected_return":float(w@m),
                         "volatility":float(np.sqrt(max(w@a@w,0))),
                         **{f"weight_{key}":float(w[i]) for i,key in enumerate(c.index)},
                         "feasible":True})
        except ValueError:
            rows.append({"target_return":float(target), "realized_expected_return":np.nan,
                         "volatility":np.nan, "feasible":False})
    return pd.DataFrame(rows)


def risk_parity(covariance_annual: pd.DataFrame, max_weight: float = 1.) -> pd.Series:
    """Long-only equal *variance-contribution* portfolio approximation.

    Minimizes squared deviations of w_i(Sigma w)_i from total variance/n.
    Some covariance/cap regimes do not admit exact equal contributions.
    """
    c,a,_ = _aligned(covariance_annual)
    n=len(c)
    def objective(w):
        contribution=w*(a@w)
        target=(w@a@w)/n
        return float(((contribution-target)**2).sum())
    w=_solve(objective,None,n,max_weight)
    return pd.Series(w,index=c.index,name="risk_parity_weight")


def maximum_diversification(covariance_annual: pd.DataFrame, max_weight: float = 1.) -> pd.Series:
    """Maximize weighted standalone vol / portfolio vol, long only."""
    c,a,_=_aligned(covariance_annual)
    standalone=np.sqrt(np.diag(a))
    if (standalone<=0).any():
        raise ValueError("individual variance must be positive")
    def objective(w):
        denominator=max(float(np.sqrt(max(0,w@a@w))),1e-15)
        return -float(w@standalone)/denominator
    w=_solve(objective,None,len(c),max_weight)
    return pd.Series(w,index=c.index,name="max_diversification_weight")


def tracking_error_optimizer(expected_active_annual: pd.Series,
                             covariance_annual: pd.DataFrame, benchmark_weights: pd.Series,
                             risk_aversion: float = 10., max_weight: float = 1.,
                             turnover_penalty: float = 0.,
                             current_weights: pd.Series | None = None) -> pd.Series:
    """Maximize alpha'w - gamma/2 * (w-b)'Sigma(w-b) - tc * ||w-current||^2.

    Alpha denotes annual expected *active* return estimates; not fitted or
    inferred by this routine. Quadratic turnover penalty is a smooth proxy,
    not actual transaction costs.
    """
    c,a,alpha=_aligned(covariance_annual,expected_active_annual)
    b=benchmark_weights.reindex(c.index)
    if b.isna().any() or (b<0).any() or abs(b.sum()-1)>1e-8:
        raise ValueError("benchmark weights must be nonnegative and sum to 1")
    if risk_aversion<=0 or turnover_penalty<0:
        raise ValueError("risk_aversion must be positive and turnover penalty nonnegative")
    current=b if current_weights is None else current_weights.reindex(c.index)
    if current.isna().any() or not np.isfinite(current.to_numpy()).all():
        raise ValueError("current weights must align")
    bb=b.to_numpy(dtype=float)
    cc=current.to_numpy(dtype=float)
    aa=alpha.to_numpy(dtype=float)
    def obj(w):
        d=w-bb
        return float(-aa@w+0.5*risk_aversion*(d@a@d)+turnover_penalty*((w-cc)**2).sum())
    def jac(w):
        return -aa+risk_aversion*a@(w-bb)+2*turnover_penalty*(w-cc)
    result=_solve(obj,jac,len(c),max_weight,initial=bb)
    return pd.Series(result,index=c.index,name="tracking_error_optimized")


def tracking_error(weights: pd.Series, benchmark_weights: pd.Series,
                   covariance_annual: pd.DataFrame) -> float:
    """Annualized ex-ante active volatility under supplied annualized covariance."""
    c,a,_=_aligned(covariance_annual)
    w=weights.reindex(c.index)
    b=benchmark_weights.reindex(c.index)
    if w.isna().any() or b.isna().any():
        raise ValueError("weights must align")
    d=(w-b).to_numpy(dtype=float)
    return float(np.sqrt(max(d@a@d,0)))


def shrinkage_mean(returns: pd.DataFrame, prior: float = 0.,
                   intensity: float = .5, periods_per_year: int = 12) -> pd.Series:
    """Fixed-strength sample-mean shrinkage. NOT Black-Litterman or an empirical Bayes fit."""
    if not 0<=intensity<=1 or periods_per_year<1:
        raise ValueError("invalid shrinkage inputs")
    x=returns.astype(float)
    if len(x)<3 or x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError("complete finite returns required")
    return ((1-intensity)*x.mean()+intensity*prior)*periods_per_year
