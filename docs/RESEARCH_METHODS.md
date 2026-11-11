# Research Methodology and Acceptance Matrix

## Investment research question
Does a rules-based, transparent multi-factor selection and weighting scheme
offer superior **risk-adjusted, benchmark-relative** outcomes under a realistic
turnover budget, without concentrating unintended sector or factor risk?

## Factor specifications (research approximations)
- Momentum: close[t-skip] / close[t-skip-formation] - 1.
- Low volatility: negative trailing realized return standard deviation.
- Value: externally sourced, explicitly defined higher-is-better score;
  publications must be available *before* decision date.
- Quality: externally sourced, explicitly defined higher-is-better score.
- Size: -log(positive historical market capitalization).
- Cross-sectional factor standardization: per-date clipped z-scores of
  eligible stocks. Missing requested factor makes the entire composite
  score unavailable for that stock; no imputation.

These are **not** MSCI proprietary factor definitions.

## Index rules
At scheduled decision dates, select top-N eligible names by composite score,
allocate equal, shifted-factor-score, or inverse-historical-vol weights, and
solve a bounded optimization with an optional sector cap (in Python).
The current Streamlit interface exposes concentration cap and frequency but
does not yet expose effective-dated sector classifications. Sector mapping in
the Python function is user-supplied and needs historical provenance.

Between rebalances, shares/weights are held and drift based on realized
security returns. Trade turnover is absolute difference between target and
**pre-trade drifted** weights. The first deployment from cash is counted.
Trading costs are charged as a fraction of portfolio value on a weight-change
basis. This remains simplified: spread, market impact, lot sizes, taxes,
partial fills and shares outstanding adjustments are not modeled.

Default execution lag is ONE monthly observation, to avoid claiming
contemporaneous close execution with a close-derived decision signal.
Same-close mode is available for sensitivity studies but marked idealized.

## Test protocol
- Distinct development, validation and final-test windows with chronological
  splits. Inputs/weights and factors are fitted as-of their decision date.
- Report full configuration and SHA-256 CSV evidence fingerprints.
- Report benchmark return convention, annualized turnover, tracking error,
  active arithmetic return, CAGR and information ratio.
- Independent final holdout should be frozen **before** running experiments;
  code cannot prove that users did not tune against the holdout.
- Exploratory models (OLS/PCA/GARCH/covariance) should be estimated only on
  training windows in any predictive comparison.
- Historical VaR uses an empirical tail average, not regulatory expected
  shortfall. GBM and OU paths are hypothetical model outputs.
- Compare factor IC, portfolio concentration, turnover and execution delay
  sensitivity; avoid selecting models solely by optimized Sharpe.

## Current acceptance states
| Deliverable | Code status | Real-data validation |
| --- | --- | --- |
| Momentum, low vol, Value, Quality, Size | Implemented | NOT YET VALIDATED |
| Point-in-time membership parser | Implemented | Source evidence missing |
| Publication-aware fundamental lookup | Implemented | Source evidence missing |
| Bounded stock weighting | Implemented | NOT YET VALIDATED |
| Drift-aware monthly simulator | Implemented | NOT YET VALIDATED |
| Benchmark comparison and holdout labels | Implemented | NOT YET VALIDATED |
| Covariance/Markowitz/Black-Scholes/GBM/OU/PCA/GARCH | Implemented | Local testing pending |
| Research HTML/CSV/JSON report | Implemented | Local run pending |
| Streamlit UI | Implemented | Local visual verification pending |
| Static Vercel presentation export | Implemented | No deployment |
| Real financial data and licensed benchmark | **NOT PROVIDED** | Blocked |
| Credible resume return statistics | **BLOCKED** | Requires audited tests |

The code is made available for local review; a *completed empirical research
study* cannot be claimed until historical evidence and experiments are supplied.


## Extended implementation scope

The index-construction Python routine accepts date-specific sector matrices
from `sectors.csv` and enforces sector allocation constraints at each
reconstitution. Missing historical classification for selected companies
blocks constrained construction. Between rebalances exposures can drift.

The new research analytics produce issuer concentration histories, rolling
tracking error, relative wealth, risk/turnover metrics, and fixed-trade-path
transaction-cost sensitivity. The dashboard also runs controlled side-by-side
momentum equal-weight, momentum score-weight, low-volatility equal-weight and
the user-selected composite under matched historical dates and costs.

The generated PDF research paper uses the experiment manifest, split
statistics, factor weights, configuration and SHA-256 dataset fingerprints.
It is explicitly an **unverified draft** until historical inputs and code are
checked locally. No formal statistical significance or real-market superiority
is inferred from template results.

**Known limitations retained:** Data-vendor security and dividend-adjustment
quality, missing corporate actions, regulatory index maintenance rules,
delistings, implementation price/impact, source-history licensing, historical
sector-vintage quality and a truly frozen final holdout cannot be proven by
source code alone. Empirical conclusions remain blocked.


## Full integration additions

- Historical sectors are loaded from effective-date `sectors.csv`,
  represented as an as-of date-by-security matrix, and passed into the
  bounded selection optimizer. Missing classifications are not fabricated.
- Computed concentration (HHI/effective issuers), historical sector
  allocations, rolling benchmark-relative metrics, and cost sensitivity
  are exported with the run.
- Independent single-factor rank IC and holding-period factor exposures
  are calculated using historical signals and exposed in the Factor Laboratory.
- Controlled momentum, low-volatility, and configured composite variants
  share input dates, benchmarking rules and implementation-cost assumptions.
  They are **not** parameter-selection-adjusted research evidence.
- The local Streamlit UI includes executive overview, Factor Laboratory,
  Index Construction, Index Comparisons, Risk/Turnover, mathematical
  model demonstrations, rolling validation, and PDF/HTML report export.
- `scripts/local_acceptance.py` defines one user-triggered local run with
  synthetic data, a model test suite and dashboard smoke tests.
- The HTML/PDF report is a draft based on calculated artifacts. There is
  no independent validation of source data or empirical findings.
