"""Constrained index and portfolio optimization mathematics.

All covariances are annualized and expected returns are annualized decimal values.
Portfolios are fully invested and long-only. The optional benchmark is an
explicit vector of weights, not an inferred market index. These routines fit
on their inputs; callers must implement time-vintage-safe rolling estimation.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize


@dataclass(frozen=True)
class OptimizedPortfolio:
    weights: pd.Series
    expected_return: float
    volatility: float
    tracking_error: float | None
    concentration_hhi: float
    objective: str


def _inputs(covariance: pd.DataFrame, expected_returns=None, benchmark=None):
    if not isinstance(covariance, pd.DataFrame) or covariance.empty:
        raise ValueError("covariance must be a nonempty DataFrame")
    if not covariance.index.equals(covariance.columns) or covariance.index.has_duplicates:
        raise ValueError("row/column security order must exactly match")
    c = covariance.to_numpy(dtype=float)
    if not np.isfinite(c).all() or not np.allclose(c,c.T,atol=1e-10):
        raise ValueError("covariance must be symmetric and finite")
    if np.linalg.eigvalsh(c).min() < -1e-9:
        raise ValueError("covariance must be positive semidefinite")
    c = (c + c.T)/2
    n = len(c)
    if expected_returns is None:
        mu = np.zeros(n)
    else:
        if not isinstance(expected_returns,pd.Series) or not expected_returns.index.equals(covariance.index):
            raise ValueError("expected return labels must match")
        mu = expected_returns.to_numpy(dtype=float)
    if not np.isfinite(mu).all():
        raise ValueError("expected returns must be finite")
    b = None
    if benchmark is not None:
        if not isinstance(benchmark,pd.Series) or not benchmark.index.equals(covariance.index):
            raise ValueError("benchmark labels must match")
        b = benchmark.to_numpy(dtype=float)
        if not np.isfinite(b).all() or (b < -1e-10).any() or abs(b.sum()-1)>1e-7:
            raise ValueError("benchmark must have nonnegative weights summing to 1")
    return c, mu, b


def _solve(c, mu, benchmark, objective, bounds, constraints, start, kind):
    n=len(c)
    res=minimize(objective,start,method="SLSQP",bounds=bounds,
                 constraints=constraints,options={"maxiter":3000,"ftol":1e-11})
    w=res.x
    if not res.success or not np.isfinite(w).all() or abs(w.sum()-1)>1e-6:
        raise RuntimeError(f"Portfolio optimization failed: {res.message}")
    if any(w[i] < lo-1e-6 or w[i]>hi+1e-6 for i,(lo,hi) in enumerate(bounds)):
        raise RuntimeError("optimized weights violate bounds")
    for constraint in constraints:
        value=float(np.min(np.atleast_1d(constraint["fun"](w))))
        if constraint["type"]=="ineq" and value < -1e-6:
            raise RuntimeError("inequality constraint violated")
    delta=w-benchmark if benchmark is not None else None
    te=float(np.sqrt(max(0,delta@c@delta))) if delta is not None else None
    return OptimizedPortfolio(
        pd.Series(w,index=kind.index,name="weight"),
        float(mu@w),float(np.sqrt(max(0,w@c@w))),te,
        float(np.square(w).sum()),kind.name)


def optimize_portfolio(covariance: pd.DataFrame,
                       expected_returns: pd.Series | None = None,
                       benchmark: pd.Series | None = None,
                       objective: str = "minimum_variance",
                       max_weight: float = 1.0,
                       target_return: float | None = None,
                       tracking_error_limit: float | None = None,
                       risk_aversion: float = 3.0,
                       min_weight: float = 0.0) -> OptimizedPortfolio:
    """Minimum variance, mean-variance utility, or active-risk objective.

    'minimum_tracking_error' minimizes (w-b)^T Sigma (w-b).
    'active_utility' maximizes (mu-mu_b)'(w-b) - lambda/2 * active variance.
    The active return term is equivalent to mu'w up to a constant.
    Neither result is evidence of out-of-sample optimality.
    """
    c,mu,b=_inputs(covariance,expected_returns,benchmark)
    n=len(c)
    allowed={"minimum_variance","mean_variance","minimum_tracking_error","active_utility"}
    if objective not in allowed:
        raise ValueError("unsupported optimization objective")
    if objective in {"minimum_tracking_error","active_utility"} and b is None:
        raise ValueError("active objectives require benchmark weights")
    if min_weight < 0 or max_weight > 1 or max_weight <= 0 or min_weight > max_weight or n*max_weight < 1-1e-10 or n*min_weight > 1+1e-10:
        raise ValueError("infeasible long-only weight bounds")
    if tracking_error_limit is not None and (b is None or tracking_error_limit < 0):
        raise ValueError("tracking error requires benchmark and nonnegative limit")
    if risk_aversion <= 0 or not np.isfinite(risk_aversion):
        raise ValueError("risk_aversion must be positive")
    if target_return is not None and not np.isfinite(target_return):
        raise ValueError("target return must be finite")
    if objective=="minimum_variance":
        obj=lambda w: float(w@c@w)
    elif objective=="mean_variance":
        obj=lambda w: float(0.5*risk_aversion*(w@c@w)-mu@w)
    elif objective=="minimum_tracking_error":
        obj=lambda w: float((w-b)@c@(w-b))
    else:
        obj=lambda w: float(0.5*risk_aversion*((w-b)@c@(w-b))-mu@(w-b))
    constraints=[{"type":"eq","fun":lambda w: np.sum(w)-1}]
    if target_return is not None:
        constraints.append({"type":"ineq","fun":lambda w:float(mu@w-target_return)})
    if tracking_error_limit is not None:
        # A constraint on squared TE is smoothly differentiable for SLSQP.
        constraints.append({"type":"ineq","fun":lambda w:float(tracking_error_limit**2-(w-b)@c@(w-b))})
    if b is not None and np.min(b)>=min_weight-1e-12 and np.max(b)<=max_weight+1e-12:
        start=b.copy()
    else:
        start=np.full(n,1/n)
    identity=pd.Series(np.zeros(n),index=covariance.index,name=objective)
    return _solve(c,mu,b,obj,[(min_weight,max_weight)]*n,constraints,start,identity)


def risk_contributions(weights: pd.Series, covariance: pd.DataFrame) -> pd.DataFrame:
    """Euler decomposition of portfolio volatility, in annualized units."""
    if not weights.index.equals(covariance.index):
        raise ValueError("weights and covariance indices must exactly match")
    c,_,_=_inputs(covariance)
    w=weights.to_numpy(dtype=float)
    if not np.isfinite(w).all() or (w<0).any() or abs(w.sum()-1)>1e-7:
        raise ValueError("weights must be long-only and sum to 1")
    variance=float(w@c@w)
    if variance<=1e-15:
        raise ValueError("risk contributions undefined for zero volatility")
    sigma=np.sqrt(variance)
    marginal=c@w/sigma
    contributions=w*marginal
    return pd.DataFrame({"weight":w,"marginal_volatility":marginal,
                         "volatility_contribution":contributions,
                         "share_of_volatility":contributions/sigma},index=weights.index)


def risk_parity(covariance: pd.DataFrame, budgets: pd.Series | None = None,
                max_weight: float = 1.0) -> OptimizedPortfolio:
    """Equal or user-budgeted *variance* risk contribution via SLSQP.

    With positive covariance, variance-budget ratios match volatility-budget
    ratios. Negative contributions may make exact long-only parity impossible.
    """
    c,mu,_=_inputs(covariance)
    n=len(c)
    if budgets is None:
        beta=np.full(n,1/n)
    else:
        if not budgets.index.equals(covariance.index):
            raise ValueError("risk-budget labels must match")
        beta=budgets.to_numpy(dtype=float,copy=True)
        if (beta<=0).any() or not np.isfinite(beta).all():
            raise ValueError("risk budgets must be positive")
        beta/=beta.sum()
    if n*max_weight<1-1e-10 or max_weight<=0 or max_weight>1:
        raise ValueError("infeasible cap")
    def error(w):
        v=float(w@c@w)
        if v<=1e-16:return 1e6
        contribution=w*(c@w)
        return float(np.square(contribution/v-beta).sum())
    constraints=[{"type":"eq","fun":lambda w:np.sum(w)-1}]
    label=pd.Series(0.,index=covariance.index,name="risk_parity")
    solution=_solve(c,mu,None,error,[(1e-9,max_weight)]*n,constraints,np.full(n,1/n),label)
    deviation=np.sqrt(error(solution.weights.to_numpy()))
    if deviation>1e-3:
        raise RuntimeError(
            "Risk parity budget could not be achieved with given covariance "
            f"and caps (L2 budget error={deviation:.6g}); not a valid risk-parity solution")
    return solution


def maximum_diversification(covariance: pd.DataFrame,
                            max_weight: float = 1.0) -> OptimizedPortfolio:
    """Maximize diversification ratio = w' individual_vol / portfolio_vol."""
    c,mu,_=_inputs(covariance)
    n=len(c)
    if max_weight<=0 or max_weight>1 or n*max_weight<1-1e-10:
        raise ValueError("infeasible cap")
    individual=np.sqrt(np.maximum(np.diag(c),0))
    if (individual<=0).any():
        raise ValueError("each constituent needs strictly positive volatility")
    def negative_diversification(w):
        v=float(w@c@w)
        return -float(w@individual/np.sqrt(v)) if v>1e-15 else 1e6
    label=pd.Series(0.,index=covariance.index,name="maximum_diversification")
    return _solve(c,mu,None,negative_diversification,
                  [(0,max_weight)]*n,
                  [{"type":"eq","fun":lambda w:np.sum(w)-1}],
                  np.full(n,1/n),label)


def efficient_frontier(covariance: pd.DataFrame, expected_returns: pd.Series,
                       points: int = 25, max_weight: float = 1.0) -> pd.DataFrame:
    """Ex-ante bounded mean-variance frontier, not realized returns."""
    if points<2:
        raise ValueError("at least two frontier points")
    _inputs(covariance,expected_returns)
    lower=float(expected_returns.min())
    upper=float(expected_returns.max())
    output=[]
    for target in np.linspace(lower,upper,points):
        try:
            sol=optimize_portfolio(covariance,expected_returns,
                                   objective="minimum_variance",
                                   max_weight=max_weight,target_return=float(target))
            output.append({"target_return":float(target),
                           "estimated_return":sol.expected_return,
                           "estimated_volatility":sol.volatility,
                           "hhi":sol.concentration_hhi,"feasible":True})
        except (ValueError,RuntimeError):
            output.append({"target_return":float(target),
                           "estimated_return":np.nan,
                           "estimated_volatility":np.nan,
                           "hhi":np.nan,"feasible":False})
    return pd.DataFrame(output)
