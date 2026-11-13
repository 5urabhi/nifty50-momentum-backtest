## Model Laboratory and Guided Documentation (Feature Branch)

QuantLab's **Advanced Mathematics** and **Quantitative Models** now open a
shared six-family workbench with **26 registered runnable algorithms**.
Families have separate parameters, 2D/3D graph gallery, exact diagnostics,
mathematical assumptions and source provenance. The workstation draws
interactive SVG charts and draggable/keyboard-rotatable 3D surfaces from
numerical Python outputs, without remotely hosted chart libraries.

The workbench labels output as **theoretical**, **seeded synthetic**, or
**observed historical**. Historical models prefer local `daily_prices.csv`;
the API rejects inadequate common observations instead of synthesizing
missing market data. Model runs never call Dhan or place orders.

A new **User Guide & Documentation** sidebar section provides searchable
onboarding, navigation shortcuts, glossary, warning explanations, and links
to allowlisted repository Markdown served by FastAPI.

Canonical references:

- `docs/QUANTLAB_USER_GUIDE.md` — end-to-end local workstation manual
- `docs/MODEL_LABORATORY_GUIDE.md` — 26 algorithms, equations, assumptions, API
- `docs/QUANTLAB_REPRODUCIBILITY.md` — evidence/validation gates and resume wording

Local API: `GET /api/lab/catalog`, `GET /api/lab/readiness?dataset_id=...`,
`POST /api/lab/run`. Documentation: `GET /api/guide/user-guide`,
`/api/guide/model-catalog`, `/api/guide/reproducibility`. FastAPI interactive
schema remains at `http://127.0.0.1:8765/api/docs`.

Do **not** interpret these computations as audited trading results. Real-data
models are descriptive unless a named strict walk-forward calculation is
used; synthetic paths and theoretical surfaces do not establish predictive
performance. Supervised ML/RL agent training and live order execution are
not represented as completed features.

# QuantLab — React/Vite quantitative research workstation

**Primary application:** React 18 + TypeScript + Vite at **http://127.0.0.1:5173**.
**Research engine:** Python FastAPI (loopback only) at **http://127.0.0.1:8765**.
**Source branch:** `workstation/quant-research-development-20261112`.

This is a **private, personal research workstation**, not a public-facing marketing site
and not a brokerage trading client. Streamlit is retained only as a legacy fallback.
The old illustrative React showcase remains in `src/App.tsx` for reference, but the
React entry point now renders the workstation in `src/Workstation.tsx`.

## Install on another Ubuntu PC

If Git cloned a nested folder, enter the folder containing `run.sh` and `package.json`.

```bash
cd ~/Desktop/codes/nifty50-momentum-backtest/nifty50-momentum-backtest
git fetch origin
git switch workstation/quant-research-development-20261112 || \
  git switch --track origin/workstation/quant-research-development-20261112
git pull --ff-only
cp -n .env.example .env
nano .env
bash run.sh
```

**Open http://127.0.0.1:5173**, not port 8501. Ctrl+C stops the React server
and the Python API together. The startup script installs/updates Python packages
in ignored `.venv` and Node dependencies locally; then it runs a TypeScript
production build before serving. No Redis/Docker required.

Subsequent launches need only `bash run.sh`. Use `bash run.sh legacy-streamlit`
only to inspect the original Python pages during migration. The old `bash run.sh web`
and `bash run.sh research` names now start the *same React workstation*, not
the previous showcase or Streamlit interface.

## Troubleshooting: Dhan HTTP 401 and incomplete historical index mappings

If a batch pauses on `Dhan HTTP 401`, use **Dhan Market Data → Verify
Dhan API access**. The workstation checks `GET /v2/profile` without exposing
the access token or account identity. A token's *presence* in `.env` is
not evidence that Dhan accepts it. A token obtained from Dhan Web generally
expires after 24 hours; generate a fresh one at
**Dhan Web → My Profile → Access DhanHQ APIs**, update the root `.env`,
restart `bash run.sh`, and recheck token expiration and
**Data API subscription**. Free trading API access does not necessarily
include the separate market-data subscription. Dhan publishes `DH-901` for
invalid/expired authentication and `DH-902` for access/market-data
subscription problems.

Historical index membership matching uses **actual NSE trading symbols**.
The official Dhan **compact** scrip master
(`https://images.dhan.co/api-data/api-scrip-master.csv`) contains the
`SEM_TRADING_SYMBOL` column. The previous detailed scrip master does not,
and its display names should **not** be treated as canonical exchange
symbols. After updating QuantLab, click **Refresh instrument catalog**;
the backend replaces the old catalog with the compact one.

If a previous historical index batch contained only 8 mapped securities out
of 51 historical members, **do not resume that old batch**: its instrument
list is frozen at creation and reflects the old mapping. Refresh the catalog,
select historical NIFTY 50/BANK NIFTY again, review the fresh mapping counts,
then **create a new batch**. Some genuinely delisted/renamed historical symbols
can still be unresolved. Those need independently reviewed historical ID
mapping and should not be silently substituted.

### Verification on the target Ubuntu PC

```bash
cd ~/Desktop/codes/nifty50-momentum-backtest/nifty50-momentum-backtest
git switch workstation/quant-research-development-20261112
git pull --ff-only
bash run.sh
```

In the React UI, click **Verify Dhan API access**, then
**Refresh instrument catalog**. When both succeed, select a small
historical index range and launch a fresh batch. No order endpoints are used.

## API tokens

Edit **project root** `.env`, not `src/.env`:

```dotenv
DHAN_ACCESS_TOKEN=YOUR_DHAN_TOKEN
```

Restart the workstation after editing. The Python process reads this variable;
React only receives a boolean indicating whether a token exists. Do not put
credentials in `VITE_*` variables because those are exposed to the browser.

The API is intentionally bound to `127.0.0.1:8765`. Vite proxies
same-origin requests under `/api` so the browser does not require CORS.
The backend rejects non-loopback Host headers and unexpected Origins.
Do **not** expose either server to the public internet, a LAN, or Vercel.
There is no multi-user authentication, account isolation, or broker order API.

## Workflows currently wired to Python

| React module | Data / behavior | State |
| --- | --- | --- |
| Overview | Live API status, local dataset inventory, saved run metrics and cumulative wealth plot | Connected |
| Data manager | Synthetic demo fixture, validated research ZIP import, readiness and dataset audit | Connected |
| DhanHQ market-data terminal | Search and multiselect stocks, all current NSE/BSE EQ cash-market instruments, ticker-list CSV, daily/intraday batch download, pause/resume, status per instrument, verified cache and candle preview | Connected |
| Dhan monthly prepare | Convert cached daily batches to month-end prices; historical NIFTY batches also export explicit dated membership.csv | Connected; compatible total-return benchmark still required |
| Index research | Real Python backtest with factor mix, top-N, cap, cost, execution lag, holdout dates | Connected |
| Factor laboratory | Saved rank IC and exposure tables from executed runs | Connected where artifacts exist |
| Index construction | Post-rebalance portfolio weights and HHI/concentration | Connected where artifacts exist |
| Index comparisons | Saved methodologies and transaction cost sensitivity | Connected where artifacts exist |
| Rolling validation | Stored rolling relative metrics | Connected where artifacts exist |
| Risk / robustness | Real saved concentration, rolling and sensitivity tables | Connected where artifacts exist |
| Visual validation | Normalized cumulative return and benchmark plot from run CSV | Connected |
| Quantitative models | Annualized covariance, minimum variance weights and historical tail loss | Connected |
| Research reports | Generate and download reproducible HTML/PDF drafts and source artifacts | Connected |
| Advanced mathematics | Black–Scholes pricing and Greeks, seeded Python GBM percentile simulation | Connected |
| Remaining math library | PCA, OU/GARCH, advanced constrained portfolio engines | **Not yet exposed individually in React** |

**Important distinction:** a connected UI does not imply the research
methodology, data provenance, or outcomes are externally audited. Synthetic
data are labeled synthetic; uploaded data remain unverified. Missing data are
reported, not carried forward silently or invented. In particular Dhan OHLCV
alone cannot provide dividend-reinvested total returns, historical index
membership, corporate action completeness or independently validated benchmark
returns.

## Data and execution

Imported ZIP files require flat `prices.csv`, `membership.csv`, and
`benchmark.csv`. Optional files include `fundamentals.csv`,
`sectors.csv`, and `corporate_actions.csv`. The app validates file
names, archive size, dataset schemas and internal consistency, and writes only
beneath `data/workstation_imports`.

Python backtest jobs are scheduled on one local worker; a second job is rejected
while a prior job is running, rather than silently superseding it. Outputs are
saved under `results/workstation_runs/<UTC-id>/`. Each run retains its
`research_manifest.json`, CSV result tables, source input SHA-256 hashes,
and internal data quality diagnostics.

### Bulk Dhan data downloads

Open **Dhan Market Data** in the left sidebar. Press **Refresh instrument
catalog** after configuring a valid `DHAN_ACCESS_TOKEN` in root `.env`.
You do not need to enter numeric Security IDs manually.

You can choose **Choose stocks** (search and multi-select), **All NSE stocks**
(current Dhan NSE EQ-series equity instruments), **All BSE stocks**
(current BSE cash-market equity instruments), **Paste a ticker list**, plus
**NIFTY 50 · Historical** and **BANK NIFTY · Historical**.

**For a historical index:** Sync public reconstructed NSE membership events
from the NIFTY card. The workstation pins the exact GitHub source commit and
SHA-256, records the provenance and the official NSE Indices 2025-12-01 bank
inclusion correction, and builds the **union of all index members during the
selected date range**. Use the as-of date selector to inspect membership at a
specific historical date, or inspect adds/removals by effective date.
The Python backend matches exact unambiguous symbols to the current Dhan
master. Renamed/delisted historical companies may not have available current
Security IDs: they appear as explicit gaps and are never silently replaced.
Downloading mapped stocks despite these gaps requires separate informed
consent and never creates a fully accepted research dataset.

The independent historical source is
[aditya-jha/nse-historical-membership](https://github.com/aditya-jha/nse-historical-membership),
data released under CC0. It is reconstructed from public NSE notices, **not
endorsed or certified by NSE**; the upstream documented membership coverage is
2014-01-01 through 2026-10-13 at this revision. Pre-2018 coverage has known
gaps. The app refuses requests outside its recorded source window, instead
of treating today's stocks as historical members. A 2025-12-01 official notice
[issued by NSE Indices](https://www.niftyindices.com/Press_Release/ind_prs01122025.pdf)
sets UNIONBANK and YESBANK's additional BANK NIFTY inclusion effective
2025-12-31, correcting a dated inference in the reconstructed source.

The historical group can also request the underlying NIFTY 50 or BANK NIFTY
**spot index OHLCV** and store it under `data/dhan/index_spot/`. The backend
prefers a unique `IDX_I` / `INDEX` identity in the current official Dhan
instrument master. If that master omits index underlyings entirely, it falls
back to Dhan's *published* IDX_I reference identities, NIFTY 50 = 13 and
BANK NIFTY = 25, and records the resolution source in each batch manifest.
The reference is
[Dhan's open-source instrument guide](https://github.com/dhan-oss/dhanhq-skills/blob/main/skills/dhanhq/references/instruments.md).
Conflicting identities in the master **block** the fallback. These identifiers
are not hardcoded stock prices or historical memberships. Index spot candles
are **price-index observations**, not a dividend-reinvested TRI benchmark.

PIT monthly preparation now labels each row using the last **observed NSE
cash-market session** of the month, not a synthetic calendar month-end.
A historical constituent missing the actual final session keeps a missing
value (no silent forward fill), and its prepared dataset is flagged **not ready**.
The observed session calendar itself is inferred from Dhan candle timestamps,
not independently verified against the official NSE holiday calendar.

Choose the inclusive start date, exclusive end date and candle resolution
(daily/1/5/15/25/60-minute through the Dhan API). There is **no arbitrary
100-instrument limit on intraday downloads**. Batches above 100 instruments
require an explicit scope acknowledgement, not a rejection. The Dhan V2
historical API documents up to five years of minute candles for active
instruments, and **a maximum of 90 calendar days per intraday request**.
The workstation automatically divides longer date periods into sequential
90-day windows. It writes and checksums each successfully retrieved window
before requesting the next one. When paused or interrupted halfway through
a stock, **Resume/retry** skips successfully cached date windows.
The workstation displays per-stock date-window progress, approximate calls,
and completed/cached/failed/no-data counts. Dhan's account entitlements,
API-rate limits (consult current official limits), supported instrument
history and local disk capacity remain real external constraints.
The app keeps sequential calls at a conservative pace and retries eligible
temporary HTTP errors using bounded backoff. It does not bypass vendor limits.

Persistent paths:

- `data/dhan/instrument_master.csv` — official Dhan master snapshot.
- `data/dhan/history/<exchange>/<security_id>/<resolution>.csv` — canonical
  locally cached, de-duplicated candles with SHA-256 provenance sidecar.
- `data/dhan/batches/batch_<id>/manifest.json` — batch selection, source
  master SHA-256, dates, counts and each security's download status.
- `data/dhan/monthly_research/batch_<id>/prices.csv` — optional, unadjusted
  observed month-end closing prices, restricted to requested dates.
- `data/dhan/monthly_research/batch_<id>/membership.csv` — for a historical
  NIFTY group, explicit True/False membership at each observed final trading
  session of the month, never a made-up weekend market close.
- `data/dhan/monthly_research/batch_<id>/PIT_MEMBERSHIP_PROVENANCE.json` —
  pinned source, effective intervals, unmapped members, missing eligible prices,
  date coverage, official source corrections and audit warnings.
- `data/index_membership/nse_reconstructed_pit.csv` — verified-hash local
  copy of reconstructed NSE membership intervals, downloaded on user sync.
- `data/dhan/index_spot/batch_<id>/` — optional independent index OHLCV
  with vendor source metadata (not total-return index history).

Only candles in missing requested date windows are fetched. Previously saved
covered ranges are reused after validating the file digest and instrument
identity, and new candles are merged chronologically. A failed instrument does not discard previously saved completed date windows
for the **same** instrument or successfully fetched instruments. Failed/empty
names are explicitly reported instead of silently represented as zero prices.

The Python Dhan adapter only calls historical-data endpoints. Its existing
read-only single-instrument route is retained for backward compatibility
but is no longer used by the main React page.

**Research limitation:** The historical NIFTY modes supply dated membership
without fabricating additions/exclusions, but cannot guarantee data for
renamed or delisted constituent symbols. A prepared historical dataset with
unmapped constituents or missing eligible market prices is explicitly **not
ready**. Even when the membership is complete, index backtesting requires a
compatible independently sourced total-return benchmark (and independently
reviewed corporate-action/delisting evidence). No broker API is presumed to
provide an adjusted TRI benchmark.


## Verification on your Ubuntu machine

```bash
bash run.sh setup
./.venv/bin/python -m unittest tests.test_react_workstation_api -v
./.venv/bin/python -m unittest discover -s tests -v
npm run build
bash run.sh
```

If the Python smoke test cannot import the package as a standalone test module,
run `./.venv/bin/python -m unittest discover -s tests -p 'test_react_workstation_api.py' -v`.
After launching, `curl http://127.0.0.1:8765/api/health` should report
`"ok":true`. Once running, create a labeled synthetic dataset, run a
research experiment, and inspect Saved Runs and Research Reports.

**Validation status:** These files were authored on the feature branch,
but a local frontend build and complete end-to-end test execution must still
be performed on the target PC before this migration is considered approved.
Do not merge or deploy as a public app until verified.


## Results Studio: statistical evidence (November 2026)

In **Results Studio**, select a saved run and open **Evidence audit**.
For an index run with 24+ paired monthly observations, the Python engine
computes source-bound net-return risk, loss-distribution and rolling-risk
figures, a seeded circular moving-block 95% uncertainty interval, and
Newey–West HAC descriptive inference. Short or incomplete data produces an
explicit blocked state, never a simulated confidence interval. Model runs
expose archived numerical metrics and the correct theoretical/synthetic/
observed-unverified source classification without claiming a prospective test.

Choose **Compare runs**, select 2–8 compatible saved index runs (the first
selected becomes baseline), then press **Calculate paired evidence**. The
backend requires equal source-file checksums, dataset ID, shared calendar and
benchmark, followed by a paired monthly comparison with Holm-adjusted nominal
p-values and deterministic block-bootstrap intervals. Use separate plot panels
for incompatible math/simulation families. Download Evidence JSON and the
relevant CSV or SVG alongside the research notebook's original report.

Read **docs/METRIC_REFERENCE.md** before interpreting intervals or p-values.
Source hashes, bootstrap intervals, and declared holdouts are useful audit
evidence but **not independent vendor/source verification, an audited market
index, live fills, or a publication-level positive result**.

API:
- `GET /api/workspace/results/model_run/{run_id}/evidence`
- `GET /api/workspace/results/research_run/{run_id}/evidence`
- `POST /api/workspace/results/paired-comparison` with
  `{"baseline_id":"run1","challenger_ids":["run2"]}`

Synthetic fixture-only acceptance:
`python -m unittest tests.test_result_evidence -v`.


## Historical source completion: guided UI

The **Experiment Studio → Historical Evidence Workflow** now handles the
last-mile steps missing from a basic chart dashboard: show exact market-data
and PIT/benchmark/event gate results; link to daily-history downloads and
TRI uploads; import a source-cited ex-date dividend/split/delisting event
ledger into a **new, non-destructive total-return dataset version**; and lock
one observed study's source files, parameters and train/validation/final
dates before consuming the frozen protocol once. The status board never
automatically claims independent market-data or publication certification.

The Results Studio **Evidence audit** identifies whether its index run was
actually bound to a valid one-use frozen receipt. Missing/modified data,
insufficient 44/1/12 training/validation/final months, incomplete PIT states,
unadjusted spot benchmarks, unsupported events and publication-vintage gaps
have explicit remediation actions.

**Sources still required from original providers:** licensed Dhan (or user)
historical daily closes, effective-dated NSE index circulars with all
historical identities, issuer action/ex-date records and delisting recovery,
correct first-release financial filings and comparable NSE Indices TRI
levels. No backend can manufacture those source truths or independently
approve its own research assumptions.
