# Completing historical total returns, fundamentals and the empirical study

Updated 2026-11-11. This guide distinguishes **source-code readiness** from
the availability of actual Indian equity market data.

## Authoritative source entry points

1. **Dhan daily historical prices:** https://dhanhq.co/docs/v2/historical-data/
2. **Dhan corporate-action adjustment confirmation:** https://dhan.co/support/platforms/dhanhq-api/is-the-historical-data-from-dhan-s-data-api-adjusted-for-corporate-actions-like-bonuses-and-splits/
3. **NSE corporate actions / ex-dates:** https://www.nseindia.com/companies-listing/corporate-filings-actions
4. **NSE quarterly filings and XBRL:** https://www.nseindia.com/companies-listing/corporate-filings-financial-results
5. **NSE Indices total-return levels:** https://www.niftyindices.com/reports/historical-data
6. **NSE index methodology and TRI benchmark guidance:** https://www.nseindia.com/static/products-services/indices-faqs

Source sites and instruments can require logged-in access, request caps,
licensing, or interactive downloads. The repository does not bypass these
controls. Keep bulk vendor market data out of git.

## A. Corporate-action-aware total-return prices

**Important source distinction:** Dhan Support states daily historical prices
are **split and bonus adjusted**. Do not apply split factors again. The daily
historical-data docs do not establish dividend reinvestment or delisting payout
completeness. Therefore our default `split_bonus_adjusted` mode adds only
independently verified, ex-date cash dividends.

Prepare an event ledger using this exact schema:
```csv
ex_date,ticker,event_type,cash_per_share,share_multiplier,declared_at,source_url,verified
2024-04-18,EXAMPLE_A,dividend,5.0,1.0,2024-04-01,https://example.com/source,true
2024-09-12,EXAMPLE_A,split,0.0,2.0,2024-08-20,https://example.com/source,true
```
**These events are fictitious FORMAT EXAMPLES, not real security claims.**

Events: `dividend`, `split`, `bonus`, `delisting_cash`.
`cash_per_share` is in the currency per share on the ex-date.
A split/bonus `share_multiplier` is new shares per old share, e.g., 2 for
2-for-1. `declared_at` is the actual published announcement date (not
a date guessed from fiscal period). Only `verified=true` event records
with a source link are allowed.

The engine:
- validates prices and event rows,
- applies split and bonus multipliers **only** when `price_basis=raw_unadjusted`,
- adds cash dividends on ex-date and reinvests,
- allows documented *terminal* delisting recovery without inventing a payout,
- aggregates daily wealth indices into monthly values,
- rejects unsupported events such as rights/merger/spin-off transformations
  until their economic payoff is sourced and supported.

```bash
python scripts/prepare_research_data.py total-returns \
  --raw-dir data/dhan/raw \
  --instruments data/dhan/instruments.csv \
  --actions data/sources/corporate_actions.csv \
  --price-basis split_bonus_adjusted \
  --output-dir data/research_v1
```

**No corporate-action records is NOT proof there were none.** An empty,
header-only event ledger may be used to inspect code paths, but **cannot**
establish dividend completeness. Vendor-disputed split policies, dividends
across multiple splits, intraday delisting, irregular corporate-event
accounting, spin-offs, merger exchange consideration and missing payouts
require review; the model intentionally fails on unsupported cases rather
than filling estimated wealth.

## B. Historical fundamentals from filings

Use a legally obtained, independently verifiable NSE filing/XBRL or licensed
vendor extract normalized to the following columns (row per published filing):
```csv
ticker,period_end,published_at,source_url,filing_id,book_equity,net_income_ttm,revenue_ttm,operating_income_ttm,total_assets,total_debt,shares_outstanding,market_cap
EXAMPLE_A,2023-12-31,2024-02-10,https://example.com/source,EXAMPLE_A_2023Q4,200,20,150,30,400,100,10,500
```
**This is a fictional FORMAT EXAMPLE.**
Accounting amounts must use a consistent currency/unit convention.
`market_cap` and shares must reflect a **historical contemporary** valuation,
not today's market cap. For published quarterly results, trailing-twelve-month
income/revenue/operating earnings must be derived from historically available
filings, never revised/restated amounts unavailable at that date.

```bash
python scripts/prepare_research_data.py fundamentals \
  --filings data/sources/filings_normalized.csv \
  --output-dir data/research_v1
```

Factor proxies (not proprietary MSCI factors):
- Value: `book_equity / historical_market_cap`, if book equity > 0.
- Quality: `0.5 * (net_income_ttm / total_assets) + 0.5 *
  (operating_income_ttm / revenue_ttm)`, if denominators valid.
- Size: positive historical market cap; the index factor score later uses
  `-log(market_cap)` to favor smaller companies.

The generated `fundamentals.csv` is compatible with existing research
factor scoring, with `available_at` equal to actual `published_at`.
The experiment only uses releases strictly **before** each decision date.
The program does not download proprietary NSE filing/XBRL content itself.

## C. Historical total-return benchmark

NSE Indices publishes **Total Returns Index Values** separately from regular
Nifty price index values. To compare dividend-reinvested stock returns,
prefer a compatible **NIFTY 50 TRI** return series. Export the permitted
date/level CSV from the NSE Indices historical page.

```bash
python scripts/prepare_research_data.py benchmark \
  --source data/sources/nifty50_tri_levels.csv \
  --date-column Date \
  --level-column "Total Returns Index" \
  --index-name "NIFTY 50 TRI" \
  --return-convention gross_total_return \
  --output-dir data/research_v1
```

Replace headers with the ACTUAL CSV header names. Result is
`benchmark.csv`, monthly simple returns, with dates labeled calendar month-end.
Review sample coverage, whether first month has a prior close, and data rights.

## D. Historical membership, sectors, security identities

`membership.csv` must represent historical effective-date entries and exits,
not today's Nifty 50 list. `sectors.csv` must have effective-dated historical
sector categories. These sources are NOT provided by Dhan's instrument master.
The user must supply the constituent evidence or a licensed point-in-time feed.

The standard research data directory requires:

```text
data/research_v1/
  prices.csv             # complete return-index series, normalized by ticker
  membership.csv         # historical event dates, eligibility TRUE/FALSE
  benchmark.csv          # NSE TRI monthly decimal returns
  fundamentals.csv       # publish-dated value / quality / size
  sectors.csv            # date-effective sector classifications
  corporate_actions.csv  # reviewed event ledger
  EVIDENCE_REVIEW.json   # external-review declarations
```

If a constituent is delisted, never silently remove it before its actual
effective exit. Where the security ceases to trade and its final recovery
is unknown, the backtest must fail instead of assuming zero loss or a sale
at a stale price.

## E. Local experiment and empirical holdout gate

After preparing all inputs and reviewing their economic comparability:

```bash
python -m index_research.cli run \
  --input-dir data/research_v1 \
  --output-dir results/research_v1 \
  --config config/research_multifactor.json

python scripts/prepare_research_data.py review \
  --data-dir data/research_v1 \
  --results-dir results/research_v1 \
  --declarations data/research_v1/EVIDENCE_REVIEW.json
```

The review emits `EMPIRICAL_RESEARCH_STATUS.json`, with evidence flags,
data SHA-256 checksums, holdout availability, and explicit warnings.

To use `dataset_status=verified_point_in_time`, the runner also requires
a completed declaration. It must NOT be treated as a machine-generated
certification: an **independent** data audit, frozen holdout methodology,
and full numerical/visual local tests are needed before an investor/recruiter
sees empirical claims.

Use `config/research_multifactor.json` as a template, and explicitly
freeze development/validation/final-test dates ahead of study execution.
Never tune on the final-test period.

## F. What cannot be truthfully completed without inputs

The toolchain is **source-code implemented** but cannot produce a genuinely
validated full-Nifty historical research report without licensed or lawfully
exported benchmark levels, historical constituent snapshots and changes,
financial-statement publication vintages, dividend/split/merger/delisting
evidence, and a Dhan or other historical price source.

Neither simulated data nor the old static universe is a substitute.
We will not invent market-history records, declare results independently
verified, or overwrite `main` on that basis.


## G. One-screen historical source preparation and final-test lock

In **Experiment Studio**, choose an actual observed dataset and scroll to
**Historical Evidence Workflow**. The screen is ordered:

1. **Collect originals.** Open the Dhan downloader for historical daily equity
   prices and the Data Library for original, lawfully obtained TRI levels.
   Use the existing pinned NIFTY constituent-history import for actual
   effective-date membership intervals. Inspect any unresolved delistings or
   security mappings; the current Dhan instrument master is not a historical
   delisted-security archive.
2. **Prepare dated actions.** Upload a real, public-source-cited
   `corporate_actions.csv` to the *Create event-adjusted total-return dataset*
   form. Choose the **original price basis**. For Dhan daily closes, select
   `split_bonus_adjusted`; `raw_unadjusted` would double-apply splits.
   QuantLab creates a **new version**, retaining the parent's daily candles,
   eligibility, benchmark, dated notes and source metadata. Originals are never
   overwritten. The return output is a daily-reinvested wealth index evaluated
   at the ACTUAL monthly observed sessions. Interior missing daily sessions,
   source calendar gaps, unsupported corporate events, unverifiable event
   records, and reused already-adjusted factors block the conversion.
   **An empty event CSV is not evidence that an issuer had no dividends.**
3. **Inspect source gates.** QuantLab structurally reconciles every PIT interval
   and observed member month, verifies the source interval hash and pinned
   commit, enforces index constituent counts (NIFTY 50=50 and source-dated
   NIFTY BANK transitions), identifies missing eligible next-month returns,
   checks TRI name/convention/calendar/level-source digest and event processing
   policy, and checks publication vintages when filing factors are selected.
   Its source and independent-license review status is **never approved by
   software alone**. Export the detailed readiness JSON to share with an
   independent reviewer.
4. **Freeze one test.** Before examining final-test performance, specify
   `validation_start` and `final_test_start` in Experiment Studio. The
   software requires at least **44 training months** (36 + 20% buffer),
   one separate validation month, and 12 final-test months. Press **Create
   frozen protocol** to pin exact input and provenance hashes, model parameters,
   test dates and a local registration timestamp. Press **Run once** to
   execute the saved configuration and consume the protocol exactly once.
   QuantLab verifies the original source hashes before and after execution and
   compares the completed manifest against frozen CSV inputs. A changed source
   invalidates the receipt; a consumed protocol cannot be rerun. The archived
   Results Studio **Evidence audit** shows the lock status.

The frozen lock is intentionally labeled **software-frozen exploratory**:
it is not a third-party-notarized preregistration, does not prevent prior
human inspection of the final test and is not proof of untouched evaluation.
For confirmatory claims, use an independently timestamped protocol, locked
future observations or truly prospective data, and a human source audit.

A successful source conversion, a matching TRI calendar, a 64-character
SHA-256 hash, or a checked `verified=true` in an action ledger is **not**
external verification. Valid Nifty-index and vendor licenses, all historical
corporate actions, split/bonus policies, special dividends, name changes,
delistings, actual recovery proceeds, and first-publication filing dates must
be checked against genuinely original evidence. No missing events are
automatically inferred to be absent.

### New local-only endpoints

- `GET /api/workspace/historical-readiness/{dataset_id}?validation_start=YYYY-MM-DD&final_test_start=YYYY-MM-DD`
- `POST /api/datasets/{dataset_id}/add-actions`: multipart `file` (original
  action CSV), `price_basis`, `acknowledge_unverified=true`.
- `POST /api/workspace/frozen/create`: the exact Experiment Studio JSON
  configuration including dataset ID and chronological split.
- `GET /api/workspace/frozen/{protocol_id}`: inspect immutable protocol.
- `POST /api/workspace/frozen/{protocol_id}/execute`: JSON `{"confirm":true}`
  queues the single-use Python research job.
- `GET /api/workspace/frozen/runs/{run_id}/receipt`: inspect source lock.

All endpoints are loopback-only and obey the same no-order security policy.
The new source snapshots live locally under ignored `data/` and `results/`,
never on GitHub or in the browser bundle. No proprietary market files are
redistributed by the exported methodology reports.

Run local regression tests after updating:
`python -m unittest tests.test_historical_freeze tests.test_action_import -v`.
