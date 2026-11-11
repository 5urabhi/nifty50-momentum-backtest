"""Quantitative modeling laboratory: validated primitives, not trading advice.

All return inputs are decimal simple returns (0.01 = 1%). No fitted model
may use observations from a test interval when evaluated out of sample.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm


def _return_matrix(returns: pd.DataFrame, minimum: int = 3) -> pd.DataFrame:
    if not isinstance(returns, pd.DataFrame) or len(returns) < minimum:
        raise ValueError("need a DataFrame with sufficient observations")
    x = returns.astype(float)
    if x.columns.has_duplicates or x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError("return matrix requires distinct columns and finite complete observations")
    return x


def sample_covariance(returns: pd.DataFrame, periods_per_year: int = 12) -> pd.DataFrame:
    """Annualized sample covariance using ddof=1."""
    x = _return_matrix(returns)
    if periods_per_year < 1:
        raise ValueError("periods_per_year must be positive")
    return x.cov() * periods_per_year


def shrinkage_covariance(returns: pd.DataFrame, intensity: float = 0.25,
                         periods_per_year: int = 12) -> pd.DataFrame:
    """Constant-intensity diagonal shrinkage; NOT Ledoit-Wolf."""
    if not 0 <= intensity <= 1:
        raise ValueError("intensity outside [0,1]")
    sample = sample_covariance(returns, periods_per_year)
    diagonal = np.diag(np.diag(sample.to_numpy()))
    values = (1 - intensity) * sample.to_numpy() + intensity * diagonal
    return pd.DataFrame(values, index=sample.index, columns=sample.columns)


def ewma_covariance(returns: pd.DataFrame, decay: float = 0.94,
                    periods_per_year: int = 12) -> pd.DataFrame:
    """Annualized EWMA covariance about a weighted mean; newest observation has highest weight."""
    x = _return_matrix(returns).to_numpy()
    if not 0 < decay < 1 or periods_per_year < 1:
        raise ValueError("invalid EWMA parameter")
    weights = (1 - decay) * decay ** np.arange(len(x) - 1, -1, -1)
    weights /= weights.sum()
    mean = weights @ x
    centered = x - mean
    matrix = (centered * weights[:, None]).T @ centered * periods_per_year
    return pd.DataFrame(matrix, index=returns.columns, columns=returns.columns)


@dataclass(frozen=True)
class PortfolioSolution:
    weights: pd.Series
    volatility: float
    expected_return: float
    success: bool
    message: str


def minimum_variance(covariance: pd.DataFrame, expected_returns: pd.Series | None = None,
                     max_weight: float = 1.0) -> PortfolioSolution:
    """Long-only min-variance index; SLSQP with exact full-investment and bounds."""
    sigma = covariance.astype(float)
    if sigma.empty or not sigma.index.equals(sigma.columns):
        raise ValueError("covariance must have matching ordered row/column identifiers")
    c = sigma.to_numpy()
    n = len(c)
    if not np.isfinite(c).all() or not np.allclose(c, c.T, atol=1e-10):
        raise ValueError("covariance must be finite symmetric")
    if np.linalg.eigvalsh(c).min() < -1e-9:
        raise ValueError("covariance must be positive semidefinite")
    if max_weight <= 0 or n * max_weight < 1 - 1e-10:
        raise ValueError("infeasible max_weight")
    if expected_returns is None:
        mu = pd.Series(0.0, index=sigma.index)
    else:
        mu = expected_returns.reindex(sigma.index)
        if mu.isna().any() or not np.isfinite(mu.to_numpy()).all():
            raise ValueError("expected returns must align")
    res = minimize(lambda w: float(w @ c @ w),
                   x0=np.full(n, 1.0/n),
                   jac=lambda w: 2 * c @ w,
                   bounds=[(0, max_weight)] * n,
                   constraints=[{"type":"eq", "fun":lambda w: np.sum(w)-1,
                                 "jac":lambda w: np.ones(n)}],
                   method="SLSQP", options={"maxiter":2000, "ftol":1e-12})
    if not res.success or abs(np.sum(res.x) - 1) > 1e-6 or np.min(res.x) < -1e-6 or np.max(res.x) > max_weight + 1e-6:
        raise RuntimeError(f"optimization failed: {res.message}")
    w = pd.Series(np.maximum(res.x, 0), index=sigma.index, name="weight")
    w = w / w.sum()
    return PortfolioSolution(w, float(np.sqrt(max(0, w.to_numpy() @ c @ w.to_numpy()))),
                             float(w @ mu), True, str(res.message))


def historical_var_es(returns: pd.Series, confidence: float = 0.95) -> dict[str, float]:
    """Positive loss magnitudes: VaR quantile and mean of losses at/above VaR.

    This empirical tail-mean convention can differ from interpolated Expected
    Shortfall estimators. It should not be mislabeled as regulatory ES.
    """
    r = pd.Series(returns, dtype=float).dropna().to_numpy()
    if len(r) < 20 or not np.isfinite(r).all() or not 0 < confidence < 1:
        raise ValueError("need >=20 finite observations and confidence in (0,1)")
    losses = -r
    var = float(np.quantile(losses, confidence))
    return {"var":var, "expected_shortfall":float(losses[losses >= var].mean())}


def simulate_gbm(s0: float, mu: float, sigma: float, years: float,
                 steps: int, paths: int, seed: int = 0) -> np.ndarray:
    """GBM: dS/S = mu dt + sigma dW. Shape (steps+1, paths)."""
    if s0 <= 0 or sigma < 0 or years <= 0 or steps < 1 or paths < 1:
        raise ValueError("invalid simulation inputs")
    rng = np.random.default_rng(seed)
    dt = years / steps
    increments = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * rng.standard_normal((steps,paths))
    log_paths = np.vstack([np.zeros((1,paths)), np.cumsum(increments,axis=0)])
    return s0 * np.exp(log_paths)


def black_scholes(s: float, k: float, t: float, r: float, sigma: float,
                  option: str = "call", dividend_yield: float = 0.0) -> dict[str,float]:
    """European Black-Scholes-Merton price + delta, gamma, vega, theta and rho.

    Continuous yield q, risk-free rate r, annualized volatility sigma and time t
    in years. theta is value change per year; vega/rho are per 1.0 change.
    """
    if s <= 0 or k <= 0 or t <= 0 or sigma <= 0 or option not in ("call","put"):
        raise ValueError("requires positive s,k,t,sigma and call/put")
    q = dividend_yield
    rt = np.sqrt(t)
    d1 = (np.log(s/k) + (r-q+sigma*sigma/2)*t)/(sigma*rt)
    d2 = d1 - sigma*rt
    dq, dr = np.exp(-q*t), np.exp(-r*t)
    pdf = norm.pdf(d1)
    gamma = dq * pdf / (s*sigma*rt)
    vega = s*dq*pdf*rt
    if option == "call":
        price = s*dq*norm.cdf(d1)-k*dr*norm.cdf(d2)
        delta = dq*norm.cdf(d1)
        theta = -s*dq*pdf*sigma/(2*rt) + q*s*dq*norm.cdf(d1) - r*k*dr*norm.cdf(d2)
        rho = k*t*dr*norm.cdf(d2)
    else:
        price = k*dr*norm.cdf(-d2)-s*dq*norm.cdf(-d1)
        delta = dq*(norm.cdf(d1)-1)
        theta = -s*dq*pdf*sigma/(2*rt) - q*s*dq*norm.cdf(-d1) + r*k*dr*norm.cdf(-d2)
        rho = -k*t*dr*norm.cdf(-d2)
    return {"price":float(price),"delta":float(delta),"gamma":float(gamma),
            "vega":float(vega),"theta":float(theta),"rho":float(rho)}


def factor_regression(asset_returns: pd.Series, factors: pd.DataFrame,
                      risk_free: pd.Series | None = None) -> dict:
    """OLS factor sensitivities; caller must handle time split and factor vintage.

    Factors and asset returns are aligned on exact timestamps; returns are decimal.
    No claim of statistical significance without accounting for serial correlation.
    """
    if factors.empty or factors.columns.has_duplicates:
        raise ValueError("factor data required")
    data = factors.astype(float).join(pd.Series(asset_returns,dtype=float).rename("__asset__"),how="inner")
    if risk_free is not None:
        data = data.join(pd.Series(risk_free,dtype=float).rename("__rf__"),how="inner")
    data = data.dropna()
    if len(data) < len(factors.columns) + 3 or not np.isfinite(data.to_numpy()).all():
        raise ValueError("insufficient complete, aligned data")
    y = data["__asset__"].to_numpy() - (data["__rf__"].to_numpy() if risk_free is not None else 0)
    x = np.column_stack([np.ones(len(data)), data[factors.columns].to_numpy()])
    if np.linalg.matrix_rank(x) != x.shape[1]:
        raise ValueError("collinear factors")
    coefficients = np.linalg.lstsq(x,y,rcond=None)[0]
    fitted = x @ coefficients
    residual = y - fitted
    denom = float(np.sum((y-y.mean())**2))
    r2 = 1 - float(residual@residual)/denom if denom > 0 else float("nan")
    return {"alpha_per_period":float(coefficients[0]),
            "betas":dict(zip(factors.columns, map(float, coefficients[1:]))),
            "r_squared":r2, "observations":len(data)}
