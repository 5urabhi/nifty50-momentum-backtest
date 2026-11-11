# Code and Validation Status

Updated: 2026-11-11. Scope: `research/multi-factor-equity-index`.

**Interpretation:** "Implemented" means source code exists in this branch, **not**
that it has been executed locally or validated against historical market data.
No GitHub Actions workflow is configured. Tests are intended for local execution
after the complete implementation phase.

| Area / module | Code | Local runtime QA | Research / data QA | Notes |
| --- | --- | --- | --- | --- |
| Original momentum notebook (`main.ipynb`) | Preserved (legacy) | Not repeated | **Unaudited** | Original Sharpe/return claims must not be copied into resume |
| Research price/membership reader (`data.py`) | Implemented | Pending | **Source evidence missing** | Requires effective-dated historical constituents |
| Fundamental publication-date reader (`data.py`) | Implemented | Pending | **Source evidence missing** | Vendor definition/revisions must be verified |
| Momentum signal (`core.py`, `factors.py`) | Implemented | Pending | Pending | Uses lagged return history |
| Low-volatility factor (`factors.py`) | Implemented | Pending | Pending | Trailing historical volatility |
| Value / Quality / Size (`factors.py`) | Implemented | Pending | **Inputs missing** | No fabricated historical fundamental scores |
| Composite scores and rank IC (`factors.py`) | Implemented | Pending | Pending | Descriptive, not forecast evidence |
| Constituent rules and weighting (`index.py`) | Implemented | Pending | Pending | Caps, selection, monthly reconstitution |
| Drift-aware index backtest (`index.py`) | Implemented | Pending | Pending | Execution/cash/turnover approximations require QA |
| Legacy baseline backtester (`core.py`) | Preserved | Pending | Not release-grade | Superseded by drift-aware research simulator |
| Benchmark metrics and holdout periods (`experiment.py`) | Implemented | Pending | Pending | Requires compatible benchmark series |
| Hashes and experiment manifests (`experiment.py`) | Implemented | Pending | Pending | CSV provenance is still user-declared |
| Offline HTML reports (`reports.py`) | Implemented | Pending | Pending | Published output must have audited inputs |
| Local CLI (`cli.py`) | Implemented | Pending | N/A | Runs without GitHub automation |
| Synthetic fixtures (`fixtures.py`) | Implemented | Pending | Clearly synthetic | For debugging; never claim historic returns |
| Legacy CSV adapter (`prepare_legacy_demo.py`) | Implemented | Pending | **Biased by construction** | Complete-case survivors and artificial benchmark |
| Sample/shrinkage/EWMA covariance (`math_models.py`) | Implemented | Pending | Pending | Shrinkage is fixed intensity, not Ledoit-Wolf |
| Min-variance optimization (`math_models.py`) | Implemented | Pending | Pending | Long-only constrained quadratic objective |
| Historical VaR / empirical ES (`math_models.py`) | Implemented | Pending | Pending | Not a regulatory ES calculation |
| GBM and BSM Greeks (`math_models.py`) | Implemented | Pending | Model assumptions only | Demonstration, not alpha evidence |
| Factor regression (`math_models.py`) | Implemented | Pending | Pending | OLS descriptive exposure model |
| PCA / OU / GARCH (`advanced_models.py`) | Implemented | Pending | Pending | Out-of-sample diagnostics required |
| Quant math dashboard (`dashboard/app.py`) | Implemented | **Visual QA pending** | N/A | Uploaded data or clearly synthetic model paths |
| Index dashboard (`dashboard/pages/1_Index_Research.py`) | Implemented | **Visual QA pending** | Pending | Displays unverified-data warnings |
| Model comparison dashboard (`dashboard/pages/2_Model_Comparison.py`) | Implemented | **Visual QA pending** | Pending | PCA, GARCH, OLS, OU |
| Static Vercel viewer (`web/`) | Implemented | Browser QA pending | Publication review pending | Static only, not deployed |
| Static exporter (`scripts/export_static_dashboard.py`) | Implemented | Pending | Licensing/privacy review pending | Requires explicit `--publish` |
| Local scripts and configuration (`scripts/run_local.sh`, `config/`) | Implemented | Pending | Pending | Uses current user environment |
| Python unit/regression tests (`tests/`) | Written | **Not rerun locally** | N/A | Prior CI passed an earlier, smaller code snapshot only |
| Research paper / empirical conclusions | Template/report generation exists | Pending | **Not completed** | Cannot write actual conclusions before verified market experiment |
| GitHub Actions | **Removed** | N/A | N/A | GitHub is source control only |
| Production Vercel deployment | **Not deployed** | N/A | N/A | User will decide later |
| Merge into `main` | **Not performed** | N/A | N/A | Keep work on draft PR |

## Model scope not yet implemented

The library does **not** claim to contain full Fama-French factor return
replication, a proprietary commercial risk model, a production-grade execution
simulator, a complete efficient-frontier model comparison, or historical
sector classification vintages. GARCH is a simplified Gaussian GARCH(1,1)
implementation rather than a full econometrics toolkit. The baseline research
framework has no automated historical constituent/fundamental vendor connector.

## Release gates

1. **Local technical QA:** dependency setup, unit tests, CLI synthetic run, legacy
   run, full dashboard smoke/visual testing, report and export integrity.
2. **Research QA:** independent as-of membership and fundamental sources,
   compatible benchmark, corporate-action/delisting handling, realistic
   execution costs, frozen final holdout and sensitivity/negative-control tests.
3. **Public presentation:** documented provenance, publication rights, accurate
   charts, review of any exported static data, and honest resume claims.
4. **Deployment/merge:** only after user-led local verification and acceptance.

## Local commands

```bash
bash scripts/run_local.sh setup
bash scripts/run_local.sh tests
bash scripts/run_local.sh synthetic
bash scripts/run_local.sh legacy
bash scripts/run_local.sh dashboard
```

Test scripts should not be mistaken for a confirmed passing local test run.


## Extended mathematics (November 11)

The following additional code has been committed; **local execution and
historical validation are pending**. See [full mathematics catalog](MATH_CATALOG.md).

| Additional module | Code status | Local QA | Market/evidence QA |
| --- | --- | --- | --- |
| `portfolio_theory.py`: efficient frontier, active tracking-error utility, risk parity, diversification, Euler risk decomposition | Implemented | Pending | Pending |
| `portfolio_extensions.py`: Black–Litterman, historical CVaR linear program, factor neutralization | Implemented | Pending | Pending |
| `statistical_inference.py`: CAPM, FF3/FF5, Carhart, HAC Newey–West, bootstrap, BH correction, walk-forward, rank IC and spread | Implemented | Pending | Factor-return data missing |
| `tail_risk.py`: normal/t VaR and ES, correlated Monte Carlo, scenario shocks, Kupiec, EVT | Implemented | Pending | Calibration/holdout missing |
| `derivatives.py`: implied vol, BSM numerical checks, binomial American options, antithetic Monte Carlo, Heston and Merton processes | Implemented | Pending | Market calibration missing |
| `dashboard/pages/3_Advanced_Mathematics.py` | Implemented | Visual QA pending | Inputs are user-supplied/assumptions |
| `tests/test_additional_mathematics.py` | Written | **Not run locally** | N/A |

These extensions are additional quantitative research demonstrations, not
proof of empirically profitable or officially published index methodologies.


## Rolling Model-Validation Extension

| Module | Code status | Local QA | Research/data QA |
| --- | --- | --- | --- |
| `model_validation.py`: rolling variance scoring, covariance model comparison, group-neutral factor spreads | Implemented | Pending | Market input provenance required |
| `dashboard/pages/4_Rolling_Validation.py`: diagnostics UI | Implemented | Visual QA pending | Historical data required |
| `tests/test_model_validation.py`: rolling leakage regression tests | Written | Not run locally | N/A |


## Integration completion pass — 2026-11-11

| Previously missing area | Source files | Code status | Verification status |
| --- | --- | --- | --- |
| Unified executive overview | `dashboard/app.py` | Connected to session results | Visual QA pending |
| Dedicated Factor Laboratory | `dashboard/pages/6_Factor_Laboratory.py` | Connected | Visual QA pending |
| Dedicated Index Comparisons | `dashboard/pages/7_Index_Comparisons.py` | Connected | Visual QA pending |
| Research-report UI / exports | `dashboard/pages/8_Research_Report.py` | Connected | Visual QA pending |
| Historical sector classification | `sector_data.py` + `index.py` | Integrated optional input | Real vintages unavailable |
| Sector cap configuration | `experiment.py` + Index Research sidebar | Connected | Local QA pending |
| Sector exposure and concentration | `sector_data.py` / `research_analytics.py` | Connected | Local QA pending |
| Rolling active risk and transaction cost sensitivity | `research_analytics.py` | Connected | Local QA pending |
| Comparable index methodology results | `comparison.py` | Connected with matched inputs | Local QA pending |
| Research PDF draft | `pdf_report.py` / CLI / UI | Connected | Rendering inspection pending |
| Integrated regression tests | `tests/test_research_integration.py` | Written | Not run locally |
| Corporate actions / delisting cash flows | Requires dated source data + event policy | Not production-complete | Blocked on source evidence |
| Point-in-time benchmark and security fundamentals | Input contracts in place | **Source data not provided** | Research validity blocked |
| Detailed research paper conclusions | PDF/HTML templates only | Actual conclusions not written | Pending verified experiment |

**Release judgment:** A materially broader source-code prototype exists, but
its complete end-to-end runtime correctness and empirical finance claims remain
unverified. The repository contains no GitHub Actions workflow. The user plans
one future local QA round; do not treat "connected" as proof of "works."


## Latest integrated research completion pass (2026-11-11)

| Feature | Code | UI / reporting | Local QA |
| --- | --- | --- | --- |
| Executive overview, Factor Lab, Index Studio, Index Comparisons | Connected | Dedicated session-aware Streamlit pages | Pending |
| Risk/concentration, historical sector exposure, transaction cost sensitivity | Connected | Charts and artifact CSVs | Pending |
| Date-effective historical sector caps | Connected to index construction | Optional configuration in Index Research | Pending |
| Minimum variance / risk parity index weighting | Connected to historical lagged covariance | Weighting selector and backtest | Pending |
| Matched factor/index variant comparison | `comparison.py` | Comparison series and table | Pending |
| Input completeness / historical evidence audit | `data_audit.py` | Robustness dashboard / JSON artifact | Pending |
| Parameter robustness grid (development/validation only) | `robustness.py` | Robustness chart / CSV artifact | Pending |
| Report generation | HTML + PDF sources | CLI and Research Report downloads | PDF render QA pending |
| Historical corporate-action records | Optional evidence audit only | Input contract and warnings | **No payout/recovery engine** |
| Vendor-backed point-in-time data / genuine Nifty benchmark | Not available | Import-only interface | **Blocked by source data** |
| Reproducible final empirical conclusions | Not written | Draft report clearly unverified | **Blocked by market-data validation** |
| Full local numerical/visual acceptance | Tests written | Run scripts provided | **Not executed per user instruction** |

**Acceptance standard:** Code being committed is not equivalent to a passing
local run. An end-to-end research product still requires trusted historical
membership, fundamental vintages, corporate actions/dividends, valid benchmark
series, careful securities lifecycle handling and final holdout research. Do
not represent these external evidence requirements as already satisfied.


## Integrated application completion pass — 2026-11-11

The software features previously classified as "UI incomplete" or "core mostly
implemented" now have implementation paths in the development branch.

| Feature | Current implementation | Verification |
| --- | --- | --- |
| Executive research overview | `dashboard/app.py` reads current experiment state | Local UI QA pending |
| Index Construction Studio | `dashboard/pages/1_Index_Research.py` supports factor weights, constituent count, weighting, caps, frequency, sector cap, execution lag and costs | Local UI QA pending |
| Factor Laboratory | `dashboard/pages/6_Factor_Laboratory.py` reads score ranks, per-factor IC history, past-signal exposure history, concentration and historical sectors | Local UI QA pending |
| Index methodology comparisons | `comparison.py` plus `dashboard/pages/7_Index_Comparisons.py` calculate like-for-like index variants and risk statistics | Local / historical QA pending |
| Risk Attribution and Stress | `dashboard/pages/9_Risk_Attribution.py` displays covariance risk contributions, losses, concentrations and hypothetical sector shock | Local UI QA pending |
| Historical sector methodology | `sector_data.py`, `index.py` effective-dated sector caps, `experiment.py` exports sector exposure | Source and integration QA pending |
| Cost and turnover sensitivity | `research_analytics.py` and comparison UI; fixed-trade-path cost sensitivity | Execution model simplifications |
| Research paper and reports | `pdf_report.py` ReportLab PDF draft; `reports.py` HTML; shared manifest / CLI / UI exports | PDF rendering QA pending |
| Shared dashboard data | Index experiment persists data and results for overview, optimization lab, factor, risk, comparison and report pages | Local cross-page QA pending |
| CLI/dashboard artifact parity | `run_from_directory` exports factor IC, exposures, sector analytics, methodology variants and coverage | Local test pending |
| End-to-end acceptance harness | `scripts/local_acceptance.py` and `tests/test_complete_integration.py` | **Written but not executed** |
| UI visual system | `.streamlit/config.toml` consistent dark theme | Visual QA pending |
| GitHub Actions | Removed | No automatic execution |
| Historic constituent/fundamental dataset | **Not sourced** | **External research/data dependency** |
| Live Vercel computational backend | Not built | Out of scope for local-first version |

**Definition of complete:** The intended local-first software feature code
has been authored. That is not yet equivalent to a functioning verified
application: acceptance tests, smoke tests, error-path QA and visual checks
still must be run locally. The real-data research study is blocked by
historical point-in-time membership and fundamental availability evidence.

**Explicit limitation:** Corporate-action adjustment accuracy, delisting
payouts, security identifiers, benchmark licensing, variable fees, impact,
partial fills and realistic live execution cannot be claimed verified from
the present inputs. No actual MSCI or official Nifty methodology is replicated.

### Local acceptance command

```bash
bash scripts/run_local.sh setup
bash scripts/run_local.sh acceptance
```

If either command fails, **the software cannot be called verified**.


## Final integration inventory (local-first feature pass)

- **Core index:** factor scores, point-in-time membership/sector-vintage
  inputs, per-stock weights/sector caps, drift-aware turnover, costs and
  benchmark-relative comparisons are implemented in source.
- **Mathematics:** statistical inference, factor-model regression,
  constrained portfolio allocation, numerical option pricing, stochastic
  processes, tail-risk and rolling estimator validation are implemented.
- **UI:** executive overview plus Index Research, Factor Laboratory,
  Model Comparison, Advanced Mathematics, Quantitative Models, Rolling
  Validation, Index Comparisons, Risk Attribution, Robustness/Data Audit,
  Visual Validation and Research Report views are in source.
- **Shared result pipeline:** the CLI and interactive experiment runner
  export factor IC and exposures, sector exposures, portfolio concentration,
  rolling relative metrics, methodology variants, sensitivity grid, dataset
  audit, SHA-256 manifest and HTML/PDF draft reports.
- **Local QA:** `scripts/local_acceptance.py` runs tests, synthetic
  end-to-end research, validates PDF and export files, and smoke-tests
  Streamlit pages. It is NOT automatically executed by GitHub.

**Still not verified:** The first actual local acceptance run, visual layout,
numerical convergence on the end-user's environment, historical market
membership, published fundamental vintages, corporate actions/delistings,
benchmark licenses, final holdout and true empirical research conclusions.

No GitHub Actions, branch merge, or Vercel deployment has been initiated.

## Visual mathematical verification (2D and 3D)

| Addition | Code | Visualization | Acceptance |
| --- | --- | --- | --- |
| `index_research/visual_validation.py` | Implemented | Chart-ready analytic checks and calculated grids | Local tests pending |
| `dashboard/pages/10_Visual_Validation.py` | Implemented | 2D convergence/fan/risk/forecast charts; 3D option and portfolio surfaces | Browser QA pending |
| `scripts/export_visual_validation.py` | Implemented | Standalone interactive HTML plus CSV/JSON evidence | Offline render QA pending |
| `tests/test_visual_validation.py` | Written | Mathematical checks, simplex and grid invariants | Not executed locally |
| `scripts/run_local.sh visuals` | Implemented | Single-command visual evidence generation | Local QA pending |

Charts deliberately label theoretical data, simulated paths, and uploaded
financial observations separately. Mathematical PASS badges refer only to
explicit numeric tolerances, not to source-data integrity or investable
performance. 3D plots are included where they reveal an additional meaningful
dimension; time-series validation remains 2D for readability.
