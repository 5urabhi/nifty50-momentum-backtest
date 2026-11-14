# QuantLab Model Laboratory — Mathematical & API Reference

> **Scope:** 26 registered mathematical models routed to existing Python implementations, presented through one React family/subtab UI. Algorithms are executable only under their declared evidence requirements. This catalog is descriptive, not evidence of out-of-sample predictive performance.

## Model-family map

| Family | Runnable model IDs | Output / interpretation |
|---|---|---|
| Stochastic Processes | `gbm`, `ou`, `heston`, `merton` | Seeded fan charts. No historical calibration. Heston full-truncation Euler is approximate. |
| Volatility & Econometrics | `garch`, `pca`, `covariance`, `rolling_vol` | Observed returns, PCA loadings, fitted conditional volatility, strict-prior-window forecast scores. |
| Derivatives & Options | `black_scholes`, `binomial`, `implied_vol`, `mc_option` | Theoretical prices, Greeks, convergence and user-supplied premium implied-vol solver; not exchange quotes. |
| Portfolio Optimization | `min_variance`, `risk_parity`, `max_diversification`, `cvar`, `black_litterman`, `efficient_frontier` | Sample covariance, fully invested long-only weights / exposures / constrained frontier. In-sample. |
| Tail Risk & Inference | `historical_tail`, `gaussian_tail`, `student_t_tail`, `evt`, `newey_west`, `bootstrap_sharpe` | Empirical, parametric, tail and inference estimators; documented sample and distribution assumptions. |
| 3D Visual Laboratory | `option_surface`, `risk_surface` | Interactive computed BSM grid or correlation stress with observed marginal volatilities. |

## Theoretical and simulated models

### Geometric Brownian Motion — `gbm`

`dS/S = μdt + σdW`. The exact discretization produces seeded lognormal paths. Plot: 5th/median/95th percentiles, horizon and volatility-controlled. **Not calibrated or a prediction**.

### Ornstein–Uhlenbeck — `ou`

`dX = κ(θ−X)dt + σdW`. Exact Gaussian transition for a discretely sampled mean-reverting process. Long-run mean θ and κ are assumed parameters. Output: seeded percentile fan.

### Heston — `heston`

`dS/S=(r−q)dt+√v dW₁`, `dv=κ(θ−v)dt+ξ√v dW₂`, `Corr(dW₁,dW₂)=ρ`. Simulates spot and variance using *full-truncation Euler*. This is a mathematical path simulator with discretization bias and **no empirical Heston calibration or option-surface calibration**.

### Merton Jump Diffusion — `merton`

Jump times follow a Poisson process, with normally distributed log-jump magnitudes. The simulator compensates the physical drift. Jump rate, mean and dispersion are explicit user assumptions.

### Black–Scholes–Merton — `black_scholes`

European call/put closed form with continuous dividend yield. The Python response contains price, delta, gamma, vega, theta and rho. Greeks are reported according to native derivative conventions (vega and rho per 1.0 change, theta per year). Graph: option value versus spot.

### Cox–Ross–Rubinstein tree — `binomial`

European or American option pricing with risk-neutral binomial transitions. Plots tree-step convergence, but different exercise regimes need not equal European BSM.

### Implied volatility — `implied_vol`

Root-finds BSM volatility by Brent's method from a **user-supplied** option premium. It rejects premiums beyond strict European no-arbitrage bounds; no Dhan live premium is requested.

### Antithetic Monte Carlo option — `mc_option`

Risk-neutral terminal lognormal simulation, antithetic variates, 95% Monte Carlo sampling CI, theoretical BSM comparison. Uncertainty is **numerical** simulation uncertainty, not predictive risk.

### 3D option price surface — `option_surface`

BSM evaluated on an explicitly theoretical grid over spot and volatility. Visualization supports drag/keyboard rotation and zoom. It is **not an option chain**.

## Observed historical models

**Data selection rule.** The model API loads `daily_prices.csv` where present, otherwise `prices.csv` (monthly). Only securities meeting the requested minimum observation count enter the eligible set. Securities are ordered by non-missing count (descending), tie by symbol, then the top user-requested count is selected. All returns are computed with `pct_change(fill_method=None)` and common dates are intersected with `dropna()`—**no price forward filling**. This is in-sample completeness selection, not a point-in-time investable stock selection or out-of-sample backtest.

### Gaussian GARCH(1,1) — `garch`

`hₜ=ω+αε²ₜ₋₁+βhₜ₋₁`. Mean-adjusted observed decimal returns, constrained Gaussian MLE, 60+ common returns. Output: ω, α, β, persistence, next-period variance and in-sample fitted volatility. Nonconvergence fails with an explicit error.

### Principal Components — `pca`

PCA on standardized common returns. Outputs explained variance ratios, loadings, PC1 vs PC2 observed scores. Training and reporting occur on the same selected sample; not out-of-sample signal validation.

### Covariance estimators — `covariance`

Annualized **sample**, fixed-intensity **diagonal shrinkage**, and **EWMA** estimators are compared on the same sample. The fixed shrinkage is not Ledoit–Wolf and should not be labeled as such. Outputs volatilities and a correlation heatmap.

### Walk-forward variance forecasts — `rolling_vol`

Strict prior-window sample and EWMA variance forecasts, evaluated on later dates. Uses noisy squared next-return proxy, QLIKE and variance MSE. The GARCH-at-every-window option is intentionally not included in this fast UI model; it remains an optional Python validation routine and must report nonconverged fits.

### Minimum variance — `min_variance`

Long-only constrained quadratic program, fully invested `sum(w)=1` with `0≤w_i≤cap`. Sample annualized covariance and mean, in-sample descriptive; portfolio weights and annualized risk.

### Equal risk contribution — `risk_parity`

Numerical approximation of `w_i(Σw)_i≈(wᵀΣw)/N` subject to a weight cap. Solver may produce approximate, not exact, risk parity under constraints. Outputs weights and Euler risk contributions.

### Maximum diversification — `max_diversification`

Maximize `sum(w_i σ_i)/sqrt(wᵀΣw)`. Uses observed covariance, no return prediction.

### Historical CVaR LP — `cvar`

Rockafellar–Uryasev optimization over observed return scenarios. Returns in-sample minimizing allocation, historical optimized tail-risk objective and scenario count, *not* an audited regulatory Expected Shortfall forecast.

### Black–Litterman — `black_litterman`

Normal-normal posterior with prior `π = δ Σ w_b` and posterior `μ_post=π+τΣPᵀ(PτΣPᵀ+Ω)⁻¹(Q−Pπ)`. The UI explicitly uses **an equal-weight illustrative benchmark** and a **hypothetical annual view spread** between the first two selected assets. The resulting posterior is an explanatory calculation, **not evidence of market equilibrium or alpha**.

### Efficient frontier — `efficient_frontier`

Minimum variance at feasible target returns with weight caps. Uses sample estimates; frontier is sensitive to mean error and not evidence of future performance.

### Historical VaR/tail mean — `historical_tail`

Quantile of observed one-period loss distribution and mean of losses at/above quantile. Loss sign convention is positive. This empirical tail-mean convention can differ from regulatory ES.

### Gaussian VaR/ES — `gaussian_tail`

Normal approximation, `VaRα=-μ+σ Φ⁻¹(α)` and corresponding analytic ES, with observed sample moments.

### Student-t VaR/ES — `student_t_tail`

Student-t model with **user-assumed degrees of freedom**. Scale is matched to observed variance (requires df>2), not estimated by Student-t likelihood. Shows parametric tail risk under a different assumption.

### EVT Peaks Over Threshold — `evt`

GPD tail fit at an assumed quantile, with at least 180 common returns required at the workbench and at least 20 observed exceedances required by the underlying fit. Very sensitive to threshold choice and sample dependence.

### Newey–West — `newey_west`

Heteroskedasticity/autocorrelation-consistent mean z statistic and asymptotic two-sided normal p-value. Small samples or dependence can still invalidate asymptotic approximations.

### Circular moving-block bootstrap — `bootstrap_sharpe`

Seeded bootstrap Sharpe confidence interval (1,000 replications), block length chosen by the user, assumes approximately stationary returns. This is not multiple-hypothesis-corrected.

### 3D correlation stress — `risk_surface`

Two selected securities contribute their **observed** annualized marginal volatilities. The x-axis varies weight and the y-axis **hypothetical** correlation from −0.95 to +0.95; the z-axis shows annualized portfolio volatility. Only marginal volatilities are observed; do not mislabel stressed correlations as historical data.

## Model readiness policy

- Theoretical or seeded simulations: no historical dataset is required.
- Most historical fits: **60+ common observed returns**. PCA uses 30+; EVT uses 180+ plus exceedance constraints. Walk-forward variance evaluation needs its training window **plus at least 12 holdout returns**.
- Observed return frequency is declared as daily (252/year) or monthly (12/year). The legacy index backtester continues to run on monthly returns; this model lab can use the **daily series** if available.
- Every numerical response states model, exact validated parameters, evidence type, source dataset, frequency, number of common observations, selected assets and limitations. A successful model run is also archived under Git-ignored \`results/model_laboratory/\` with a SHA-256 digest of the observed source file, and can be reopened from **Saved model runs**.
- Input values are constrained server-side; unsupported model IDs, out-of-bound parameters, missing datasets and inadequate samples fail explicitly.
- Model Lab has **no order-writing routes** and does not request Dhan network data during a model run.

## API

```text
GET  /api/lab/catalog
GET  /api/lab/readiness?dataset_id=<id>
POST /api/lab/run
GET  /api/lab/runs
GET  /api/lab/runs/{run_id}
```

For the valid model ID `gbm`, a local call would look like:

```bash
curl -fsS http://127.0.0.1:8765/api/lab/catalog | python3 -m json.tool
curl -fsS -X POST http://127.0.0.1:8765/api/lab/run \
  -H 'Content-Type: application/json' \
  -d '{"model_id":"gbm","params":{"seed":2026,"paths":100,"steps":100}}' \
  | python3 -m json.tool
```

For a historical model include the dataset `"dataset_id":"dhan_batch_<your id>"` (use the actual ID shown in Data Manager). No token or brokerage identity belongs in this request.

## Not implemented / never claim

Random Forest, XGBoost, LSTM, PPO, SAC, a historical order-book replay engine, continuous retraining, broker order execution and audited out-of-sample alpha are **NOT** parts of this model registry. Those require a separate versioned feature, validated training protocol and test evidence.

See `docs/QUANTLAB_USER_GUIDE.md` and `docs/QUANTLAB_REPRODUCIBILITY.md`.


## Complete model workflows: observed prices vs assumptions vs option quotes

The original theoretical and seeded stochastic models were not placeholders:
they compute legitimate analytical/numerical examples. Their labels describe
their **evidence type**, not an implementation percentage. A simulated curve
never becomes historical data because parameters are fitted to prices.

### Two routes on each applicable model

Choose **Model Laboratory → select family → select model**.
A paired selector now offers the assumed-parameter original and an observed-data
version where a genuine estimator or quoted market input is mathematically
appropriate. Both are fully runnable once their particular inputs are present.

| Model | Market-data route | Original provider input | Scope |
| --- | --- | --- | --- |
| GBM | GBM historical fit | Original NIFTY TRI return series or named Dhan stock | Drift, volatility; 80/20 chronology; seeded paths |
| OU | OU historical volatility fit | 90+ Dhan daily stock returns | AR(1) mean reversion of log 20-session realized volatility; test diagnostics |
| Merton | Merton historical jump proxy | 120+ Dhan daily returns or historical NIFTY TRI | 3-MAD tail-event frequency + diffusion proxy, 80/20; synthetic scenarios |
| Heston | Historical variance proxy | 252+ daily stock returns | Realized variance AR(1), shock correlation/vol-of-vol proxies, held-out variance comparison; **not** risk-neutral options calibration |
| Black–Scholes | Observed quote BSM | Original provider bid/ask + spot/strike/exact expiry | Midpoint-implied vol and theoretical Greeks/pricing |
| Binomial | Observed quote CRR | Same exact option quote | Theoretical European/American exercise tree; American IV proxy caveat |
| Implied volatility | Original bid/ask IV inversion | Same exact option quote | Bid/ask/mid BSM inversions with explicit yield/rate assumptions |
| Antithetic Monte Carlo | Quote-anchored MC | Same exact option quote | Numerically sampled option payoffs and MC standard errors; no simulated 'market quotes' |
| 3D option surface | Quote-anchored BSM 3D | Same exact option quote | What-if surface around observed quote IV; **not** market smile calibration |

All other portfolio/risk/econometric models already read the original
historical returns. Their outputs remain in-sample unless a model's methodology
explicitly declares time-respecting walk-forward or an isolated test.

### Import actual option quotes once, reuse across models

For any "Observed Market Quote" model, select an existing research dataset.
Inside **Experiment setup → Original option quote snapshots** choose
**Download blank CSV template** and populate it using your permitted original
option-chain/quote export from Dhan, NSE or another provider. Required columns:

`captured_at,provider,underlying,underlying_spot,expiry_at,strike,option_type,bid,ask`

Both timestamps must contain an explicit UTC offset. Example formatting:
`2026-11-14T15:25:00+05:30` and `2026-12-31T15:30:00+05:30`.
`option_type` is `call` or `put`. The quote importer accepts an original
CSV with one to 300 different contracts. It validates timestamp order,
bid ≤ ask, positive prices, strike and spot, and original contract identity.
It stores source-checked raw quotes in local ignored `data/model_option_quotes/`,
returns a new immutable quote snapshot ID, and never uploads vendor data to
GitHub. If the original source changes, model calculations fail closed.
No API keys appear in report artifacts.

Select a saved contract under **Quote** and click **Run selected model**.
The backend automatically derives the observed quote midpoint, precise
time-to-expiry and one-contract European BSM implied volatility. Risk-free
rate and continuous dividend yield remain explicitly **user assumptions**,
not silently downloaded rates. If the observed quote violates selected BSM
European no-arbitrage constraints, the model displays a useful error rather
than inventing an implied volatility. Old quotes remain historical snapshots,
not executable market fills.

**Important:** A single strike/maturity quote cannot calibrate Heston's
full risk-neutral volatility surface or a term structure of implied
volatilities. That requires an option chain with several strikes and
expiries, plus appropriate rates, dividends and exercise/contract conventions.
QuantLab does **not** call that "completed market calibration" just because
it has a stochastic Heston simulator and a rolling variance proxy.

### Research honesty and no extra vendor approvals

Dhan is the intended primary source of individual cash-equity historical
candles. Checking that a quote matches its timestamps, that a benchmark is
TRI rather than price-only, or that a model uses enough consecutive
observations is a numerical/data-contract check, **not distrust of the
broker**. NSE Indices TRI is needed when dividend-inclusive NIFTY benchmark
returns are the model target. Quote-source evidence is accepted from the
user's authorized quote export without demanding another vendor account.

The interface separates:
- **Runnable mathematics** — theoretical/seeded model needs parameter inputs;
- **Observed-source ready** — data-backed fitting has required observed history;
- **Observed-quote ready** — quote-anchored valuation has a real dated contract;
- **Independently audited** — much stronger third-party source, rights and
  publication-methodology validation (not automatically claimed).

No broker orders are ever placed. No provider-specific options API entitlements
are assumed when using the CSV quote import. Importing source quote snapshots
does not certify trade execution, liquidity, forecast performance or
third-party review.

Regression checks:
`python -m unittest tests.test_model_market_workflows tests.test_gbm_historical_calibration -v`.

### All-model readiness, not a misleading single Ready badge

Model Laboratory includes a **What can run with the selected data?** panel,
populated from one local Python dataset audit. It identifies per-model:
**Math runnable**, **Historical source available**, **Quoted-market source
available**, or **Needs inputs**, and supplies the next concrete action.
The counts are calculated from actual saved local files; they are not fixed
UI metrics or a blanket statement that the model is publication certified.
For individual model runs, source availability is checked again with its
exact ticker, option contract and parameters.

API: `GET /api/lab/model-readiness?dataset_id=<saved-id>`.
The panel never submits live orders or assumes that source sufficiency
guarantees optimizer convergence or empirical predictive power.

### Automatic read-only Dhan option-chain capture

CSV import remains a fallback. **Model Laboratory → observed quote model →
Automatic current option chain · Dhan** now supports a single-click read-only
capture of NIFTY 50 or BANK NIFTY options using the existing local
`DHAN_ACCESS_TOKEN`. The server uses `DHAN_CLIENT_ID` in the ignored
`.env` when configured, or fetches it *server-side* from the Dhan profile.
No token or client identifier is sent to the React browser.

The backend calls ONLY `/v2/optionchain/expirylist` and
`/v2/optionchain`, selects the nearest nonexpired date, observes Dhan's
one-unique-request-per-three-seconds limit, records current index LTP,
original best bid/ask and returned option strikes, and persists a
versioned local source-checksummed provider JSON and normalized contract
CSV. It selects positive, noncrossed quotes closest to index spot; it never
places orders, invents option premiums, or sends credentials to reports.

**Timing caveat:** Dhan's option-chain response documents an expiry
**date**, not an exact expiry instant. QuantLab assumes the regular NSE
15:30 Asia/Kolkata session close for modeled tenor and marks this explicit
assumption in the original quote manifest. The quote capture time is
the workstation's local clock, not an exchange-signed trade timestamp.
Actual exchange holidays, early closes, option exercises and contract
settlement details require separate source checks for high-precision
risk/pricing. Captured quotes may become stale almost immediately.

A Dhan token or data plan without option-chain entitlements receives an
actionable sanitized HTTP error. In that case, users can upload an original
authorized option-quote CSV instead. Historical expired-option candles
are a distinct source/API and are NOT substituted for current bid/ask
quotes. Original option-chain source is never committed to GitHub.

CI includes mocked HTTP response tests; it must never make a live Dhan
request using test credentials.

**Source-label protection:** A synthetic fixture may execute the same model
math as observed Dhan data, but **must not be counted as a historical-source
ready model** in the readiness matrix. The all-model overview marks it
`synthetic_fixture_only`, recommends switching to observed input, and
does not treat generated prices as empirical source evidence.
