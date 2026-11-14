# QuantLab — Start Here

**Current interface (November 2026): React/Vite + FastAPI/Python.** This is a local-first, read-only quantitative research workstation, not a brokerage trading terminal. The older Streamlit dashboard and legacy branches are archived; do not use those commands for the current app.

## Run on Ubuntu

Open a terminal in the checkout that contains `run.sh`:

```bash
cd "$HOME/Desktop/codes/quantlab"
git switch main
git pull --ff-only origin main
bash run.sh
```

Open **http://127.0.0.1:5173** in the same Ubuntu machine. The local API normally listens at **http://127.0.0.1:8765**. Leave the launcher running while using the browser. For first-time setup, read [the main README](README.md) and [the workstation guide](REACT_WORKSTATION.md).

This guide describes the verified `main` release. Feature-branch reviewers should check out their own branch and run the same launcher before merge. The launcher may need to install Python/npm dependencies on a fresh checkout.

## Complete a research workflow

**Start with Guided Research** — the default landing page. Follow the numbered stages: **1 Select data → 2 Choose model → 3 Run → 4 Analyze → 5 Save**. The Run stage embeds the actual Python-backed Model Laboratory; Analyze opens the exact archived result in Results Studio, and Save exports an evidence ZIP with an offline checksum verifier. The guided route does not duplicate data/model engines or hide unsupported sources.

1. **Choose a research goal.** Use Guided Research for a model study, or the advanced Experiment Studio for multi-factor index construction.
2. **Select inputs.** Mathematical theory needs assumptions, not fake market candles. Historical models show actual common returns and the **minimum / preferred +20%** target for the chosen securities. Option models requiring original quotes offer read-only Dhan chain capture and CSV import.
3. **Recover missing source data.** Click **Get missing Dhan history (+20%)** when the source is mapped and extendable. QuantLab reuses SHA-verified cached candles and requests only missing date windows. For a missing TRI, corporate-action, membership or filing record, use the named source action in Data Library; spot OHLCV cannot replace these inputs.
4. **Run the model.** Inspect the exact parameters and source before running. A successful calculation is not certification of investment performance.
5. **Interpret and save.** Results Studio distinguishes synthetic, theoretical and observed-unverified evidence, with chronological holdout evidence identified separately; no source receives automatic independent certification. Check Sharpe, returns, drawdown and other reported metrics with their units. Save figures/CSV, compare compatible experiments and export the immutable source/parameter record.
6. **Manage the library.** Research Workspace supports archive, recoverable Trash, restore, report export, and protected source dependencies. Do not delete original Dhan history to hide an old result.

## What the readiness words mean

| Status | Meaning | Next action |
| --- | --- | --- |
| Mathematical / theoretical | Parameters can be evaluated without observed prices. | Run as theory; do not call paths observed. |
| Historical source ready | The selected source meets the numerical model minimum. | Run, then check validation, biases, and provenance. |
| Preferred history short | Model may run, but the preferred +20% data buffer is absent. | Extend only uncovered mapped Dhan history when available. |
| Choose a stock | Dataset-wide dates exist, but the exact model security is not selected. | Choose a named ticker, including an incomplete one. |
| Option quote required | A model needs actual quoted premium, bid/ask and expiry. | Capture a current read-only chain or import original quoted CSV. |
| Source action required | Historical evidence is not supplied by Dhan close prices. | Get original TRI, membership, dividends, filings or licensed records. |
| Incomplete after download | Vendor or local source does not have enough real observations. | Review the precise shortfall. Missing prices are never invented. |

**Note:** The additional 20% observations are a *preferred sample-size buffer*. They are not automatically a statistically independent holdout; a chronological train/validation/final-test protocol is still necessary. A checksum identifies a saved source version, not the truth of the source's prices.

## Problems and help

- **Engine offline:** Keep `bash run.sh` active; check `http://127.0.0.1:8765/api/health`.
- **Dhan token missing/expired:** Configure `DHAN_ACCESS_TOKEN` only in the ignored local `.env`, restart and use the read-only profile verification. Never commit or paste credentials.
- **Insufficient series:** Use the Model Laboratory's **Data requirements & shared history** panel. It distinguishes stock returns from dataset-wide price dates.
- **Unverified historical index experiment:** Follow [Historical Research Evidence](docs/QUANTLAB_STATUS.md) and [Final Study Handoff](docs/FINAL_STUDY_HANDOFF.md). Audited NIFTY TRI, point-in-time members and corporate actions are separate source requirements.
- **Metric definitions:** Use **Help & Settings → Metric Guide** or [Metric Reference](docs/METRIC_REFERENCE.md). A fraction such as 0.12 means 12% only for explicitly declared return-type metrics, not for beta, Sharpe or other ratios.

## Deeper references

[Researcher walkthrough](docs/START_HERE_RESEARCHER.md) · [Model Laboratory](docs/MODEL_LABORATORY_GUIDE.md) · [Research Workspace](docs/RESEARCH_WORKSPACE_GUIDE.md) · [Reproducibility](docs/QUANTLAB_REPRODUCIBILITY.md) · [Source-aware research](docs/QUANTLAB_STATUS.md).

Run the complete CURRENT workstation software acceptance with `bash run.sh check` (React/TypeScript build, Python unit/integration and mathematics checks, and a read-only historical-source doctor). For a synthetic research evaluation and 2D/3D report, use `bash run.sh evaluate`. The archived Streamlit UI is optional and is not the default acceptance path. You may also run `python -m unittest discover -s tests -v` and `npm run build` separately. GitHub Actions also executes automated Ubuntu Chromium browser acceptance. It uses isolated synthetic fixtures; it does **not** validate a user's live Dhan entitlement or original NSE data.

### Last-mile cleanup and recovery

**Jobs:** For an interrupted local calculation, select **Research Projects → Jobs → Recheck inputs & retry**. This action is available only for supported deterministic research sweeps, chronological validation, reports and learning experiments. It checks the exact saved local source bytes, edited notebook and corresponding calculation code. If sources changed, reopen the study and start a new run. Dhan reads and single-use frozen evaluations are NEVER automatically restarted.

**Data Quality:** Scan for exact duplicate prepared views. The hash includes every regular file and nested provenance record; a user-confirmed redundant copy may be moved to recoverable Trash only after rescan and dependency checks. The first copy and raw Dhan market cache remain untouched. Restore from Dataset Library if needed.

**Plot Builder:** Declare INR/₹ or USD/$ only when you know the input price currency. This is a user-supplied display declaration, not certified by Dhan or NSE. Returns remain decimal fractions (0.01 = 1%), Sharpe/beta unitless, costs in bps and wealth indices base 100. Dated 2D figures can link zoom/pan and pointers on exactly matching observed dates, never invented intermediate dates.

### Advanced research features

**Results Studio → Overfitting & regimes** provides retrospective CSCV/PBO, declared-trial Deflated Sharpe statistics, and trailing benchmark-volatility regimes for compatible saved index experiments (at least 48 aligned monthly returns; more for six/eight blocks). The calculations are exploratory, not purged CPCV or a prospectively untouched final test. See [advanced validation methods](docs/ADVANCED_SELECTION_VALIDATION.md).

**Research Workspace → Data quality** can check exact byte-identical prepared dataset views, and **Jobs** shows the bounded serial queue, safe cancellation, retry and failure recovery. Chart toolbars offer 2D date-linked crosshairs, zoom/pan/reset, with complete raw CSV exports. Saved model/index results can export portable research ZIPs from their guide or `/api/workspace/evidence-bundles/{kind}/{run_id}.zip`. The bundles do not include proprietary original data or secrets.
