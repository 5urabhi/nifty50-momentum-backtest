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

1. **Choose a research goal.** Open Model Laboratory for stochastic models and financial mathematics, or Experiment Studio for index/factor studies.
2. **Select inputs.** Mathematical theory needs assumptions, not fake market candles. Historical models show actual common returns and the **minimum / preferred +20%** target for the chosen securities. Option models requiring original quotes offer read-only Dhan chain capture and CSV import.
3. **Recover missing source data.** Click **Get missing Dhan history (+20%)** when the source is mapped and extendable. QuantLab reuses SHA-verified cached candles and requests only missing date windows. For a missing TRI, corporate-action, membership or filing record, use the named source action in Data Library; spot OHLCV cannot replace these inputs.
4. **Run the model.** Inspect the exact parameters and source before running. A successful calculation is not certification of investment performance.
5. **Interpret and save.** Results Studio distinguishes synthetic, theoretical, observed-unverified and genuinely held-out evidence. Check Sharpe, returns, drawdown and other reported metrics with their units. Save figures/CSV, compare compatible experiments and export the immutable source/parameter record.
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

Run offline checks with `python -m unittest discover -s tests -v` and `npm run build`. GitHub Actions also executes automated Ubuntu Chromium browser acceptance. It uses isolated synthetic fixtures; it does **not** validate a user's live Dhan entitlement or original NSE data.
