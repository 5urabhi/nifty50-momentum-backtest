# Local-first Quickstart (Ubuntu, macOS, Windows)

The project is **not automatically executed, scheduled or deployed** by GitHub.
The development branch intentionally contains **no GitHub Actions workflow**.

## 1. Get the branch

```bash
git clone --branch research/multi-factor-equity-index https://github.com/5urabhi/nifty50-momentum-backtest.git
cd nifty50-momentum-backtest
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r dashboard/requirements.txt
```

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`.
Requires Python 3.11 or later. The older root requirements.txt is from the
legacy notebook; install dashboard/requirements.txt for the new project.

## 2. Local tests (ONLY when ready)

```bash
python -m unittest discover -s tests -v
```

Tests cover timing, point-in-time eligibility, factor signals, index constraints,
drift-aware turnover, analysis reports, covariance, option parity, GBM, PCA,
GARCH and regression. No tests have to run in GitHub.

## 3. Try a synthetic offline end-to-end run

```bash
python -m index_research.cli make-fixture --output-dir data/synthetic_example
python -m index_research.cli run --input-dir data/synthetic_example --output-dir results/synthetic --config config/research_momentum.json
python -m index_research.cli report --output-dir results/synthetic
```

The **entire example dataset is synthetic**, including the benchmark and
"fundamentals". Results must not appear in a job application as historical
market-performance evidence. View `results/synthetic/research_report.html` in a
browser; other outputs are machine-readable CSV/JSON.

For multi-factor mode on synthetic fixtures:

```bash
python -m index_research.cli run --input-dir data/synthetic_example --output-dir results/synthetic_multi --config config/research_multifactor.json
```

## 4. Launch the dashboard locally

```bash
streamlit run dashboard/app.py
```

The start page is the quantitative modeling lab. Use the sidebar navigation to
open **Index Research** and use a synthetic demonstration or upload a ZIP
containing exactly the research CSVs from `data/README.md`.
Streamlit runs locally and is not a Vercel application.

## 5. Real-market research

Prepare `data/my_research/` with point-in-time `prices.csv`, `membership.csv`,
`benchmark.csv` and optional publication-dated `fundamentals.csv`.
The reader intentionally rejects missing benchmark dates and unknown membership
state. Use **adjusted total-return-compatible** prices and matching benchmark
returns or document a price-return-only comparison. Backtests remain exploratory
until data provenance is independently verified.

```bash
python -m index_research.cli run --input-dir data/my_research --output-dir results/real_experiment --config config/research_multifactor.json
```

These JSON configurations are **templates**; change time splits and factor
choices only based on a declared research protocol, not post-hoc holdout tuning.

## 6. Optional future Vercel preview

A static-only viewer lives in `web/`. To publish a **publicly shareable**
snapshot of the experiment's AGGREGATED metrics and return series, opt in:

```bash
python scripts/export_static_dashboard.py --results-dir results/real_experiment --publish
```

Read the warnings before doing this: all static files are public if deployed.
Review the exported `web/data/` files before any deployment. Do not publish
brokerage accounts, private positions, licensed vendor data, or proprietary
investment information. No automated deployment is configured.

A later hosted *interactive* research computation service would need a separate
API architecture. Streamlit cannot simply be copied into Vercel static hosting.

## Research claims policy

Do not cite old optimized Sharpe/return as verified. Never present synthetic
results as evidence. The resume should describe methods actually implemented
and results independently reproduced, not hypothetical return improvements.

## Use the **actual legacy source CSV** as a transparent demonstration

The old `nifty50_prices_monthly.csv` can be used without replacing or
pretending to reconstruct historical membership. The converter uses
complete-case securities, a static eligible universe, and an internally
equal-weighted benchmark. **This introduces serious survivorship bias and is
NOT a real Nifty 50 benchmark study**:

```bash
python scripts/prepare_legacy_demo.py
python -m index_research.cli run --input-dir data/legacy_static_demo --output-dir results/legacy_static_demo --config config/research_legacy_demo.json
```

It produces `data/legacy_static_demo/DEMONSTRATION_LIMITATIONS.json`.
Use the output to inspect workflow mechanics only, not for published returns.

## One-command local helpers

After `bash scripts/run_local.sh setup`, choose
`bash scripts/run_local.sh tests`, `synthetic`, `legacy`, or `dashboard`.
All execution occurs on your machine, not GitHub.


## New advanced mathematics dashboard

The Streamlit sidebar also offers **Advanced Mathematics**:
portfolio frontiers, risk parity, benchmark-tracking optimization,
Black–Litterman, CVaR, tail-distribution comparisons, robust factor
regression and numerical option-pricing comparisons.

New math tests are in `tests/test_additional_mathematics.py`. They
should be run locally with `bash scripts/run_local.sh tests` when ready;
no GitHub Actions checks are configured.
