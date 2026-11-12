# QuantLab — User Guide

**New:** The Research Workspace now manages saved model presets, datasets, results, 2D/3D comparisons, notebooks, reports and chronological validation. See [Research Workspace manual](RESEARCH_WORKSPACE_GUIDE.md) for the full instructions.

**Multi-Factor Equity Index Construction, Stochastic Modeling & Quantitative Risk Research**

> This is the canonical guide for the **local React/Vite + Python/FastAPI workstation**. It is **not** a public trading application, brokerage order router, or independently audited investment strategy.

## 1. Start here (Ubuntu)

1. Open a terminal in the existing project checkout.
2. Switch to the branch holding this Model Laboratory implementation.
3. Start both local processes with `bash run.sh`.
4. Open **http://127.0.0.1:5173** in the same machine's browser.
5. If the UI says **Engine Offline**, check that the Python backend is running on **http://127.0.0.1:8765**.

```bash
cd "$HOME/Desktop/codes/nifty50-momentum-backtest/nifty50-momentum-backtest"
git fetch origin
git switch feature/quantlab-model-laboratory-and-guide-20261113
git pull --ff-only origin feature/quantlab-model-laboratory-and-guide-20261113
bash run.sh
```

The checkout might not be nested if you cloned directly under `~/Desktop/codes`; use the directory that contains `run.sh`. The startup script installs/uses local dependencies. The terminal must stay running while you use the workstation.

## 2. Guided UI navigation

| Sidebar | When to open | What to expect |
|---|---|---|
| **Overview** | Dashboard and recent results | Shows saved Python experiment artifacts and selected dataset status; not an account brokerage portfolio. |
| **Data Manager** | Select or audit a dataset | Separate **FILES COMPLETE** from total-return correctness or independent verification. |
| **Dhan Market Data** | Download and resume | API profile check, instrument master, dated NIFTY membership, 1-minute OHLCV, resumption. |
| **Index Research** | Run a factor strategy | Historical point-in-time universe, factor scoring, portfolios, transaction costs, execution lag. |
| **Factor Laboratory** | Evaluate saved runs | Rank IC, factor exposures; requires an existing index research experiment. |
| **Index Construction** | Inspect saved allocations | Portfolio weights and concentration. |
| **Index Comparisons** | Compare methodology results | Variants and cost sensitivity. |
| **Advanced Mathematics** | Run theory and stochastic modeling | Six families, validated parameters, 2D and 3D plots, numeric diagnostics and equations. |
| **Quantitative Models** | Optimize and inspect calibration | Same Model Laboratory, initially opening Portfolio Optimization. |
| **Rolling Validation** | Inspect saved historical experiment | Windowed backtest analytics and risk comparisons. |
| **Risk Attribution** | Inspect saved risk outputs | Concentration and rolling relative-risk metrics. |
| **Robustness** | Parameter sensitivity | Existing saved experiment evaluations. |
| **Visual Validation** | Saved run visualizations | Strategy-vs-benchmark and other evidence. |
| **Research Reports** | Export artifacts | Offline report artifacts generated for completed index experiments. |
| **Saved Runs** | Inspect experiment history | Select a run; read sample window and integrity warnings before using metrics. |
| **User Guide & Documentation** | Learn the workflow | Searchable help, definitions, route shortcuts and full reference documents. |

### Navigation within the Model Laboratory

**Choose a family** using one of six major tabs: Stochastic Processes, Volatility & Econometrics, Derivatives & Options, Portfolio Optimization, Tail Risk & Inference, or 3D Visual Laboratory.

**Choose a model** from the left list. Check the evidence badge:

- **THEORETICAL**: Price or Greek computed from manually specified parameters (no live option-chain quote).
- **SEEDED SIMULATION**: Explicitly synthetic, reproducible mathematical paths (no historical price calibration).
- **OBSERVED MARKET DATA**: Fits or descriptive risk calculations using cached local prices; not automatically point-in-time investable or predictive.

Use the four inner tabs:

1. **Parameters**: Select a dataset where required, inspect sample counts, set bounded inputs, then Run.
2. **2D / 3D Graphs**: Inspect real computed outputs. On 3D graphs drag to rotate, use arrow keys to rotate, and use +/− to zoom.
3. **Results & diagnostics**: Exact metrics, sample dates, input asset list and source, export to reproducible JSON or CSV.
4. **Theory & limitations**: Mathematical equation, modeling assumptions, sample requirement, and interpretation warnings.

The Python model catalog is the single source for supported algorithms and parameter bounds; the React UI does not silently substitute data.

## 3. DhanHQ API setup

QuantLab keeps market-data authentication in Python, not React. Store `DHAN_ACCESS_TOKEN` in the local project-root `.env`. **Never commit, share, or screenshot your token, PIN or TOTP secret.** Dhan's manually generated token is short-lived; check access under **Dhan Market Data → Verify Dhan API access**.

Data API subscription, token validity, exchange symbol mapping and historical coverage are separate conditions. Read-only Dhan API calls do not place orders. Run the API from localhost only. See `docs/DHAN_API_SETUP.md` for detailed troubleshooting.

## 4. From Dhan candles to research

### NIFTY 50 or BANK NIFTY with historical members

1. Open **Dhan Market Data**.
2. Select **NIFTY 50 · Historical** or **BANK NIFTY · Historical**.
3. Choose **from** (inclusive), **to** (exclusive), and resolution (for example 1 minute).
4. Sync/update historical membership when needed. Membership evidence and price candles have **different sources**.
5. Review exact symbol mapping and incomplete historical coverage. Do **not** assume today's stocks always belonged to the index.
6. Download stocks. Large windows are divided into supported Dhan date batches, with per-window cache checksums and resumable progress.
7. Inspect the batch for failed, empty or missing instruments; a successful queue count alone does not prove perfect candle completeness.
8. On a **completed** batch, click **Prepare research dataset from 1-minute candles**. This creates daily OHLCV, daily closes, month-end prices and `membership.csv` locally.
9. If the downloaded batch includes verified index-level spot candles, click **Prepare price-index benchmark from saved index spot**. This creates `benchmark.csv` from the same local cache. **It is a price index (not TRI).**
10. Open **Data Manager** and select the derived dataset. Check file inventory, benchmark type, and basis.

No repeat stock downloading is necessary for the local preparation steps. The original files stay in `data/dhan/`, which is Git-ignored.

### Data Manager: read the badges correctly

- **FILES COMPLETE / Ready = true** means required structural inputs exist and the dataset can be passed to the research engine.
- It **does not** certify adjusted total returns, accurate historical delisting coverage, exchange-level 1-minute completeness, point-in-time fundamentals or an investable portfolio.
- **Fundamentals** and **sectors** are optional for some models but compulsory if a selected factor or constraint needs them.
- Price-index comparison excludes reinvested dividends. To claim excess total returns, acquire independently sourced **NIFTY TRI** and audit each stock's split/dividend/corporate-action history.

## 4A. Unified market history and model data readiness

**One canonical Dhan store:** Market closes are keyed by exchange segment, Dhan Security ID and trading date in `data/dhan/shared_market.sqlite3`. The two files `data/dhan/monthly_research/shared/daily_prices.csv` and `prices.csv` are derived, reusable model views, not independent datasets. One stock appearing in multiple NIFTY/BANK NIFTY portfolios is stored once. Index membership and benchmark files remain separate because they represent different historical evidence.

1. Open **Advanced Mathematics** or **Quantitative Models** and choose a historical model and an observed Dhan dataset.
2. The **Data requirements & shared history** panel shows the model minimum, +20% research buffer, actual common finite returns across the requested number of securities, and any shortage. The minimum and buffer target are distinct: the model can run with its minimum while showing that additional data is preferable.
3. When appropriate, click **Yes — download & prepare missing data**. This is the user's explicit authorization for read-only Dhan requests. The backend inspects SHA-verified existing daily and intraday caches first, and downloads **only uncovered date windows** for each instrument.
4. The background job appends new observations to the canonical SQLite store, checks conflicts, regenerates the shared daily/monthly views and rechecks model readiness. It selects `dhan_shared` on completion and reports when history remains insufficient. Original per-batch data and prior saved research snapshots are preserved.

**Important:** The +20% preference is extra sample depth, not automatically an independent testing holdout. Separate chronological training, validation and untouched test data for out-of-sample claims. Observed unadjusted Dhan closes are not audited total-return series. Missing prices and sessions are never manufactured or forward-filled. The current automatic extension supports up to 18 unambiguously mapped Dhan stocks, and cannot reconstruct unresolved delistings, fundamentals or source-unavailable history.

**Existing downloads without network use:** The local backend offers `POST /api/lab/data-requirements/reuse-cached` to import the already cached Dhan catalog into the canonical store without vendor requests. Import can use significant local disk and CPU. The shared dataset may have a Data Manager "missing membership/benchmark" badge because it is usable for price-model experiments but not independently certified for index backtesting.

## 5. Run your first index experiment

1. Open **Index Research**, choose the prepared NIFTY dataset.
2. Enter a unique experiment name, for example `nifty_momentum_equal_v1`.
3. Set factors: **Momentum 1.0** and all other factors 0.0 (price-only); Value/Quality/Size require publication-dated fundamentals.
4. Choose Portfolio Weighting **Equal**, Top N **10**, Max Weight **0.20**, Rebalance **3 months**, and nonzero transaction costs.
5. Leave the **one-month conservative execution lag** unless your methodology explicitly assumes tradability at the same observation.
6. Choose formation months and skip months consistent with your history length.
7. Click **Run Python Backtest**, then open **Saved Runs** or the resulting Overview metrics.

**One year of monthly data cannot support a trustworthy 12-month formation plus skip plus execution lag followed by an informative holdout.** Reduce lookback only for a clearly labeled demonstration, or get longer history. An unavailable CAGR/drawdown metric (shown as —) means there are insufficient observations—not a zero result.

For a controlled comparison, create a second experiment that changes **only** Portfolio Weighting to **Minimum Variance** or **Risk Parity**, while retaining the same sample and costs. Do not tune on the same final test period and claim out-of-sample skill.

## 6. Model laboratory examples

### Example A — Stochastic GBM

Open Advanced Mathematics → **Stochastic Processes** → **Geometric Brownian Motion**. Keep the seed, steps and paths fixed; change only annual volatility. Run and compare the 5th, median and 95th simulated paths. These are **synthetic distributions**, not market forecasts.

### Example B — Heston vs Merton

Select Heston to inspect correlated spot/variance path behavior, then Merton to inspect jumps. Both are seeded and **uncalibrated**; the Heston solver uses an approximate full-truncation Euler discretization.

### Example C — GARCH calibrated to observed prices

Select **Volatility & Econometrics → Gaussian GARCH(1,1)**. Choose your prepared local dataset. The panel will prefer **daily_prices.csv**, require at least 60 common observed returns, then show fitted `ω, α, β`, persistence and conditional volatility. This is **in-sample**; use Walk-Forward Volatility for strict prior-window forecasts.

### Example D — Efficient frontier and optimizers

Select **Portfolio Optimization → Efficient Frontier / Minimum Variance / Risk Parity / Maximum Diversification / Historical CVaR**. Adjust asset count and maximum weight, respecting the feasibility constraint. Inputs are observed returns for the chosen securities, annualized consistently. These are descriptive allocations, not empirical investment alpha.

### Example E — Theoretical 3D options

Select **3D Visual Laboratory → 3D BSM Price Surface**. Adjust spot, strike, time and rate, then run. Drag to rotate the surface; it is mathematical theory over assumed spot/volatility axes, **not a downloaded options order book**.

### Example F — Tail inference

Select **Tail Risk & Inference**. Compare Historical VaR, Gaussian or Student-t assumptions, exploratory POT/EVT, Newey–West and moving-block bootstrap. EV T requires sufficient tail exceedances; QuantLab rejects underpowered samples.

## 7. Reading charts, numbers and exports

All model-lab charts are returned by the **Python research engine**. The chart itself is an SVG rendering of supplied numbers, not a placeholder image.

- **2D lines/fan**: simulated distribution paths, observed volatility forecasts and numerical convergence.
- **Bars**: portfolio weights, component importance, covariance estimator differences.
- **Heatmaps**: observed correlation matrix for the selected sample.
- **3D surfaces**: option-price response across assumptions, or hypothetical correlation stress with observed marginal volatilities.
- **Tables**: exact values; capped in-browser for readability.
- **JSON export**: the request's validated parameters, model identity, source lineage, output metrics and plotted observations. Each successful model run is also automatically archived in the Git-ignored \`results/model_laboratory/\` folder, accessible via **Saved model runs** in the same laboratory panel. Retain exports alongside experiment notes.
- **CSV export**: data rows when present or named metrics otherwise.

If the selected model is classified as **synthetic/theoretical**, changing the dataset selector does not make it historically calibrated. The run response explicitly states that the dataset was not used.

## 8. Data integrity, risk and research limitations

A reproducible **mathematical implementation** is different from an independently validated **trading result**.

1. Correct historical index membership: verify event sources and delisted/renamed instruments.
2. Adjusted prices: splits, dividends, rights and corporate actions.
3. Benchmark: price index and TRI are not interchangeable.
4. Calendar completeness: check timestamp order, missing trading sessions, duplicate bars, holidays, and session boundaries.
5. Survivorship and liquidity: exclude future membership knowledge and account for actual tradability.
6. Inference: use separate training, validation and final holdout; avoid repeated tuning on a final test.
7. Costs: account for spread, fees, market impact and execution timing.
8. Stochastic assumptions: distinguish simulated physical paths, risk-neutral pricing, and observed return calibration.
9. Evidence: keep instrument master hashes, dataset provenance, model parameters, code revision and run logs.

No live trading, execution order endpoints, broker write capability, or historical market depth reconstruction is claimed.

## 9. Troubleshooting

**Engine Offline**: Verify `bash run.sh` is running and `curl -i http://127.0.0.1:8765/api/health` returns HTTP 200.

**Dhan HTTP 401**: Refresh the short-lived token in local `.env`, restart Python, then use **Verify Dhan API access**. A token existing in `.env` does not prove it is valid. An exported environment variable can override the `.env` value; use `unset DHAN_ACCESS_TOKEN` before restart if needed.

**Missing index stocks**: Refresh the compact Dhan master with canonical trading symbols. Old batches freeze an instrument selection; create a fresh one after catalog correction.

**Dataset not in Data Manager**: A downloaded batch must be prepared. Open completed batch → Prepare research dataset. The prepared dataset is a different local artifact from the raw candle cache.

**Files complete but unverified**: Expected for Dhan price-index only research. Review benchmark provenance and missing adjustment evidence.

**Model requires more observations**: Use daily_prices.csv or a longer historical period; do not fabricate observations or turn empty months into zeros.

**3D chart missing**: 3D graphs appear when selecting a 3D model and running it, not for every 2D model.

**Mathematical notebook vs workstation**: Legacy `main.ipynb` and Streamlit are historical artifacts. Use the React/Vite + FastAPI workstation for this guided workflow.

## 10. Project docs, API and testing

- In-app **User Guide & Documentation** is searchable.
- **API documentation**: `http://127.0.0.1:8765/api/docs`
- **Model catalog**: `GET /api/lab/catalog`
- **Dataset readiness**: `GET /api/lab/readiness?dataset_id=...`
- **Model run**: `POST /api/lab/run` with a registered `model_id` and bounded `params`.
- **Repository references**: `docs/MODEL_LABORATORY_GUIDE.md` and `docs/QUANTLAB_REPRODUCIBILITY.md`.

Run the offline test suites with `python -m unittest discover -s tests -v` and the React typecheck/build with `npm run build`. CI also checks the development branch. Never include `.env` or market data caches in Git commits.

---

**Resume statement policy:** Only list algorithms implemented, tests passed, datasets actually validated, and research results supported by reproducible evidence. A passing mathematical unit test is not evidence of significant trading performance.
