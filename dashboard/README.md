# Personal Quantitative Research Workstation

This is the **main interface** for testing your own mathematical models,
collecting local Dhan historical data, constructing factor indexes,
comparing risk estimators, checking robustness, and exporting evidence
for a portfolio or résumé. It is NOT a company product.

## One command

From the repository root:

```bash
bash run.sh
```

Open http://127.0.0.1:8501. The launcher installs required Python packages
in `.venv` and starts Streamlit locally. No npm, Redis, Docker, Vercel,
or Node.js is needed for the research workstation.

## Navigation

Every research page has the same **WORKSTATION WORKFLOW** sidebar expander.
The home screen contains five clickable stages.

| Stage | Page(s) | Purpose |
| --- | --- | --- |
| Data ingestion | Dhan Historical Data | Download official master, search symbols, map IDs, fetch historical OHLCV, inspect, convert |
| Data review | Empirical Readiness | Check membership, price adjustment, benchmark, publication vintages and evidence |
| Index research | Index Research | Select local prepared folder, ZIP, or synthetic example; run configurable factor strategy |
| Factor analysis | Factor Laboratory, Index Comparisons | Inspect constituent ranking, exposures, tracking error and methodology |
| Portfolio mathematics | Advanced Mathematics | Run Markowitz, risk parity, CVaR, Black–Litterman and inference |
| Statistical modeling | Model Comparison, Rolling Validation | Reuse active research returns for PCA, GARCH, EWMA and rolling comparisons |
| Stochastic & options | Quantitative Models | GBM, BSM, Heston, option Greeks and numerical tools |
| Risk | Risk Attribution, Robustness | Stress, contribution, sensitivity and coverage |
| Mathematics QA | 2D / 3D Visual Validation | Manipulate interactive analytical graphs and view numerical checks |
| Reports | Research Report, Saved Run History | Inspect current and previous runs, download PDF/HTML/CSV/ZIP outputs |

## Dhan workflow — no terminal downloader needed

1. **Dhan Data Manager → Connection & master:** store token only in
   local ignored `.env`, then use the button to download the instrument master.
2. **Find instruments:** search by name or symbol; select an equity/index
   result and prefill the watchlist mapping.
3. **Watchlist mapping:** review the Security ID, exchange and instrument
   and save.
4. **Download history:** select instruments, date range and daily/intraday
   resolution, then click the fetch button.
5. **Explore candles:** inspect local OHLCV and plot raw price/volume.
6. **Prepare for models:** resample daily closes to a monthly price matrix.
   Select the resulting folder as the research input.
7. **Empirical Readiness:** check source evidence.
8. **Index Research:** select the local folder and run only when all
   mandatory input files are present.

**Data warning:** Dhan historical candles alone do not establish
dividend-reinvested returns, historical Nifty index constituents, a
compatible total-return benchmark, or publication-dated fundamentals.
Missing evidence is not fabricated and incomplete index research is blocked.

Dhan is used **read-only**; no order placement, brokerage trade execution,
or credential submission to a web frontend.

## Interconnected model data

- The active Index Research experiment is held in Streamlit session state.
- Factor Laboratory, Index Comparisons, Risk Attribution, Robustness and
  Research Report read this shared experiment directly.
- Model Comparison (PCA/volatility), Rolling Validation and Quantitative
  Models (covariance panel) can optionally reuse its security return matrix.
- Advanced Mathematics already supports the active research dataset.
- Each experiment's generated artifacts persist under
  `results/workstation_runs/<UTC timestamp>_<id>/` even if the browser
  session closes. Use **Saved Run History** to reopen output charts, tables,
  manifests and report exports.

## Research testing

```bash
bash run.sh check       # Unit tests + Streamlit page acceptance + math tests
bash run.sh evaluate    # Same checks + synthetic experiment + 2D/3D reports
```

These commands run **locally**, not in GitHub Actions. A numerical test PASS
does not prove a profitable investment strategy.

## Publishing credible résumé findings

Only make historical performance claims after collecting authorized,
independently reviewed point-in-time source data, corporate actions,
complete index membership history, a valid benchmark and uncontaminated
out-of-sample results. The default simulated demonstrations must remain
labeled as mathematical or software tests.

For first-time setup, Dhan token configuration and troubleshooting,
see [GETTING_STARTED.md](../GETTING_STARTED.md).
