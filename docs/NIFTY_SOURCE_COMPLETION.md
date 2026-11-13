# QuantLab — Completing Authentic NIFTY 50 Historical Research

**Status: source-integration tools implemented; actual exchange evidence still requires original licensed downloads and independent review.**

This guide closes the gap between source-correct QuantLab software and a
defensible historical multi-factor NIFTY study. No ticker, historical weight,
dividend, filing, or index level is fabricated by these utilities. They read
local files only; no order submission, token sharing or scraping of an
authenticated NSE portal occurs.

## 1. Obtain original records legally, then preserve them privately

The following first-party NSE and NSE Indices reports are the preferred
starting points (some are interactive, rate-limited or licensed):

| Actual evidence | Official first-party starting point | Why it matters |
| --- | --- | --- |
| Historical NIFTY 50 membership and monthly weight snapshots | https://www.niftyindices.com/reports/historical-data | Choose **Archives of Daily/Monthly Reports → Market Capitalisation, Weightage, Beta for NIFTY 50 & NIFTY Next 50**. Monthly files can identify members/weights, but publication time must be reviewed. |
| NIFTY 50 dividend-inclusive benchmark | https://www.niftyindices.com/reports/historical-data | Choose **Total returns Index Values**; export at least ONE MONTH BEFORE your first intended research month. |
| Original reconstitution announcements | https://www.niftyindices.com/Press_Release | Verify the exact effective date of additions and removals, including renamed/delisted companies. |
| Equity corporate actions | https://www.nseindia.com/companies-listing/corporate-filings-actions | Obtain ex-dates and published split, bonus, dividend, delisting and special event evidence. |
| Published financial results | https://www.nseindia.com/companies-listing/corporate-filings-financial-results | Record first-public dates and historically contemporaneous capitalisation. |
| Equities trade/notional data | https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives | Dated historical volume/ADV source used for capacity and impact scenarios. |

A current NSE constituents CSV is NOT a substitute for past membership.
Dhan's current master does not contain historical delisted identifiers.
Data availability and licensing must be confirmed before a public paper.

Keep the authentic source files in ignored LOCAL directories. Commit code and
non-identifying derived acceptance summaries only; licensed raw source rows
need redistribution permission.

## 2. Inspect the exact holes in your own local research data

You can audit a partial dataset; it does not need a valid benchmark yet.

    python scripts/prepare_research_data.py coverage-audit \
      --data-dir data/dhan/monthly_research/LOCAL_BATCH_ID \
      --config config/research_multifactor.json \
      --output-dir results/source_coverage_001

Outputs:
- SOURCE_COVERAGE.json: numeric source and PIT status, prevalidation history,
  future-return gaps, benchmark alignment, 20% preferred buffer, factor vintages.
- MISSING_SECURITY_MONTHS.csv: exact missing ticker-month eligibility and
  following-period wealth values. Missing historical names must be identified,
  not silently removed.
- SOURCE_REMEDIATION.md: readable remediation actions and limitations.

The output directory must not already exist. The +20% buffer is preferred
extra training/diagnostic history, not a substitution for untouched test data.

## 3. Prepare genuine dividend-inclusive individual stock wealth

Original Dhan daily closes are stock PRICE observations, not complete
dividend-reinvested research returns. Use independently reviewed original
corporate-action records and the correct vendor adjustment basis:

    python scripts/prepare_research_data.py total-returns \
      --raw-dir data/dhan/raw \
      --instruments data/dhan/instruments.csv \
      --actions data/sources/corporate_actions.csv \
      --price-basis split_bonus_adjusted \
      --output-dir data/stock_total_returns_stage_001

The existing importer handles sourced splits, bonuses, dividends and terminal
cash, but explicitly blocks complex rights/mergers/spinoffs and undocumented
payouts. An EMPTY event ledger is NOT evidence that no actions occurred.
Review all symbols, delistings, income basis, share identity and source license.

## 4. Prepare official TRI before aligning the price calendar

Use the verified official NIFTY 50 TRI downloaded separately from NSE Indices:

    python scripts/prepare_research_data.py benchmark \
      --source data/sources/NIFTY50_TRI_ORIGINAL_EXPORT.csv \
      --date-column "Date" \
      --level-column "Total Returns Index" \
      --index-name "NIFTY 50 TRI" \
      --return-convention gross_total_return \
      --output-dir data/nifty_tri_stage_001

**Replace the date/value column names with the ACTUAL downloaded headers.**
The original TRI source needs a real price level in the month before the
first study month. The importer never invents a first zero return.

If stock observations are stamped with the last observed trading SESSION
(e.g. March 28) but TRI returns with calendar MONTH END (March 31),
do not modify economic values or forward-fill through weekends. Create a
new, auditable calendar-aligned view:

    python scripts/prepare_research_data.py calendar-align \
      --source-dir data/dhan/monthly_research/LOCAL_BATCH_ID \
      --benchmark data/nifty_tri_stage_001/benchmark.csv \
      --output-dir data/calendar_aligned_stage_001

This relabels actual observed month-close prices and samples membership on
the ORIGINAL session close, before any post-close membership change. It keeps
OBSERVED_MARKET_SESSIONS.csv and CALENDAR_ALIGNMENT_PROVENANCE.json and
rejects missing/old months or unmatched TRI data. It does NOT add dividends.
If your stock data are not yet wealth-index adjusted, complete step 3 before
treating them as comparable to TRI.

## 5. Import official historical monthly index weight snapshots

NSE's historical monthly weight reports can help cross-check the third-party
reconstructed PIT index history and supply source-weight references for Study B.

1. Download each monthly **CSV** from the official archival interface under
   your permitted use terms (extract an official ZIP locally if necessary).
2. Preserve the original file bytes and note its date and first-available
   publication date. If publication time is unknown, do not assume the
   snapshot was available at the preceding market close.
3. Create a private manifest like this. The row is a SCHEMA EXAMPLE, not an
   actual claim about a real January 2024 download:

        file,snapshot_date,published_at,source_url
        ORIGINAL_MAY_2024_REPORT.csv,2024-05-31,2024-06-03,https://www.niftyindices.com/reports/historical-data

4. Supply a stock price panel containing the FULL historical union including
   old/exited members. The importer rejects any missing historical source
   ticker rather than dropping it.

    python scripts/prepare_research_data.py nse-weight-snapshots \
      --manifest data/sources/nse_weights/manifest.csv \
      --prices data/calendar_aligned_stage_001/prices.csv \
      --weight-unit percent \
      --symbol-column "Symbol" \
      --weight-column "Weightage (%)" \
      --output-dir data/nse_weights_stage_001

Use the actual headers from the downloaded original report. For a combined
NIFTY 50 / NIFTY Next 50 report, add:
    --index-column "Index" --index-label "NIFTY 50"
and replace "Index" with the source's real column name.

The tool verifies: 50 source names, unique symbols, nonnegative/normalized
weights with small rounded-weight tolerance, full security-universe matching,
source SHA-256, chronological snapshot dates and declared publication dates.
It creates exact-universe benchmark_weights.csv with explicit ZERO weights for
securities not in the monthly source and shifts each availability to the DAY
AFTER the declared publication date, preventing unknown same-day lookahead.

Optionally provide --pit-intervals data/index_membership/nse_reconstructed_pit.csv
to compare source snapshot composition against third-party event histories.
Disagreement is reported, never fixed by guessing the true ticker alias.

**Critical distinction:** monthly snapshots are NOT original effective-date
membership change notices. These outputs do not auto-create research
membership.csv; verify actual reconstitution dates separately. Source
publication dates in the manifest are researcher-declared until inspected.

## 6. Bring in historical fundamental vintages and advanced factor sources

For Value, Quality, Size or Yield, supply first-available-date filings and
historical market caps, then use the existing filing importer. For
benchmark-relative risk, supply independently sourced factor_returns.csv and
matching benchmark_weights.csv. For capacity analysis, use dated
liquidity.csv with observed ADV and spreads in portfolio capital currency.

External source evidence is not inferred from file presence. A run blocked by
missing filings or delisted prices is better than survivorship-biased output.

## 7. Run and audit the three studies, then obtain independent review

    python scripts/research_release.py \
      --data-dir data/research_v1 \
      --config config/research_multifactor.json \
      --output-dir results/my_release_001 \
      --execute

The report includes exact source completeness, data caveats, numerical
Study A/B/C calculations where possible, an immutable manuscript draft,
local HTML and source-safe ZIP. Unknown original records remain blocked.

Independent review must reconcile original membership notices, source
publication vintages, total-return conventions, full event history,
unexplained missing securities, realistic execution and truly untouched
frozen final holdout before publication.

**NO automatic audit can independently certify source truth from only user
uploaded files or source links.**

## 8. Resume and project-showcase completion policy

Validated software and the actual source-gated workflow can be documented.
Do not claim real historical NIFTY alpha, true exchange weight replication,
independently verified Sharpe, economic capacity or broker fills until the
original research data and review evidence support them.

The interactive research video and benchmark artifacts are already on main.
Use source-verified measures rather than fictional resume performance.
