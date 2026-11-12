# QuantLab — Research Reproducibility & Acceptance Checklist

**Project:** Multi-Factor Equity Index Construction, Stochastic Modeling & Quantitative Risk Research  
**Audience:** Quantitative research hiring teams, interviewers, reviewers, and future project contributors.

## Scope and evidence classes

This project has three distinct computational paths. Never confuse their claims.

1. **Historical factor backtest:** point-in-time selection with prepared market data, factor formation, rebalancing and costs. Supports descriptive, sample-specific results only until benchmark and corporate-action adjustments are externally verified.
2. **Observed mathematical fits:** sample covariance, PCA, GARCH, statistical estimators, long-only optimizers and tail metrics. The Model Laboratory identifies the exact price sample, frequency, selected assets and observation count. In-sample fits are NOT out-of-sample evidence.
3. **Theoretical/synthetic calculations:** BSM/CRR/Monte Carlo and GBM/OU/Heston/Merton paths, with finite parameter bounds and reproducible seeds where relevant. Do not describe these as calibrated predictions.

## Reproduce the workstation

```bash
cd "$HOME/Desktop/codes/nifty50-momentum-backtest/nifty50-momentum-backtest"
git switch feature/quantlab-model-laboratory-and-guide-20261113
git pull --ff-only origin feature/quantlab-model-laboratory-and-guide-20261113
python -m unittest discover -s tests -v
npm run build
bash run.sh
```

No external brokerage credentials are necessary for synthetic or theoretical model tests; do not include network requests in offline regression tests. Runtime API is localhost `127.0.0.1:8765`; UI is `127.0.0.1:5173`. Treat `.env`, cached customer data, and broker identifiers as local secrets.

## Dataset acceptance gates

- [ ] Every downloaded instrument matches its exact Dhan Security ID and exchange segment.
- [ ] Raw minute candle cache has a cryptographic checksum and source timestamp.
- [ ] Source coverage date windows match the requested inclusive/exclusive range.
- [ ] Trading sessions checked against exchange calendar; no duplicate timestamps.
- [ ] Intraday candles converted using Asia/Kolkata trading dates; no UTC session shift.
- [ ] Daily OHLCV uses first observed open, max observed high, min observed low, last observed close, summed volume.
- [ ] Incomplete/missing trading sessions are reported, not filled with a plausible price.
- [ ] Dated NIFTY/BANK NIFTY constituents reconstructed from source notices with no use of current membership for past dates.
- [ ] Renamed/delisted tickers reconciled with historical identity evidence.
- [ ] Month-end marks correspond to last observed session, not a future quote.
- [ ] Spot **price index** benchmark explicitly labeled `PRICE INDEX (not TRI)`.
- [ ] Independently sourced **TRI** and split/dividend-adjusted constituent returns verified **before a total-return performance claim**.
- [ ] Point-in-time fundamentals use the first public availability date, not filing period end.
- [ ] Exchange/tax fees, spread, slippage and realistic execution timing included in claimed tradable returns.

**Files complete ≠ scientifically validated.** Completion means structural inputs are present and computation can proceed; it is not an audit certificate.

## Model validation gates

- [ ] Confirm input mode (theoretical, synthetic, observed).
- [ ] Enforce parameter bounds, finite outputs, and deterministic seed reproducibility.
- [ ] Check common returns sample after `dropna()`; do not fill missing stock prices.
- [ ] Record frequency and annualization factor (252 for daily, 12 for monthly).
- [ ] For covariance/PCA/GARCH/risk, report in-sample estimation versus strict holdout.
- [ ] For portfolio optimizers, verify `sum(weights)=1`, long-only and max caps.
- [ ] For GARCH, reject optimizer nonconvergence and unstable series.
- [ ] For EVT, check tail exceedance count and threshold sensitivity.
- [ ] For options, disclose volatility, rate, dividend, exercise assumptions.
- [ ] For Heston paths, disclose discretization approximation and calibration status.
- [ ] For 3D surfaces, label assumed axes versus measured axes.
- [ ] For stochastic simulations, verify percentile monotonicity and reproducibility.
- [ ] For model comparison, use matched input windows and reasonable observation counts.

## Experiment acceptance gates

- [ ] Freeze a training window, validation window and untouched final holdout.
- [ ] Record all experiment parameters: factors, weights, lag, rebalance, transaction costs, top N, portfolio constraints.
- [ ] Test against benchmark of matched return basis. NIFTY price index and TRI are distinct.
- [ ] Show sample count, CAGR if defined, max drawdown if defined, turnover and tracking risk.
- [ ] Do not treat NaN/blank performance metrics as zero; explain which sample-size constraint removed them.
- [ ] Apply multiple-test controls when screening multiple factor configurations.
- [ ] Check parameter robustness without selecting the best result retrospectively on the final test.
- [ ] Use walk-forward retraining where time-series calibration is claimed.

## Deliverable provenance

For each resume-visible experiment, retain:

```text
research_case/
  README.md                 # question, hypothesis, methodology, data caveats
  source_provenance.json    # original cache hashes, membership source versions
  parameters.json           # exact model/experiment settings and random seed
  environment.txt           # Python/node versions, dependency versions, git SHA
  model_result.json         # generated Model Lab numerical result / chart values
  metrics.csv               # key sample metrics, with undefined values disclosed
  figures/                  # optional SVG/PDF snapshots, exact axis labels
  limitations.md            # missing TRI, short sample, splits, costs, OOS status
```

Model Lab can export JSON/CSV. The saved Index Research run artifacts remain in `results/workstation_runs/`. Some manuscript-ready figures and an integrated comparison report still require deliberate human interpretation; generating a figure is not itself a research result.

## Suggested defensible resume wording

> Designed a local React/TypeScript + FastAPI/Python quantitative research workstation integrating historically reconstructed NIFTY index membership, resumable DhanHQ minute-candle ingestion, monthly factor portfolio backtesting, constrained portfolio optimization, stochastic process simulation, option-pricing analytics and observed-risk model diagnostics. Implemented bounded model APIs, source provenance, diagnostic visualization and regression tests.

Do **not** claim independently audited alpha, production brokerage execution, live market forecasting, historical level-20 depth replay, or completed ML/RL training unless separately proven.

## Architecture & security

```text
React/Vite localhost UI
  ├── Dhan Data Manager -> validated local Python API -> Dhan READ-ONLY prices
  ├── Index Research -> index_research backtest -> local results
  ├── Model Laboratory -> model registry / gated runner -> numerical results and charts
  └── User Guide -> allowlisted repository Markdown on local API

FastAPI 127.0.0.1:8765
  ├── Host + Origin localhost guard
  ├── model_registry.py (single catalog, bounds, assumptions)
  ├── model_lab.py (execution, finite/sufficient data gates)
  └── service.py + index_research/ (data and numerical mathematics)

Local (Git-ignored) data and .env credentials
```

Review input limits before adding heavier models; future ML/RL modules must be built behind independent training/validation engines rather than passing off historical backtests as live-tradable decisions.
