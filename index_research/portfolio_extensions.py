"""Additional mathematical asset-allocation tools and convex downside control.

Black-Litterman outputs posterior expectations, NOT out-of-sample alpha.
CVaR optimizer uses historical scenarios and linear Rockafellar-Uryasev
auxiliary variables, solved with scipy.optimize.linprog.
"""
import numpy as np
import pandas as pd
from scipy.optimize import linprog


def black_litterman_posterior(covariance: pd.DataFrame,
                              benchmark_weights: pd.Series,
                              risk_aversion: float,
                              views_matrix: pd.DataFrame,
                              view_returns: pd.Series,
                              tau: float=0.05,
                              view_covariance: pd.DataFrame | None=None) -> dict:
    """Normal-normal Black-Litterman posterior for implied equilibrium returns.

    pi = delta Sigma w_mkt,
    mu_post = pi + tau Sigma P' (P tau Sigma P' + Omega)^-1 (Q-P pi).
    Uses least-square solves for numerical stability. Omega defaults to
    diagonal(P tau Sigma P') (heuristic view confidence choice).
    """
    if not covariance.index.equals(covariance.columns) or covariance.empty:
        raise ValueError("covariance security order mismatch")
    assets=covariance.index
    if not benchmark_weights.index.equals(assets):
        raise ValueError("benchmark weight labels mismatch")
    if views_matrix.empty or not views_matrix.columns.equals(assets):
        raise ValueError("views must have same columns in matching security order")
    if not view_returns.index.equals(views_matrix.index):
        raise ValueError("view return labels mismatch")
    if tau<=0 or risk_aversion<=0:
        raise ValueError("positive tau and risk-aversion required")
    sigma=covariance.to_numpy(dtype=float)
    w=benchmark_weights.to_numpy(dtype=float)
    P=views_matrix.to_numpy(dtype=float)
    Q=view_returns.to_numpy(dtype=float)
    if (not np.isfinite(sigma).all() or not np.allclose(sigma,sigma.T,atol=1e-10)
        or np.linalg.eigvalsh(sigma).min()<-1e-9 or not np.isfinite(w).all()
        or (w<0).any() or abs(w.sum()-1)>1e-8 or not np.isfinite(P).all()
        or not np.isfinite(Q).all()):
        raise ValueError("invalid covariance, weights or views")
    prior=risk_aversion*sigma@w
    scaled=tau*sigma
    if view_covariance is None:
        omega=np.diag(np.maximum(np.diag(P@scaled@P.T),1e-10))
    else:
        if not view_covariance.index.equals(views_matrix.index) or not view_covariance.columns.equals(views_matrix.index):
            raise ValueError("view covariance labels mismatch")
        omega=view_covariance.to_numpy(dtype=float)
        if not np.isfinite(omega).all() or np.linalg.eigvalsh((omega+omega.T)/2).min()<=0:
            raise ValueError("view covariance must be positive definite")
    rhs=Q-P@prior
    system=P@scaled@P.T+omega
    adjustment=scaled@P.T@np.linalg.solve(system,rhs)
    posterior=prior+adjustment
    posterior_uncertainty=scaled-scaled@P.T@np.linalg.solve(system,P@scaled)
    return {
        "equilibrium_returns":pd.Series(prior,index=assets),
        "posterior_expected_returns":pd.Series(posterior,index=assets),
        "posterior_mean_uncertainty":pd.DataFrame(posterior_uncertainty,index=assets,columns=assets),
        "view_residual":pd.Series(rhs,index=views_matrix.index),
        "model":"black_litterman_normal_normal"
    }


def minimize_historical_cvar(scenario_returns: pd.DataFrame, confidence: float=0.95,
                             max_weight: float=1.0, benchmark: pd.Series | None=None,
                             max_active_weight: float | None=None) -> dict:
    """Long-only historical CVaR minimizing z + 1/(N*(1-a)) sum_i u_i.

    Constraints: u_i >= -r_i'w-z, u_i>=0, sum(w)=1 and 0<=w<=cap.
    Scenarios must be ex ante plausible; fitted result is in-sample only.
    """
    if (not isinstance(scenario_returns,pd.DataFrame) or len(scenario_returns)<30
            or scenario_returns.empty or not 0<confidence<1 or not 0<max_weight<=1):
        raise ValueError("invalid scenario data or optimization parameters")
    r=scenario_returns.to_numpy(dtype=float)
    if not np.isfinite(r).all() or scenario_returns.columns.has_duplicates:
        raise ValueError("nonfinite scenarios or duplicate securities")
    n,k=r.shape
    if k*max_weight<1-1e-10:
        raise ValueError("cap makes full investment infeasible")
    if max_active_weight is not None:
        if benchmark is None or not 0<=max_active_weight<=1:
            raise ValueError("active weight cap requires benchmark")
        if not benchmark.index.equals(scenario_returns.columns):
            raise ValueError("benchmark labels mismatch")
        b=benchmark.to_numpy(dtype=float)
        if not np.isfinite(b).all() or (b<0).any() or abs(b.sum()-1)>1e-8:
            raise ValueError("invalid benchmark weights")
    else:
        b=None
    # Decision x = [w_1..w_k, z, u_1..u_n]
    cost=np.concatenate([np.zeros(k),[1.],np.full(n,1/(n*(1-confidence)))])
    inequality=np.hstack([-r,-np.ones((n,1)),-np.eye(n)])
    upper=np.zeros(n)
    eq=np.zeros((1,k+1+n))
    eq[0,:k]=1
    bounds=[(0,max_weight)]*k+[(None,None)]+[(0,None)]*n
    if b is not None:
        for j in range(k):
            row=np.zeros(k+1+n);row[j]=1
            inequality=np.vstack([inequality,row])
            upper=np.append(upper,b[j]+max_active_weight)
            inequality=np.vstack([inequality,-row])
            upper=np.append(upper,max_active_weight-b[j])
    solution=linprog(cost,A_ub=inequality,b_ub=upper,A_eq=eq,b_eq=[1],
                     bounds=bounds,method="highs")
    if not solution.success:
        raise RuntimeError(f"CVaR LP failed: {solution.message}")
    weights=pd.Series(solution.x[:k],index=scenario_returns.columns,name="cvar_weight")
    losses=-(r@weights.to_numpy())
    q=float(np.quantile(losses,confidence))
    return {
        "weights":weights,
        "optimization_objective_cvar":float(solution.fun),
        "empirical_var":q,
        "empirical_tail_mean":float(losses[losses>=q].mean()),
        "scenarios":n,
        "note":"In-sample historical scenario minimization, not regulatory ES."
    }


def factor_neutralize_scores(scores: pd.Series, exposures: pd.DataFrame,
                             add_intercept: bool=True) -> pd.Series:
    """OLS residual factor signal orthogonal to supplied cross-sectional exposures.

    No automatic sector one-hot creation or future exposure information.
    The inputs MUST be effective-dated on the scoring date.
    """
    if not scores.index.equals(exposures.index) or exposures.empty:
        raise ValueError("factor signal and exposure securities must match")
    joint=exposures.astype(float).join(scores.rename("__signal__")).dropna()
    if len(joint)<=exposures.shape[1]+1 or not np.isfinite(joint.to_numpy()).all():
        raise ValueError("insufficient complete cross-sectional data")
    X=joint[exposures.columns].to_numpy()
    if add_intercept:
        X=np.column_stack([np.ones(len(X)),X])
    y=joint["__signal__"].to_numpy()
    if np.linalg.matrix_rank(X)<X.shape[1]:
        raise ValueError("collinear exposures")
    residual=y-X@np.linalg.lstsq(X,y,rcond=None)[0]
    return pd.Series(residual,index=joint.index,name="neutralized_score").reindex(scores.index)
