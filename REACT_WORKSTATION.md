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
(daily/1/5/15/60-minute). Batches above 100 instruments require a clear
acknowledgement; intraday batches are limited to 100 instruments. The
workstation shows approximate API calls, progress, successful/cached/failed/
no-data counts, optional cancellation after the current request, and
**Resume/retry**. A restarted workstation retains manifests and previously
completed candles.

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
identity, and new candles are merged chronologically. A failed instrument
doesn't discard successfully fetched instruments. Failed/empty names are
explicitly reported instead of silently represented as zero prices.

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
