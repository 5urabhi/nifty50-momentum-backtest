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
| DhanHQ | Token status, instrument-master refresh/search, validated read-only daily/intraday OHLCV download | Connected |
| Dhan monthly prepare | Convert a daily downloaded dataset to month-end observed closes | Connected; still missing benchmark and PIT membership |
| Index research | Real Python backtest with factor mix, top-N, cap, cost, execution lag, holdout dates | Connected |
| Factor laboratory | Saved rank IC and exposure tables from executed runs | Connected where artifacts exist |
| Index construction | Post-rebalance portfolio weights and HHI/concentration | Connected where artifacts exist |
| Index comparisons | Saved methodologies and transaction cost sensitivity | Connected where artifacts exist |
| Rolling validation | Stored rolling relative metrics | Connected where artifacts exist |
| Risk / robustness | Real saved concentration, rolling and sensitivity tables | Connected where artifacts exist |
| Visual validation | Normalized cumulative return and benchmark plot from run CSV | Connected |
| Quantitative models | Annualized covariance, minimum variance weights and historical tail loss | Connected |
| Research reports | Generate and download reproducible HTML/PDF drafts and source artifacts | Connected |
| Advanced math library | Additional existing Python mathematical functions | **Not yet exposed individually in React** |

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

Dhan downloads are saved under `data/dhan/raw/download_<id>/`.
Use the returned download ID on the same Dhan page to prepare a separate
monthly price dataset. That dataset will remain **incomplete** for backtesting
until separately sourced historical membership and benchmark evidence exist.
No attempt is made to fabricate those files.

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
