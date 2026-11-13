# QuantLab — Canonical Release and Empirical Evidence Status

Last software review: **November 13, 2026**. This is the authoritative status
register; older archived Streamlit/branch-specific status documents are not.

## Acceptance matrix

| Capability | Software | Genuine historical NIFTY evidence |
| --- | --- | --- |
| React/FastAPI workstation and local dataset manager | CI and Chromium tested | Dhan entitlement needs user-local access |
| Multi-factor Index Studio and constraints | Implemented | Actual PIT and dated factor inputs pending |
| Benchmark-relative optimization | Implemented | Real dated benchmark weights pending |
| Sourced Yield and source-vintage fundamentals | Implemented | Original filing and payout record review pending |
| Factor/specific active-risk estimation | Implemented | Authentic factor returns and weights pending |
| Capacity, spread and square-root market impact | Implemented | Historical ADV/spreads and cost assumptions pending |
| Explainability/Graph Studio/Data Passport | Implemented | Source truth and independent reproducibility pending |
| Immutable research releases and three study pipelines | Implemented | Actual untouched empirical holdout not completed |
| Python SDK, Jupyter, saved calculations, replay | Implemented | Authorized source access for external reviewer pending |
| Synthetic large-universe CPU/memory benchmarks | Bounded script and CI artifact | Does not demonstrate exchange data accuracy |
| Local demonstration video generation | Opt-in recorder available | Actual video must be recorded and reviewed |
| Resume/public abstract and methodology drafts | Source-safe wording available | No independently validated factor-alpha metric |
| Production NIFTY research publication | Methodology and release tools ready | NOT complete; independent review required |

Software verification source: GitHub Actions on main, CI workflows
[Python/React](../.github/workflows/workstation-ci.yml) and
[Ubuntu Chromium](../.github/workflows/workstation-browser-smoke.yml).
Review the most recent workflow SHA before claiming an individual release
passed. CI uses deterministic synthetic fixtures, not audited NSE results.

## Source-assembly upgrade (research inputs)

QuantLab now has source-preserving month-end calendar alignment, a first
publication date-lagged official monthly weight snapshot importer, reconstructed
PIT membership disagreement reporting, and exact missing security-month
coverage. These tools address input *integration*, not independently establish
original NSE data completeness. See
[Authentic NIFTY Data Completion](NIFTY_SOURCE_COMPLETION.md).

## Why empirical research is still blocked

A complete valid historical NIFTY study requires:

1. Original effective-date NIFTY membership notices and security identities,
   including removals/renames, audit of existing third-party reconstruction.
2. Fully sourced stock total returns and corporate actions: ex-dividend
   cash, split/bonus handling, rights/mergers, delisting recovery and suspensions.
3. Official NIFTY 50 Total Returns Index levels with actual previous-month
   close and compatible calendar and return convention.
4. As-first-published NSE financial results and historical market caps for
   fundamental factors, including documented revisions and announcement time.
5. Date-effective sector classifications, benchmark weights, factor returns,
   and historically observed ADV/spread data for advanced studies.
6. A preregistered model protocol, genuinely untouched later holdout and
   independent original-source/implementation review with licensing permission.

No synthetic dataset, modern constituents list, spot index candle, historical
close alone, source URL, checksum or user-submitted review flag can substitute
for these observations. The application explicitly marks them missing.

## NSE index-data rights

NSE's Data Sharing & Usage Policy may restrict creating a new index from
subscriber market data and redistribution of derived datasets. The official
research application path is
https://www.nseindia.com/static/research/initiatives-data-for-research
(request form via nseri@nse.co.in). Source download availability is NOT
index-creation or publication permission. Confirm intended noncommercial use
and obtain any necessary license before publishing a research product.

## Primary sources to acquire permitted exports

- Exchange TRI levels: https://www.niftyindices.com/reports/historical-data
- NSE Indices index membership schedules and methodology:
  https://www.niftyindices.com/resources/index-rebalancing-schedule
- NSE Indices monthly capitalisation/weightage archives:
  https://niftyindices.com/reports/monthly-reports
- Original NSE index announcements:
  https://www.niftyindices.com/Press_Release
- NSE company announcements and corporate actions:
  https://www.nseindia.com/companies-listing/corporate-filings-actions
- NSE financial results:
  https://www.nseindia.com/companies-listing/corporate-filings-financial-results
- Securities master/volume archives:
  https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives

Some pages are interactive and rights-limited. Do not bypass authentication
or mass-download against a provider's terms. Save authorized raw source
files outside git; commit only legally shareable structured summaries.

## One-command missing-data and evidence report

    python scripts/research_release.py \
      --data-dir data/research_v1 \
      --config config/research_multifactor.json \
      --output-dir results/research_evidence_report_001

Produces a source checklist with official acquisition starting points,
SHA-256 inventory, internal audit (when possible), immutable HTML memo,
research evidence JSON and source-safe ZIP. Add --execute only after all
required statistical inputs and a genuinely frozen protocol are supplied.

## Publication and resume policy

The repository demonstrates implemented software mathematics, engineering,
testing, provenance controls and scientific communication. It does NOT
support claims of audited NIFTY annualized alpha, market-adjusted Sharpe,
historically invested capital, exchange-certified membership, or realized
execution quality. Any final paper must cite original licensed evidence,
actual code and reproducible results and clearly separate exploratory from
predeclared analysis.

A future reviewer may declare evidence complete, but the software will
still mark external independent certification as NOT established until a
separate manual review and public claim approval. This is intentional.
