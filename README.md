> **Looking for the React/Vite QuantLab research workstation?** This repository includes
> legacy notebook research alongside the modern local React + FastAPI UI.
> Start with [the workstation user guide](docs/QUANTLAB_USER_GUIDE.md),
> [the 26-model mathematical catalog](docs/MODEL_LABORATORY_GUIDE.md),
> and [reproducibility checklist](docs/QUANTLAB_REPRODUCIBILITY.md).
> Launch with `bash run.sh` on branch `feature/quantlab-model-laboratory-and-guide-20261113`
> and open `http://127.0.0.1:5173`. In-app help is under **User Guide & Documentation**.
> Brokerage orders are disabled. Outputs must not be misrepresented as audited historical returns.

> **Current application — React/Vite QuantLab workstation (November 12, 2026):**
> The previous Streamlit dashboard has been replaced as the **default** interface
> by a private local React/Vite workstation backed by FastAPI/Python. Start with
> `bash run.sh` and open **http://127.0.0.1:5173**. API tokens belong in
> project-root `.env`. Read [REACT_WORKSTATION.md](REACT_WORKSTATION.md)
> for current setup, supported workflows and validation status. The older
> Streamlit instructions below are retained for legacy reference only.
>
# Equity Index Quantitative Research & Construction Framework

**Local-first research software | Independent project | Development branch**

This repository extends an original Nifty 50 cross-sectional momentum study
into a reproducible research environment for factor methodologies, index
construction, constrained optimization, quantitative risk, and model comparison.

> **Research integrity:** The historical legacy notebook contains an
> optimized Sharpe of 3.34 and annualized return of 132.86%. These are
> **unverified legacy claims**, not audited outputs of this framework. The
> static ticker universe can introduce survivorship bias. Do not cite these
> performance figures or claim investability without point-in-time validation.

## What this research project provides

| Area | Implementation |
| --- | --- |
| Legacy research | Original `main.ipynb`, data exports, and legacy findings preserved |
| Factor engine | Momentum, Low Volatility, Value, Quality, Size |
| Index design | Top-N eligibility, equal/score/inverse-vol weighting, caps, periodic reconstitution |
| Historical-data controls | Membership events, source-date fundamentals, strict benchmark alignment |
| Simulation | Drift-aware long-only monthly backtest, explicit execution lag, cost sensitivity |
| Quantitative models | Sample/shrinkage/EWMA covariance; Markowitz min variance; historical VaR/ES |
| Mathematical laboratory | GBM, OU, PCA, Gaussian GARCH(1,1), BSM pricing/Greeks, factor OLS |
| Presentation | Local Streamlit research dashboard and offline HTML report |
| Reproducibility | Deterministic synthetic fixture, CLI, JSON configs, SHA-256 input manifest |
| Optional publication | Static Vercel viewer exported from explicitly approved public aggregate data |
| Tests | Local `unittest` suite; **no GitHub Actions execution** |

No official MSCI or NSE index methodology is claimed. This is an independent
research and educational framework, not investment advice.

## Start here — your personal quantitative research workstation

This project is **for running your own quantitative finance models,
experiments, mathematical tests, and 2D/3D graphs** to build a reproducible
research portfolio. It is not a company application or a trading service.

**[Full local setup and model-running guide](GETTING_STARTED.md)**

After cloning the research branch:

```bash
cd ~/Desktop/codes/nifty50-momentum-backtest
git pull --ff-only origin research/multi-factor-equity-index
bash run.sh
```

**The default command opens the actual Python research dashboard at
http://127.0.0.1:8501.** This includes Index Research, Factor Laboratory,
Index Comparisons, Advanced Mathematics, Rolling Validation, Quantitative
Models, Risk Attribution, Robustness, Visual Validation and Research Report.

```bash
bash run.sh             # DEFAULT: personal Python model/workstation UI
bash run.sh evaluate    # Run full tests + mathematics + synthetic experiment + reports
bash run.sh check       # Run Python unit tests and mathematical acceptance
bash run.sh research    # Same as default
bash run.sh web         # OPTIONAL animated public explainer website (React/Vite)
bash run.sh both        # Both interfaces
bash run.sh setup       # Prepare dependencies without starting servers
```

**Inside the dashboard:** Choose **Index Research** in the sidebar, select
**Synthetic demonstration** to test the machinery, then click **Run**. Visit
the other model pages and Research Report to explore and export results.

**Research validity:** Synthetic results show that code runs, not that a
Nifty strategy earns money. Portfolio-worthy historical performance must be
recomputed using verified point-in-time sources and an approved benchmark.

### Inside the workstation — no terminal data-download commands

1. **Data → Dhan Data Manager:** Download instrument master, search symbols,
   confirm Security IDs, maintain a local watchlist, download historical
   OHLCV, and explore observed prices and volumes.
2. **Data → Prepare for models:** Convert saved daily candles to month-end
   price observations and select the dataset.
3. **Empirical Readiness:** Upload independently sourced membership,
   benchmark, fundamentals, corporate actions or adjusted price files
   through the UI. Missing evidence remains a hard blocker.
4. **Index Research:** Run a configured factor experiment using that local
   folder, a ZIP, or a clearly labeled synthetic fixture.
5. **Labs → Model Comparison / Rolling Validation / Advanced Mathematics:**
   Explore analytical models and optionally reuse the active experiment.
6. **Reports → Saved Run History:** Reopen locally persisted run artifacts,
   plots, validation tables, HTML/PDF research drafts and ZIP exports.

Every page includes a grouped **WORKSTATION WORKFLOW** navigation menu.
There are no trading/order actions and no invented historical data. Full
instructions: [dashboard/README.md](dashboard/README.md).

## Architecture

```text
index_research/
  core.py             Initial momentum baseline utilities
  data.py             Local CSV validation and publication-date eligibility
  factors.py          Five factor scores and rank information coefficient
  index.py            Index construction + drift-aware monthly simulator
  experiment.py       Experiment config, holdout metrics, provenance manifest
  math_models.py      Covariance, Markowitz, empirical risk, GBM, BSM, OLS
  advanced_models.py  PCA, OU, GARCH and covariance stress approximation
  reports.py          Offline HTML methodology/performance report
  fixtures.py         Clearly labeled synthetic test inputs
  cli.py              Local run interface
dashboard/
  app.py                        Mathematical modeling laboratory
  pages/1_Index_Research.py     Multi-factor index research + export
  pages/2_Model_Comparison.py   PCA/GARCH/OLS/OU comparison
scripts/
  export_static_dashboard.py   Manual static publication boundary
web/                            Static future Vercel presentation
config/                         Frozen experimental configuration examples
tests/                          Local unit and integrated tests
docs/                           Methodology, runbook, research protocol
main.ipynb                      Original notebook (preserved)
```

## Research workflow

1. Declare hypotheses and chronological development / validation / final-test splits.
2. Prepare **verified point-in-time** historical securities and adjusted prices;
   record vendor licensing, security identifiers, delisting treatment, corporate
   actions, and publication dates.
3. Calculate factor scores only from observations available to the decision.
4. Construct and backtest index methodology with documented weight constraints.
5. Compare against return-convention-compatible benchmarks and estimate
   transaction costs, turnover, drawdowns and risk.
6. Evaluate holdout robustness. Do not tune on the frozen final test.
7. Export machine-readable artifacts and the offline report for independent review.
8. Present verified findings, assumptions and limitations in the portfolio and resume.

## DhanHQ historical market-data connector\n\nThe repository now contains a **read-only local DhanHQ v2 adapter** with\nhistorical daily/intraday OHLCV, 90-day intraday chunking, retry/backoff,\nvalidation, instrument-master lookup, provenance manifests, and monthly-close\nconversion. It never places orders or commits tokens.\n\n**[Step-by-step Dhan API setup and downloads](docs/DHAN_API_SETUP.md)**\n\n\`python scripts/dhan_data.py instrument-master\` downloads the current\nDhan scrip master; \`instrument-search --query "RELIANCE"\` helps locate\nSecurity IDs. The local dashboard includes a **Dhan Data Setup** onboarding\npage and raw OHLCV preview charts. The connector supplies raw closes, not\ncertified total-return-adjusted prices or historical Nifty constituents.\n\n## Documentation

- [Full code status and remaining QA](docs/CODE_STATUS.md)
- [Local runbook](docs/LOCAL_RUN.md)
- [CSV and point-in-time data contract](data/README.md)
- [Research methods and acceptance matrix](docs/RESEARCH_METHODS.md)
- [Research protocol](docs/RESEARCH_PROTOCOL.md)
- [Mathematical models](docs/MATHEMATICAL_MODELS.md)
- [Legacy README](docs/LEGACY_MOMENTUM_README.md)

## Local research workstation — integrated pages

The Streamlit navigation now contains the executive **Overview** plus:
- **Index Research** — rank eligible stocks, apply caps/sector constraints and calculate a backtest.
- **Model Comparison** — PCA, GARCH, OU and factor regression.
- **Advanced Mathematics** — Markowitz, Black–Litterman, CVaR, HAC inference and options.
- **Rolling Validation** — lag-only variance/covariance comparisons.
- **Quantitative Models** — covariance optimization, stochastic models, BSM, Heston and jump processes.
- **Factor Laboratory** — per-factor rank IC, scores and holding-period factor exposures.
- **Index Comparisons** — matched strategies, rolling tracking error and cost sensitivity.
- **Research Report** — HTML/PDF draft exports and experiment provenance.
- **Risk Attribution** — covariance risk contributions, historical losses and hypothetical sector shocks.

The research runner also generates a **data quality manifest**, historical
sector exposure if sector input is supplied, and multiple strategy comparison
tables. All charts come from uploaded data or clearly labeled simulations.

**One local acceptance command:** `bash scripts/run_local.sh acceptance`.

This software is **code-complete for the planned local-first prototype**,
but not runtime-verified or supported by independently audited point-in-time
market data. The accompanying local tests and UI checks have been authored;
their results remain pending. The Vercel presentation is a separate static
viewer, not a deployed Python research backend.

## Remaining research gates

**Code-implemented does not mean empirical validation completed.** The code
needs first local execution, numerical QA, independent historical data,
a documented benchmark, and reproducibility review before any positive
backtested return or professional impact claim is published.

The legacy notebooks and exports are preserved as the historical baseline,
not silently overwritten by the new model results.


## Advanced mathematics extension

New modules cover efficient-frontier portfolio theory, risk parity, maximum
diversification, benchmark-constrained active optimization, Black–Litterman,
historical CVaR linear programming, Fama–French/Carhart factor regressions,
Newey–West HAC inference, block bootstrap, multiple testing, stochastic
volatility, tail risk and numerical derivatives pricing.

- [Quantitative mathematics catalog](docs/MATH_CATALOG.md)
- [Advanced Mathematics dashboard page](dashboard/pages/3_Advanced_Mathematics.py)

All new models await local runtime QA. GitHub Actions remains disabled.


### Rolling model validation

An additional **Rolling Validation** dashboard page compares sample/EWMA
variance forecasts using QLIKE and forecast error, plus rolling (historical
only) sample/shrinkage/EWMA covariance portfolios. The illustrated
portfolio paths are **frictionless diagnostic comparisons**, not a production
index backtest. See [Model Mathematics Catalog](docs/MATH_CATALOG.md).

- [Rolling validation module](index_research/model_validation.py)
- [Rolling validation dashboard](dashboard/pages/4_Rolling_Validation.py)
- [Local rolling diagnostics tests](tests/test_model_validation.py)


## End-to-end research workstation (development branch)

The Streamlit entrypoint now provides a session-aware executive overview,
a dedicated Factor Laboratory, matched Index Comparisons, a Research Report
with HTML/PDF exports, four additional mathematical modeling pages, and
rolling model diagnostics. Index Research supports optional effective-dated
`sectors.csv` evidence and sector caps.

Calculated outputs include issuer concentration, sector allocation,
rolling benchmark-relative risk, transaction-cost sensitivity, and common
methodology comparison series; none of these use hardcoded return numbers.

**Documentation:** [Local execution](docs/LOCAL_RUN.md) ·
[Input CSV contract](data/README.md) ·
[Complete module status](docs/CODE_STATUS.md) ·
[Research methodology](docs/RESEARCH_METHODS.md).

The empirical market study is **not finished** until vetted historical data,
local execution, numerical verification, corporate-action handling, QA and
independent holdout evaluation are complete. No GitHub Actions or hosted
Python compute is configured.


## Final integration additions (research prototype)

- Standalone **Factor Laboratory**, **Index Comparisons**, **Research Report**
  and **Robustness** pages connected to the Index Research experiment.
- Date-effective sector classification history and sector-constrained index
  selection; issuer/sector exposures and concentration histories.
- Lagged covariance-based minimum-variance and risk-parity weighting available
  directly in the index methodology selector.
- Like-for-like momentum/low-volatility/selected factor methodology comparisons,
  rolling benchmark-relative metrics and transaction-cost sensitivity.
- Dataset completeness and corporate-action **evidence** audit (not a complete
  corporate-action return-processing engine).
- Parameter-grid robustness studies restricted to development/validation.
- Offline PDF research-paper **draft** and HTML report from reproducible
  experiment artifacts.

The implementation is ready **for local QA**, not for a verified empirical
performance claim. No Actions workflows, deployment or merge was performed.

## Visual validation and presentation

The **Visual Validation Laboratory** adds interactive 2D and 3D Plotly charts,
with analytical reference values and numerical PASS/FAIL checks. Option-price
and Greek surfaces, a three-asset portfolio risk simplex, CRR/Monte Carlo
pricing convergence, GBM confidence bands and risk contribution checks are
available without external market data. Uploaded market observations can be
used for rolling variance forecast diagnostics.

```bash
bash scripts/run_local.sh visuals
```

This exports a **self-contained interactive HTML report**, machine-readable
chart data and a deterministic mathematical-check manifest to
`results/visual_validation/`. The local Streamlit sidebar also contains the
**Visual Validation** page. All mathematical fixtures are distinctly labeled
as hypothetical; they do not validate the Nifty backtest.

## Evidence-based empirical research input preparation

The research branch now contains three additional **local and read-only**
data-preparation modules:

- `index_research/total_returns.py`: source-aware daily return-index
  construction from Dhan split/bonus-adjusted closes plus independently
  verified cash dividends and terminal recovery events; never invents missing
  payouts or applies splits twice.
- `index_research/fundamental_ingestion.py`: validates normalized
  publication-dated historical filings and constructs transparent
  Value/Quality/Size research proxies.
- `index_research/benchmark_ingestion.py`: converts legally obtained
  NSE Indices total-return index levels into aligned monthly benchmark returns.
- `index_research/empirical_validation.py`: a human-declaration and
  frozen-holdout readiness gate, never an automatic external audit.

**[Complete corporate-action, fundamentals, TRI and historical membership
setup guide](docs/EMPIRICAL_DATA_GUIDE.md)**

```bash
python scripts/prepare_research_data.py --help
python -m unittest discover -s tests -v
```

The required underlying financial statement histories, event/vintage records,
index membership and benchmark datasets are **not supplied by this repository**.
The code cannot make a genuinely verified empirical result without them.


## Empirical data and study readiness — latest pass

Code added for: split/bonus-aware Dhan dividend reinvestment, evidenced
delisting cash, publication-dated NSE filing factor inputs, official
Nifty TRI benchmark level import, and a human-review/frozen-holdout gate.
The Streamlit navigation includes **Empirical Research Readiness**, where
real data coverage and review blockers are visible with no synthetic
substitution.

Use:
```bash
python scripts/prepare_research_data.py --help
```

**[Full data preparation and empirical protocol](docs/EMPIRICAL_DATA_GUIDE.md)**

**Important:** Full historical results are **not completed** until actual
exchange/vendor files and source documentation are available and independently
reviewed. The existing numerical/visual tests have not yet been executed
locally under the user's deferred-QA workflow. Do not describe model code as
a verified historical result.


## Quantitative mathematics acceptance

The equity-index mathematical framework includes an additional hardening
pass: drift-aware rolling covariance portfolios, solver-verified risk budgets,
one-step-ahead optional GARCH with fit diagnostics, comparable forecast
holdout periods, analytical option Greeks and stochastic-process tests.

**[Mathematical acceptance matrix and runbook](docs/MATHEMATICAL_ACCEPTANCE.md)**

```bash
bash scripts/run_local.sh math
```

This generates JSON/HTML numerical-check evidence using deterministic
local tests. The code has been committed, but a complete local acceptance
result has **not been observed** in this remote GitHub-only environment.
Mathematical correctness, source-data validity and empirical index
performance are three separate claims; do not conflate them.


## 🎬 Interactive website — mathematical explainer

The development branch now includes a **React 18 + TypeScript + Vite** public
showcase. It is distinct from the local Python/Streamlit research laboratory.

- Five autoplay/manual explainer chapters for factor research, index constraints,
  mathematical risk geometry, and out-of-sample validation.
- Animated vector graphs; selectable factor signals; interactive holding cap;
  draggable 3D portfolio volatility geometry; theoretical options-pricing curve.
- Responsive cinematic research design, reduced-motion support, keyboard
  navigation and code-rendered visuals.
- An **evidence-first** publication panel that never invents historical returns.
- A Vercel-ready static build, with no Python server or broker credentials.

**[Website and video recording guide](docs/SHOWCASE_AND_VIDEO.md)**

```bash
# After pulling this branch
npm install
npm run dev
# When ready for release verification:
npm run build
npm run preview
```

The existing Streamlit app remains intact for local research. The legacy
`web/` viewer is preserved for comparison; Vercel now builds `dist/` from
the new root Vite frontend. If you later export and approve a real public
snapshot, its aggregate data belong under `public/data/` and must pass
research source/licensing review before deployment.

**Build/visual QA and Vercel deployment have not been completed yet.**
