# Quantitative Mathematics Catalog — Full Research Toolkit

**Implementation status:** Code is committed to `research/multi-factor-equity-index`.
**Verification status:** New mathematical modules and dashboard are NOT YET
locally executed or market-calibrated. No GitHub Actions workflows are used.
This is independent research code, not a proprietary risk model or investable index.

## 1. Index research and factor mathematics

| Model / discipline | Implementation | Research use | Critical limitation |
| --- | --- | --- | --- |
| Cross-sectional 12-1 momentum | `factors.py` | Factor signal ranking | Needs historical as-of universe |
| Low-volatility ranking | `factors.py` | Defensive style selection | Rolling volatility is not an expected-return model |
| Value / Quality / Size scores | `factors.py` | Composite multifactor indexes | Requires publisher-dated, definition-audited inputs |
| Cross-sectional z-score composites | `factors.py` | Combine standardized factors | Scores are research approximations |
| Rank IC / forward quantile spreads | `statistical_inference.py` | Factor monotonicity and signal testing | Purely descriptive, spread excludes trading costs |
| Factor exposure neutralization | `portfolio_extensions.py` | Remove linear sector/style exposure | Requires as-of exposure histories |

## 2. Asset pricing and inference

| Model / discipline | Implementation | Mathematical method | Critical limitation |
| --- | --- | --- | --- |
| CAPM market factor | `regression_with_known_factors` | OLS + HAC factor alpha and beta | Real risk-free-adjusted factor series not bundled |
| Fama–French 3-factor | `statistical_inference.py` | MKT-RF, SMB, HML OLS | Does not independently reconstruct factor returns |
| Carhart 4-factor | `statistical_inference.py` | FF3 plus MOM | Requires frequency-aligned factor returns |
| Fama–French 5-factor | `statistical_inference.py` | MKT-RF, SMB, HML, RMW, CMA | Needs appropriate market-specific source |
| FF5 plus momentum | `statistical_inference.py` | Six-factor regression | Not a causal performance attribution model |
| Newey–West HAC | `statistical_inference.py` | Bartlett long-run covariance estimate | Asymptotic normal p-values only |
| Moving-block bootstrap | `statistical_inference.py` | Dependence-aware sampled mean CI | Does not fix model-selection bias |
| Benjamini–Hochberg FDR | `statistical_inference.py` | False discovery rate q-values | Assumptions on test dependence still matter |
| Chronological walk-forward splits | `statistical_inference.py` | Rolling or expanding time folds, embargo | Consumer must freeze parameters outside folds |
| PCA | `advanced_models.py` | Singular value decomposition | Must fit on historical train window |
| OLS attribution | `math_models.py` | Least-squares factor exposures | No automatic robust inference |

## 3. Portfolio construction and optimization

| Model / discipline | Implementation | Objective / formula | Critical limitation |
| --- | --- | --- | --- |
| Markowitz minimum variance | `math_models.py`, `portfolio_theory.py` | min wᵀΣw | Estimation noise, constrained long-only |
| Mean–variance utility | `portfolio_theory.py` | min λ wᵀΣw/2 − μᵀw | Ex-ante expected returns unstable |
| Efficient frontier | `portfolio_theory.py` | min variance s.t. return ≥ target | Ex-ante only; infeasible points excluded |
| Benchmark tracking-error minimization | `portfolio_theory.py` | min (w−b)ᵀΣ(w−b) | Requires benchmark weights/covariance |
| Active mean–variance utility | `portfolio_theory.py` | maximize expected active return − active risk penalty | In-sample optimizer |
| Risk parity | `portfolio_theory.py` | Match variance risk contributions to budgets | Some covariance/budget targets infeasible |
| Maximum diversification | `portfolio_theory.py` | max weighted vol / portfolio vol | Ex-ante and covariance dependent |
| Euler volatility risk contributions | `portfolio_theory.py` | wᵢ(Σw)ᵢ / σₚ | Undefined at zero variance |
| Black–Litterman posterior | `portfolio_extensions.py` | Equilibrium returns + Bayesian normal views | Sensitive to subjective views and confidence |
| Historical CVaR minimization | `portfolio_extensions.py` | Rockafellar–Uryasev linear program | Depends on scenario quality |
| Bounded factor index weighting | `index.py` | Ranking and constrained SLSQP | Not an official index methodology |
| Effective-dated index simulation | `index.py` | Next-period returns, drift-aware turnover | Simplified execution and security events |

## 4. Stochastic processes, volatility and tail risk

| Model / discipline | Implementation | Research use | Critical limitation |
| --- | --- | --- | --- |
| Geometric Brownian Motion | `math_models.py` | Lognormal simulated paths | Unrealistic constant-vol assumption |
| Ornstein–Uhlenbeck | `advanced_models.py` | Mean-reverting process paths | Mean-reversion not guaranteed in prices |
| EWMA volatility/covariance | `math_models.py` | Recency-weighted dependence | Fixed decay parameter |
| Gaussian GARCH(1,1) | `advanced_models.py` | Conditional variance forecasts | Needs calibration/rolling backtest |
| Heston stochastic volatility | `derivatives.py` | Correlated stock/variance evolution | Full-truncation Euler discretization bias |
| Merton jump diffusion | `derivatives.py` | Discontinuous stock-price scenarios | Unknown jump intensity/size in practice |
| Historical VaR and empirical ES | `math_models.py` | Quantile / tail average | Not regulatory ES |
| Gaussian and Student-t VaR/ES | `tail_risk.py` | Parametric tail risk comparison | Distribution choice dominates tails |
| Correlated Gaussian Monte Carlo | `tail_risk.py` | Portfolio-level scenario risk | Does not capture nonlinear dependence |
| Historical shock vectors | `tail_risk.py` | Linear scenario P&L | Not option convexity or second-order feedback |
| Kupiec VaR coverage test | `tail_risk.py` | Exceedance-rate consistency | Unconditional coverage only |
| Peak-over-threshold EVT | `tail_risk.py` | GPD extreme-tail extrapolation | Threshold/sample dependence; exploratory |

## 5. Derivatives pricing and numerical mathematics

| Model / discipline | Implementation | Mathematical method | Critical limitation |
| --- | --- | --- | --- |
| European Black–Scholes–Merton | `math_models.py` | Closed-form lognormal diffusion | Constant volatility |
| Delta/Gamma/Vega/Theta/Rho | `math_models.py` | Analytical option sensitivities | Local model derivatives |
| Implied volatility | `derivatives.py` | Bracketed Brent root solver | Requires arbitrage-consistent European price |
| European/American CRR binomial tree | `derivatives.py` | Risk-neutral recombining lattice | Discretization convergence |
| Antithetic Monte Carlo option pricing | `derivatives.py` | Paired shocks with pair-based SE | Numerical sampling uncertainty |
| Stochastic-volatility/jump paths | `derivatives.py` | Discrete-time SDE simulation | Not calibrated derivatives models |

## What "complete" means here

The code provides a **broad, career-relevant mathematics toolkit**:
factor selection, risk estimation, constrained index construction, statistical
inference, stochastic simulation and options-pricing demos. It is NOT a
complete encyclopedia of mathematical finance. Proprietary models, real
high-frequency execution, pricing of all exotic derivatives, SABR calibration,
full interest-rate term structure, copula dependence models, and production
regulatory risk methods remain deliberately outside the MSCI equity index
research project's core scope.

**Important:** The software's mathematical functions are authored but the
new code has not yet passed local runtime tests. A unit-test file is not
evidence of a passing test. Historical factor returns, constituent membership,
publication-dated fundamentals and official benchmark series are not bundled.

## Local review sequence (when user is ready)

```bash
bash scripts/run_local.sh setup
bash scripts/run_local.sh tests
bash scripts/run_local.sh synthetic
bash scripts/run_local.sh dashboard
```

In Streamlit choose **Advanced Mathematics** for Markowitz/risk parity,
frontier, Black–Litterman, CVaR, distribution-tail comparison, Newey–West
factor regressions and BSM/binomial/Monte Carlo comparisons.

Do not publish numeric performance claims from the static-universe
original notebook or synthetic fixtures. Any resume statistic requires
an independent market data audit and frozen holdout research protocol.


## 6. Rolling out-of-sample mathematical validation

| Tool | Implementation | Mathematical evaluation | Limitation |
| --- | --- | --- | --- |
| Lag-only rolling variance forecasts | `model_validation.py` | Sample and EWMA conditional-variance proxies | GARCH not included in automated comparison |
| QLIKE forecast loss | `model_validation.py` | Mean log forecast variance plus squared return/forecast variance | Squared return is a noisy realized-vol proxy |
| Variance mean squared error | `model_validation.py` | Mean squared error of next-period squared-return proxy | Sensitive to extreme outliers |
| Rolling covariance model portfolios | `model_validation.py` | Equal vs sample/shrinkage/EWMA minimum variance | Frictionless, no delisting or turnover modeling |
| Group-neutral factor spreads | `model_validation.py` | Equal-weight average of within-group high-minus-low spreads | Requires effective-dated group classification |
| Visual rolling validation panel | `dashboard/pages/4_Rolling_Validation.py` | Interactive local upload and model comparisons | Needs historical data and local visual QA |

The model-forecast comparison is **out-of-sample in estimation timing only**:
the full experiment design can still be contaminated by analyst selection
of train-window length or estimator parameters based on visible test returns.
Freeze evaluation choices before publishing.
