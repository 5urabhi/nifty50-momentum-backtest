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

## Start locally (Python 3.11+)

```bash
git clone --branch research/multi-factor-equity-index https://github.com/5urabhi/nifty50-momentum-backtest.git
cd nifty50-momentum-backtest
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r dashboard/requirements.txt
```

When you choose to test locally:

```bash
python -m unittest discover -s tests -v
python -m index_research.cli make-fixture --output-dir data/synthetic_example
python -m index_research.cli run --input-dir data/synthetic_example --output-dir results/synthetic --config config/research_momentum.json
streamlit run dashboard/app.py
```

**Synthetic experiment data are NOT Nifty history.** You must supply historical
membership events, compatible prices and benchmark returns, and publication-dated
fundamental factors before claiming a market-valid index experiment.

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

## Documentation

- [Full code status and remaining QA](docs/CODE_STATUS.md)
- [Local runbook](docs/LOCAL_RUN.md)
- [CSV and point-in-time data contract](data/README.md)
- [Research methods and acceptance matrix](docs/RESEARCH_METHODS.md)
- [Research protocol](docs/RESEARCH_PROTOCOL.md)
- [Mathematical models](docs/MATHEMATICAL_MODELS.md)
- [Legacy README](docs/LEGACY_MOMENTUM_README.md)

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
