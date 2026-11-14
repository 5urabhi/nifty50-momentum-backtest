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
6. **Audit authentic NIFTY evidence.** In **Experiment Studio → Historical evidence**, QuantLab now displays the exact missing eligible security-months, next-month return gaps, unresolved historical tickers, incomplete calendar months, preferred **+20%** training-buffer shortfall, official NSE source starting points, and source-specific import/download actions. Choose **Export missing-source ZIP** for a portable request/review package; it contains **identifiers and checksums, not licensed price rows or credentials**. Import authorized exports, then choose **Recheck dataset**. This report never grants source approval.
7. **Manage the library.** Research Workspace supports archive, recoverable Trash, restore, report export, and protected source dependencies. Do not delete original Dhan history to hide an old result.

## Official NSE data is inside the app — no terminal commands

Open **Data Library → NSE Sources** (or **Experiment Studio → Historical evidence →
NSE Source Assistant**). Choose **Corporate actions**, **Stock prices**,
**Find a stock**, or **Index context**. Enter the symbol and date, then press
**Check NSE source**. The local Python API automatically uses the official NSE
MCP tool and presents the returned evidence, warnings, or a clear provider error.
You do **not** need to install an MCP client, type Python commands, or provide a
broker token for these informational checks.

For authorized downloaded NSE CSV/ZIP/XLSX/PDF files, use **Prepare NSE reports
inside QuantLab → Choose downloaded source files → Prepare source files**. The
app preserves originals and creates an unverified source receipt and an initial
weightage manifest, without replacing any saved TRI or research dataset.

If NSE's corporate action service reports an error embedded in a JSON text
message, QuantLab now shows **source unavailable**, never *zero events*. For a
stock-price check it tries the official corporate-action check first and warns
if events cannot be confirmed. NSE MCP responses are not automatically used for
trading, backtests, or licensed research data. The existing Dhan data manager
remains the research-price download workflow.

## Advanced optional command-line source tools

The following scripts remain available to developers, but are **not required**
for routine QuantLab research.

## Automate source intake without website scraping

You already may have a NIFTY TRI benchmark. Check it before importing anything:

    python scripts/quantlab_nse_sources.py status

A single command safely processes authorized local NSE ZIP/CSV reports:

    python scripts/quantlab_nse_sources.py intake "$HOME/Downloads/NSE/original_report.zip"

For information-only lookups, the script supports **NSE's official MCP
servers**, which are designed for AI clients (tools include historic OHLCV
and corporate action information). Discover available tools with:

    python scripts/quantlab_nse_sources.py mcp-tools --server bhavcopy

These are NOT approved sources for automated research simulation or raw-data
redistribution. Both NSE and NSE Indices ban systematic website scraping
without appropriate permission, so this project does not implement it.
Read [NSE compliant source automation](docs/NSE_AUTOMATED_SOURCE_WORKFLOW.md)
for the supported integration, restricted scope and complete commands.

## Collect useful official NSE data now (without waiting for an application)

Open **Experiment Studio → Historical evidence → Public NSE reports you can collect**.
This is a navigational guide to exchange pages, not an automatic scraper. You can
start gathering records from the public pages, subject to their terms and date
coverage, while the separate research-data access request is under review.

1. **NIFTY 50 TRI:** In the NSE Indices Historical Data page, select **Total returns Index Values → NIFTY 50**, set the period including a prior month-end level, and save its original CSV. When a dataset has genuine **prices + historical membership** and lacks a benchmark, use **Data Library → Add TRI** to create a new immutable version. The source is not independently verified by a successful import.
2. **Historical weights:** In **Monthly Reports**, get the Market Capitalisation / Weightage / Beta ZIPs for your study months. Keep each original and its publication date. The existing `import_nifty_weight_snapshots` importer requires a dated source manifest; a current weights file is not historical membership.
3. **Equity close / volume:** In **NSE All Reports**, use **CM-UDiFF Common Bhavcopy Final (ZIP)** for modern daily sessions, or the corresponding older historic reports. NSE notes an older common bhavcopy format was discontinued on **July 8, 2024**. Compare exact session closes, traded volume and symbols with Dhan rather than treating unadjusted prices as dividend-inclusive stock wealth.
4. **Historical membership & actions:** Use original dated NIFTY reconstitution notices, issuer corporate actions and financial result filings. Record first-publication dates and every dividend/delisting outcome before calculating factor returns.
5. **Extra granular analytics:** **Data for Research** has an applicant request path. **Data for Analytics / NSE Data Room** is a separate research-grant proposal process; it is not an unrestricted free download. Both require appropriate permissions and license review.

The source-worklist ZIP now includes **OFFICIAL_SOURCE_GUIDE.csv**.
No raw licensed data or broker credentials are bundled, and viewing a public
download does not automatically authorize publishing a derived financial index.

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
