# Quantitative Modeling Laboratory (research branch)

This directory extends the existing Nifty 50 momentum notebook with independently
testable mathematical primitives. **No claim that any model improves returns is
made until a historical, point-in-time, out-of-sample study has been run.**

## Implemented

| Method | Mathematical identity / objective | Validation |
| --- | --- | --- |
| Sample covariance | Sigma = annualization * sample covariance | PSD check |
| Diagonal shrinkage | (1-lambda) Sigma + lambda diag(Sigma) | lambda=1 diagonal |
| EWMA covariance | Weighted centered return outer products | PSD check |
| Minimum variance | min w^T Sigma w, sum(w)=1, 0<=w_i<=cap | Analytic diagonal example |
| Historical VaR and ES | Empirical loss quantile, tail average | ES >= VaR |
| GBM Monte Carlo | dS/S = mu dt + sigma dW | Zero-volatility limit |
| Black-Scholes-Merton | European options with continuous dividend yield | Put-call parity, delta parity |
| Factor regression | OLS excess-return factor model | Known synthetic betas |

## Important interpretation rules

1. The *simple* historical Expected Shortfall here is the mean loss beyond the
   empirical quantile. It is not a regulatory expected-shortfall implementation.
2. The covariance shrinkage intensity is fixed by the analyst, not
   Ledoit-Wolf's estimated optimal intensity.
3. GBM simulations are **hypothetical**; calibration and distribution diagnostics
   are required before using them for financial risk estimates.
4. Black-Scholes applies to theoretical **European** options under its assumptions.
   It is a mathematical demonstration, not an index-methodology performance claim.
5. The unconstrained sample covariance optimizer can be unstable out of sample.
   Use rolling estimation, concentration limits and holdout results.
6. The existing static-universe notebook may have survivorship/selection bias.
   Model results must not inherit the reported 3.34 Sharpe without an audit.
7. Factor regression is descriptive and does not prove causal attribution.
8. The current index backtester uses idealized month-end execution and
   simplified cost/turnover treatment. Do not claim realized investability.

## Roadmap

- First: repair drift-adjusted turnover and execution timing, validate data.
- Next: point-in-time securities and historical factor characteristics.
- Then: rolling and expanding estimation, min-vol and factor-scored indexes,
  tracking-error constrained optimization and comparison against consistent
  total-return benchmarks.
- Subsequently: optional GARCH, PCA and regime diagnostics with tests.
- Finally: research dashboard reading versioned and verified output files
  and PDF methodology/research report. Never hardcode result charts.
