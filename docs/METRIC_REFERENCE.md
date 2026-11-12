# QuantLab Mathematical Metrics and Statistical Interpretation

This is the in-app formula/assumption reference for QuantLab's Python research
workstation. All figures are computed from registered model outputs or observed
local data. **A formula producing a result does not certify the historical
correctness, investability, or predictive significance of that result.**

## Returns, portfolio risk and performance

| Metric | Definition / computation | Interpretation and limitations |
| --- | --- | --- |
| Simple return | r_t = P_t/P_(t−1) − 1 | Requires price adjustment and dividends for true total returns. A Dhan close may not be adjusted. |
| Log return | ln(P_t/P_(t−1)) | Undefined for nonpositive prices. Not additive across separate assets. |
| Cumulative wealth | W_T = 100 × product_t(1+r_t) | Assumes a fully invested self-financing strategy. QuantLab Plot Builder's wealth view ignores dividends and trading costs unless already present in source returns. |
| Annualized return (CAGR) | (W_T/W_0)^(K/n) − 1 | K = returns/year, n = observed periods; not meaningful for extremely short or synthetic samples. |
| Annualized volatility | sqrt(K) × sample standard deviation of r_t | Square-root-of-time annualization presumes a stable enough sampling process; clustered variance violates naive uncertainty assumptions. |
| Sharpe ratio | sqrt(K) × mean(r_t − rf_t)/sd(r_t − rf_t) | Zero-risk-free convention is explicitly labeled in the basic validation metrics. It is not a guarantee of live returns. |
| Sortino ratio | sqrt(K) × mean(r_t − target)/downside deviation | Depends on the threshold and handling of missing/no-negative observations. |
| Max drawdown | minimum_t(W_t/max_{s≤t}W_s − 1) | Historical path statistic; exposure to future drawdowns is not bounded. |
| Tracking error | sqrt(K) × std(strategy − benchmark) | Strategy and benchmark periods, source and return convention must match. |
| Information ratio | sqrt(K) × mean(strategy − benchmark)/std(strategy − benchmark) | Requires investable, aligned benchmark; price-index and TRI mismatch is not comparable. |
| Beta | Cov(asset, benchmark)/Var(benchmark) | Sample beta, not a structural causal coefficient. |
| HHI concentration | sum_i w_i² | Effective holdings = 1/HHI; correlated holdings can still concentrate economic risk. |

## Tail risk

| Metric | Formula | Assumptions |
| --- | --- | --- |
| Historical VaR(alpha) | Quantile_alpha(−r_t) | Estimates a loss threshold at the chosen confidence. A 95% VaR does not bound the remaining 5% losses. |
| Historical Expected Shortfall | Mean(−r_t | −r_t ≥ VaR_alpha) | Sensitive to how few tail events exist. This is a sample estimate, not guaranteed future loss. |
| Gaussian VaR | −mu + sigma × Phi^−1(alpha) | Assumes normal return innovations; underestimates heavy tails if violated. |
| Student-t tail | mu, scale and degrees of freedom; Quantile at alpha | QuantLab's Student-t df may be a **user assumption**, not an estimated best fit. |
| Extreme-value POT/GPD | Fit a generalized Pareto to losses above a fixed high threshold | Unstable with insufficient excess events, changing volatility or look-ahead threshold selection. |
| CVaR optimization | min_w,z z + 1/(N(1−alpha)) × sum_i max(loss_i(w)−z,0) | In-sample scenario LP; doesn't imply an unseen distribution has the same risk. |

## Portfolio optimization and covariance

| Metric | Formula | Interpretation |
| --- | --- | --- |
| Minimum variance | min w^T Sigma w under sum(w)=1, 0≤w≤cap | Optimizer assumes fitted covariance is relevant in the future. |
| Risk contribution | RC_i = w_i (Sigma w)_i | Sum_i RC_i = w^T Sigma w. Divide by variance for contribution fractions. |
| Equal risk contribution | Seek RC_i approximately equal across assets | Depends heavily on covariance estimation and solver convergence. |
| Maximum diversification | sum_i w_i sigma_i / sqrt(w^T Sigma w) | High ratio does not guarantee out-of-sample superior returns. |
| Shrunk covariance | (1−lambda) Sigma_sample + lambda diag(Sigma_sample) | Shrinkage trades estimation variance against model bias. |
| EWMA covariance | Exponentially weighted historical covariance | Recency weighting may underreact to regime changes. |
| Principal components | Eigenvectors of standardized covariance/correlation | In-sample PCA may overfit and does not automatically create tradable factors. |

## Statistical inference and diagnostics

| Metric | Formula | Interpretation |
| --- | --- | --- |
| Jarque–Bera | n × (skewness²/6 + excess_kurtosis²/24) | A nominal chi-square normality check; sensitive to extreme observations. |
| Ljung–Box Q | n(n+2) sum_{k=1..h} rho_k²/(n−k) | Chi-square approximation for return autocorrelation; approximate under heteroskedasticity. |
| ARCH LM | nR² from regressing squared demeaned returns on lagged squares | Suggests variance clustering; depends on chosen lag count. |
| Newey–West standard error | Bartlett-weighted autocovariances, truncated at lag L | Asymptotic HAC uncertainty; does not correct selection on test results. |
| Circular moving-block bootstrap | Resample blocks of consecutive returns, including wrapping around sample end | Preserves short-range dependence approximately; choice of block size and stationarity assumption matter. |
| Holm multiple testing | Sort nominal p-values and multiply by remaining hypothesis count, applying monotonic adjustment | Controls familywise error under valid individual p-values, not bias from cherry-picked experiments. |
| Out-of-sample R² | 1−MSE(test model)/MSE(test training-mean baseline) | Negative values mean the benchmark predicts better; holdout must be strictly later than fitting. |
| Factor proxy beta | OLS coefficient of observed portfolio-return proxy on user-selected return-series proxies | **Not** economically identified investment-factor attribution. Use correctly published factor vintage for formal attribution. |

## Stochastic models and derivative assumptions

| Model | Core equation | Not supported as a trading claim |
| --- | --- | --- |
| Geometric Brownian Motion | dS/S = mu dt + sigma dW | Simulated Brownian paths do not predict observed price paths. |
| Ornstein–Uhlenbeck | dX = kappa(theta−X)dt + sigma dW | Mean reversion is an assumption unless independently estimated and validated. |
| Heston | dS/S = (r−q)dt + sqrt(v)dW1; dv = kappa(theta−v)dt + xi sqrt(v)dW2 | Need correct calibration and discretization analysis; synthetic demo ≠ market fit. |
| Merton jumps | dS/S = (mu−lambda*k)dt + sigma dW + (exp(Y)−1)dN | Jump intensity and size distribution can be hypothetical. |
| Black–Scholes–Merton | Discounted risk-neutral European option payoff under lognormal diffusion | Not valid for arbitrary early exercise, stochastic funding or unhedged execution costs. |
| Binomial CRR | Backward discounted binomial continuation plus early-exercise step where applicable | Numerical convergence is necessary but not evidence of realistic market microstructure. |

## Evidence categories that must not be mixed

1. **Theoretical:** Formulas evaluated from assumed inputs.
2. **Synthetic:** Simulations driven by random seeds, not market observations.
3. **Observed historical:** Prices returned by Dhan or user uploads, subject to adjustment and source-vintage audits.
4. **Chronological OOS:** A model fit on earlier data, evaluated only on later data, but not automatically unbiased selection of universe or benchmark.
5. **Prospective execution:** Recorded quotes, decisions, fills, fees and real availability timestamps; not currently claimed.

An observation buffer of **+20%** is a preferred sample-size target, **not** a valid holdout automatically. Freeze model selection and research protocol separately from the final test.

## Working with QuantLab

Use **Help & Settings → Metric Guide** to inspect concepts. Use **Model Laboratory** for the registered algorithm formulas and bounds. Use **Compare & Visualize → Plot Builder** for graphs and **Research Projects** for notebook reports. Source checksums are recorded to show data lineage, not independent accuracy certification.

Do not place Dhan access tokens in research notes, exports, or bug reports.
