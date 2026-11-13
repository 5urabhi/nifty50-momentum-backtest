# QuantLab — Multi-Factor Equity Index & Quantitative Risk Research

**Local-first React/Vite + FastAPI/Python research workstation.** Factor indices,
stochastic and portfolio mathematics, historical source management, risk
attribution, visual experiments, reproducibility and publication tooling.

**Release scope (November 13, 2026):** software and synthetic-browser acceptance
are tested. **No independently validated NIFTY historical investment result is
published.** Real TRI, point-in-time constituents, historical filings, dividends
and other corporate events still require an original-source audit.

## Fast status (default: OK / NOT READY / ERROR)

The doctor prints a **short, readable status**, never a wall of JSON or
step-by-step instructions. It saves the optional detailed report separately.
Run this from the repository with the local `.venv` activated:

    python scripts/quantlab_finish.py doctor

This automatically creates a new timestamped report folder and prints
`QUANTLAB DOCTOR: OK`, `HISTORICAL RESEARCH: NOT READY` (or the actual
readiness state), the missing inputs, and the next action. Use `--json`
only if you need machine-readable output. Full methodology, evidence
and instructions remain in the generated `NEXT_ACTIONS.md` file.

## Final research handoff: one command to see exactly what remains

The new [final study handoff guide](docs/FINAL_STUDY_HANDOFF.md)
provides copy-paste Ubuntu commands for Dhan history, authentic NSE TRI,
historical member and corporate-action records, and independent review.
[Research data-request template](docs/NSE_DATA_ACCESS_REQUEST.md).

    python scripts/quantlab_finish.py doctor \
      --data-dir data/research_v1 \
      --config config/research_multifactor.json \
      --output-dir results/my_first_doctor

The doctor creates an immutable research-evidence HTML/JSON/academic-paper
draft and, importantly, NEXT_ACTIONS.md listing the specific missing
historical files. The separate **assemble** command joins authorized
source stages without inventing observations, preserves source SHA-256s,
the frozen configuration, and synthetic-data warning markers.
**legacy-audit** gives an actual numeric assessment of the old static
49-security 2012–2025 CSV; it is NOT a PIT NIFTY research result.

## Run on Ubuntu

    cd ~/Desktop/codes/quantlab
    git switch main
    git pull --ff-only origin main
    source .venv/bin/activate
    bash run.sh

The directory above is the recommended fresh clone name. If you use a
different local folder, change only the `cd` path. The local Python
environment `.venv` is created and activated per checkout, not committed
to GitHub. On Ubuntu with Python 3.14+:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt

You only need to create/install the environment once per checkout.

Open http://127.0.0.1:5173. The local Python engine reads broker tokens only
from the ignored local environment. QuantLab does not submit trading orders.

## Start a research study

### 1. Learn the workstation
- [Five-minute researcher tour](docs/START_HERE_RESEARCHER.md)
- [Research Workspace guide](docs/RESEARCH_WORKSPACE_GUIDE.md)
- [Index research and mathematical explanations](docs/INSTITUTIONAL_MODELING.md)
- [Python SDK and Jupyter](quantlab_sdk)
- [Reproducible NIFTY study design](docs/CASE_STUDY_NIFTY_MULTIFACTOR.md)

### 2. Prepare historical data

**New original-source import workflow:** [Complete authentic NIFTY evidence and
calendar reconciliation](docs/NIFTY_SOURCE_COMPLETION.md) explains how to
download NSE historical weight snapshots, align observed Dhan month closes to
the official TRI calendar WITHOUT altering observations, and generate
security-by-security missing-data remediation reports. Source data remain local.

Inside Data Library, use the local read-only Dhan manager and upload source
evidence. Monthly stock price observations and a current instrument master do
not establish a dividend-reinvested, historically investable NIFTY index.

[Historical data guide](docs/EMPIRICAL_DATA_GUIDE.md) describes NSE index
notices, TRI exports, primary financial filings, dividend adjustments,
delistings, effective-dated sectors and explicit data licenses.

### 3. Inspect release readiness

    python scripts/research_release.py \
      --data-dir data/research_v1 \
      --config config/research_multifactor.json \
      --output-dir results/release_check_001

Even without input data, this generates an **immutable, actionable missing-source
report**. It never silently fills absent evidence. A nonzero CLI exit means
the empirical software inputs are not ready.

### 4. Run the three research studies when legitimate sources exist

    python scripts/research_release.py \
      --execute \
      --data-dir data/research_v1 \
      --config config/research_multifactor.json \
      --output-dir results/study_release_001

Study A: source-dated multi-factor index and frozen holdout; study B:
benchmark-relative systematic and specific risk; study C: robustness,
look-ahead-contaminated universe counterfactual and source integrity.
Outputs include status JSON, local HTML research report, study artifacts,
and a source-safe ZIP. **An output file is not an empirical certification.**

### 5. Inspect benchmark and create a demonstration

    python scripts/benchmark_research.py \
      --assets 50,100,300 --periods 120 \
      --output results/software_scalability.json

These are **measured synthetic CPU and memory** workloads, not actual market
performance or NSE investability evidence.

[Recording an evidence-labeled local tour](docs/SHOWCASE_AND_VIDEO.md)
documents how to create a local WebM recording with Playwright (no real data
or brokerage transactions required). A recording is not silently uploaded
or published.

## Workstation modules

- Research Index Studio: Momentum, Value, Quality, Size, Low Volatility,
  sourced Yield; selection and constraints; target weights and factor reasons.
- Conditional benchmark-relative optimization: source-dated benchmark
  weights and strictly prior covariance; sector/name/trade/turnover/TE limits.
- Capacity & modeled trading costs: source-dated ADV, spreads and explicit
  participation/impact scenarios. Never described as actual fills.
- Research explainer: Beginner, Researcher and Mathematical views tied to
  archived model calculations and input SHA-256.
- Evidence Passport and preregistered hypotheses: explicit source blockers,
  no automatic claim of independent review.
- Plots, experiments, comparison and results libraries: saved 2D/3D figures,
  models, archives, project notebooks, mathematical and statistical workflows.
- Read-only local Dhan history management with user-confirmed extensions;
  no broker orders, no public credential exposure.

## Authoritative status and limits

[Canonical release and evidence status](docs/QUANTLAB_STATUS.md).
[Source-verified research and release commands](docs/THREE_STUDIES_RESEARCH_ACCEPTANCE.md).
[Software/browsers tests](.github/workflows/workstation-ci.yml).

Historical membership reconstructions from third parties are not official NSE
certifications. Vendor or user-supplied data require an independent source
audit and legal review. A matching checksum proves file identity, not accuracy.

**Legacy notebooks and instructions** are archived in
[the original README](docs/archive/README_legacy_20261113.md) and
[legacy momentum documentation](docs/LEGACY_MOMENTUM_README.md). Their
branch names, Streamlit launcher commands and historical performance figures
are not the current release instructions or validated investment claims.
