# Mathematical Research Code: Acceptance Contract

Status: **source-code completion pass delivered, local runtime verification pending**.

This page defines "mathematical code complete" for the equity-index research
scope. It does not claim all of mathematical finance, calibration on real market
data, or numeric correctness before a passing run.

## Research models in scope

| Discipline | Implemented code | Analytical/acceptance evidence |
| --- | --- | --- |
| Cross-sectional equity factors | `factors.py`, `diagnostics.py`, `statistical_inference.py` | Rank IC, temporal score availability, factor-spread diagnostics |
| Covariance & portfolio optimization | `math_models.py`, `portfolio_theory.py` | Closed-form diagonal minimum-variance solution, Euler risk shares, risk-parity budget feasibility |
| Benchmark-relative equity index methods | `index.py`, `experiment.py`, `comparison.py` | Drift-aware turnover and net/gross return invariants |
| Stochastic processes | `math_models.py`, `advanced_models.py`, `derivatives.py` | GBM and OU expectations, deterministic jump-diffusion limit |
| Option pricing | `math_models.py`, `derivatives.py` | Put-call parity, delta parity, finite-difference Greeks, lattice and Monte Carlo convergence |
| Risk & extreme values | `tail_risk.py` | Distributional loss VaR/ES inequalities and scenario validity |
| Asset pricing/inference | `statistical_inference.py` | OLS/HAC standard errors, chronological folds, FDR correction, block bootstrap |
| Robust out-of-sample comparisons | `model_validation.py` | Only prior returns fit covariance/variance; holdout dates shared across forecast models |
| Risk budgeting | `portfolio_theory.py` | Exact budget checks, solver raises when no feasible risk-parity solution |
| Black-Litterman/CVaR | `portfolio_extensions.py` | Posterior equals equilibrium under zero residual view, CVaR LP constraints |
| Charts | `visual_validation.py`, `dashboard/pages/10_Visual_Validation.py` | Model diagnostics and interactive 2D/3D plots |
| Mathematical acceptance report | `scripts/verify_mathematics.py` | Run independent local tests; emit JSON, log, and standalone HTML evidence |

## Material corrections during this completion pass

1. **Covariance portfolio drift:** the rolling covariance experiment now
   evolves buy-and-hold weights between rebalances. At rebalance it trades
   against drifted holdings; gross returns, turnover and configurable cost
   sensitivity are separately exposed. Earlier static weights every period
   could distort empirical comparisons.
2. **Risk parity accuracy:** solver convergence alone is not treated as proof
   that target variance risk budgets were achieved. Numerical residual checks
   now block falsely labeled risk-parity portfolios.
3. **Forecast model comparability:** rolling Gaussian GARCH(1,1) is available
   as an optional one-step-ahead estimator using strictly prior data. Failed
   numerical windows are **missing**, never silently replaced. QLIKE/MSE
   model comparisons default to an identical holdout sample and report
   fit coverage. A comparison with fewer than 12 common windows is blocked.
4. **Numerical input hygiene:** stochastic paths and Gaussian covariance
   stress calculations reject nonfinite parameters/weights.
5. **Independent analytical acceptance:** a new `tests/test_math_acceptance.py`
   checks options Greeks via central differences, binomial/BSM agreement,
   minimum variance against inverse-variance closed form, Monte Carlo and
   stochastic process moments, risk-budget feasibility and turnover drift.

## Run locally

```bash
git switch research/multi-factor-equity-index
bash scripts/run_local.sh setup
bash scripts/run_local.sh math
```

Or:

```bash
python scripts/verify_mathematics.py --output-dir results/math_acceptance
```

The acceptance command runs four deterministic test files, exits nonzero
on failure, and produces:
- `results/math_acceptance/mathematics_acceptance.html`
- `results/math_acceptance/mathematics_acceptance.json`
- One detailed `.log` per suite.

The broader end-to-end project also requires:

```bash
bash scripts/run_local.sh acceptance
bash scripts/run_local.sh dashboard
```

Do not label the mathematics numerically verified until the acceptance command
passes on a pinned local Python environment. Do not label historical model
performance verified until independent point-in-time data, survivorship,
corporate actions, realistic execution and a frozen holdout have been audited.

## Explicitly outside the core scope

A full proprietary MSCI factor model, regulatory ES calculations, full
options-surface calibration (SABR/local-volatility), interest-rate derivatives,
microstructure simulation, exotics, and real-time production execution are not
necessary to complete this **equity-index research** mathematical scope.
They may be future research extensions, not silently claimed delivered.

The code modules are ready for their first full local acceptance run; no
GitHub Actions automation, Vercel deployment or `main` merge is necessary.
