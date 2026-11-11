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
