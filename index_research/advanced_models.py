"""Additional numerical research models; analytical demonstrations only."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize


def principal_components(returns: pd.DataFrame, n_components: int = 3) -> dict:
    """PCA of standardized returns, fitted on supplied history only.

    To avoid leakage, callers must fit PCA on a training window and project
    subsequent dates using the fixed training-window mean/scaling/loadings.
    """
    x=returns.astype(float)
    if x.empty or x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError("PCA requires complete finite historical returns")
    if n_components < 1 or n_components > min(x.shape):
        raise ValueError("invalid number of principal components")
    mu=x.mean(axis=0)
    sd=x.std(axis=0,ddof=1)
    if (sd <= 0).any():
        raise ValueError("constant-return columns cannot be standardized")
    z=(x-mu)/sd
    _, singular, right=np.linalg.svd(z.to_numpy(),full_matrices=False)
    explained=(singular**2)
    explained=explained/explained.sum()
    projected=z.to_numpy() @ right[:n_components].T
    return {
        "loadings":pd.DataFrame(right[:n_components].T,index=x.columns,
            columns=[f"PC{i+1}" for i in range(n_components)]),
        "scores":pd.DataFrame(projected,index=x.index,
            columns=[f"PC{i+1}" for i in range(n_components)]),
        "explained_variance_ratio":explained[:n_components],
        "training_mean":mu,"training_std":sd,
    }


def simulate_ou(initial: float, mean: float, reversion: float,
                diffusion: float, dt: float, steps: int, paths: int,
                seed: int = 2026) -> np.ndarray:
    """Exact-step Ornstein-Uhlenbeck Gaussian transition simulation."""
    if reversion <= 0 or diffusion < 0 or dt <= 0 or steps < 1 or paths < 1:
        raise ValueError("invalid OU inputs")
    rng=np.random.default_rng(seed)
    phi=np.exp(-reversion*dt)
    innovation_sd=diffusion*np.sqrt((1-phi**2)/(2*reversion))
    out=np.zeros((steps+1,paths),dtype=float)
    out[0]=initial
    for t in range(steps):
        out[t+1]=mean+(out[t]-mean)*phi+innovation_sd*rng.standard_normal(paths)
    return out


@dataclass(frozen=True)
class GarchResult:
    omega: float
    alpha: float
    beta: float
    next_variance: float
    converged: bool
    observations: int


def fit_garch11(returns: pd.Series) -> GarchResult:
    """Gaussian GARCH(1,1) MLE, mean-adjusted, decimal return variance.

    Fitted on supplied sample only. Validate out of sample before comparing
    forecasts against EWMA or realized volatility. No leverage effect.
    """
    r=pd.Series(returns,dtype=float).dropna().to_numpy()
    if len(r)<60 or not np.isfinite(r).all():
        raise ValueError("GARCH estimation needs >=60 finite returns")
    centered=100*(r-r.mean())
    initial=float(np.var(centered,ddof=1))
    if initial<1e-10:
        raise ValueError("GARCH requires nonzero return variance")
    def sequence(theta):
        omega,alpha,beta=theta
        h=np.empty(len(centered),dtype=float)
        h[0]=initial
        for i in range(1,len(centered)):
            h[i]=omega+alpha*centered[i-1]**2+beta*h[i-1]
        return h
    def nll(theta):
        omega,alpha,beta=theta
        if alpha+beta>=0.999 or omega<=0 or alpha<0 or beta<0:
            return 1e30
        h=sequence(theta)
        if (h<=0).any() or not np.isfinite(h).all():
            return 1e30
        return float(np.log(h).sum()+np.square(centered).dot(1/h))
    solution=minimize(nll,[max(initial*0.05,1e-8),0.07,0.88],
                      bounds=[(1e-10,initial*10+1e-5),(1e-8,0.999),(1e-8,0.999)],
                      constraints=[{"type":"ineq","fun":lambda p:0.999-p[1]-p[2]}],
                      method="SLSQP",options={"maxiter":1500,"ftol":1e-9})
    if not solution.success or solution.x[1]+solution.x[2]>=0.999:
        raise RuntimeError(f"GARCH solver did not converge: {solution.message}")
    omega,alpha,beta=map(float,solution.x)
    h=sequence(solution.x)
    forecast=omega+alpha*centered[-1]**2+beta*h[-1]
    return GarchResult(omega/10000,alpha,beta,forecast/10000,True,len(r))


def covariance_stress_loss(weights: pd.Series, covariance: pd.DataFrame,
                           z_score: float = 2.326347874) -> float:
    """Gaussian one-period loss quantile assuming ZERO drift.

    Covariance and z_score must refer to the same interval and confidence.
    This is a normal approximation; not an empirical stress-test scenario.
    """
    c=covariance.reindex(index=weights.index,columns=weights.index)
    if c.isna().any().any() or not np.isfinite(c.to_numpy()).all():
        raise ValueError("covariance missing or nonfinite")
    w=weights.astype(float).to_numpy()
    if (not np.isfinite(w).all() or not np.isfinite(z_score) or (w<0).any()
            or w.sum()<=0 or w.sum()>1+1e-8 or z_score<=0):
        raise ValueError("invalid weights or quantile")
    v=float(w@c.to_numpy()@w)
    if v < -1e-10:
        raise ValueError("negative variance")
    return float(z_score*np.sqrt(max(v,0)))
