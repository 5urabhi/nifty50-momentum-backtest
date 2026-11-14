# NSE data in QuantLab: built-in source assistant

## Normal user workflow — entirely inside QuantLab

Open **Data Library → NSE Sources**, or **Experiment Studio → Historical
evidence → NSE Source Assistant**. The app automatically chooses the official
NSE MCP tool for the source task you select. Stock history checks try corporate
actions first. User-visible errors distinguish a temporary provider outage
from a confirmed event list; the latter is still not independent certification.

To prepare an authorized report, select ZIP/CSV/XLSX/PDF under **Prepare NSE
reports inside QuantLab**. The Python API stores original source hashes
and a safe manifest; no command-line script or manual ZIP extraction is needed.
The original TRI is detected and preserved.

All commands below are **optional developer tools**, not steps a user must
execute in the app.

## Advanced command-line reference

QuantLab ALREADY supports an imported TRI benchmark. Do not re-import it.
The source collector checks existing local benchmark.csv and its provenance,
including first/last observed monthly return, without overwriting anything.

## Site restrictions and supported access

- NSE India Terms, paragraph 9, prohibit systematic/automated website
  collection: https://www.nseindia.com/static/nse-terms-of-use
- NSE Indices Terms, paragraph 12, require express written consent for
  automated website collection: https://www.niftyindices.com/terms-of-use
- NSE offers official Streamable HTTP MCP interfaces for informational and
  educational use: https://www.nseindia.com/nse-mcp
- NSE Indices offers licensed original constituent data subscriptions:
  https://www.niftyindices.com/offerings/data-subscription

This CLI deliberately does NOT scrape or crawl website pages, bypass
CAPTCHAs/login, rotate IPs/cookies, or insert informational MCP results into
model training/backtests. Use licensed Dhan historical APIs and permitted
original records for research, with source-review requirements intact.

## 1 — Check which TRI is ALREADY there

From the repository root:

    python scripts/quantlab_nse_sources.py status

Or specify the derived dataset in your Data Library:

    python scripts/quantlab_nse_sources.py status --dataset-id upload_run_YOUR_ID

A properly annotated existing TRI is marked tri_present_source_unverified,
with observed monthly returns, earliest/latest date, and SHA-256 receipts.
Never upload it again just because a source checklist says TRI is needed.
Instead verify whether the already-imported time range is sufficient.

You can see all remaining source gaps using:

    python scripts/quantlab_nse_sources.py plan \
      --dataset-id upload_run_YOUR_ID \
      --validation-start 2024-01-31 --final-test-start 2025-01-31

Or open Experiment Studio → Historical evidence.

## 2 — Automatically organize already-downloaded NSE source files

Use official websites' authorized download features, or a licensed data feed,
to save original CSV, ZIP, XLSX, or PDF locally. Then:

    python scripts/quantlab_nse_sources.py intake \
      "$HOME/Downloads/NSE/monthly_weights.zip" \
      "$HOME/Downloads/NSE/original_report.csv"

The script checks safety and size, keeps the exact original bytes under
the ignored data/nse/authorized_intake directory, generates SHA-256
SOURCE_INTAKE.json receipts, and extracts valid flat CSV members without
running downloaded code or following ZIP paths.

If it finds potential constituent-weight CSVs, it writes a
WEIGHTAGE_MANIFEST_TEMPLATE.csv. You MUST fill/confirm the snapshot_date
and first published_at using actual source records. The existing strict
index_research/nse_weights.py importer enforces membership, time lag, exactly
50 constituents, and weight totals. An incomplete manifest is not approved
research data. XLSX and PDF originals are preserved but not falsely parsed.

The script never overwrites the existing TRI or original source dataset.

## 3 — Ask NSE's official MCP instead of scraping

NSE advertises two official Streamable HTTP servers:
- Bhavcopy: https://mcp.nseindia.in/bhavcopy/cm/mcp
- Cash market: https://mcp.nseindia.in/cmmkt/mcp

Discover current tool arguments:

    python scripts/quantlab_nse_sources.py mcp-tools --server bhavcopy

Example of one informational query; adjust the symbol parameter to the
schema returned by the actual server:

    python scripts/quantlab_nse_sources.py mcp-lookup \
      --server bhavcopy --tool get_corporate_actions \
      --args '{"symbol":"RELIANCE"}' --ack-informational-use

Only allowlisted tools, one call per CLI invocation. Data are printed to
the terminal, not silently saved in a research matrix. NSE states its
Bhavcopy MCP covers up to five years and get_stock_history provides up to
three months per query; it does not certify a complete 2014+ investment study.
Provider errors or rate limits are surfaced, not bypassed.

NSE's official MCP is for informational/educational purposes, not trading,
commercial deployment, or automatically authorized investment simulation.
The researcher must separately confirm permitted uses.

## 4 — Existing Dhan automation for actual research data

For authorized historic prices, open Data Library → Download market data →
NIFTY 50 Historical → Dates → Download → Prepare. QuantLab's existing
Dhan adapter already caches and resumes authorized daily data; it does not
manufacture dividend reinvestment, historical eligibility, filings or rights.

Authentic historic financial data, sector/issuer identifiers, dates and
corporate actions still need original-source and independent validation.
No script may mark a real-market study independently certified solely
because source files, MCP responses, or checksums exist.
