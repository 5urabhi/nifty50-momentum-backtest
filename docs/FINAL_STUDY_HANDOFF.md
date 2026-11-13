# QuantLab — Final Owner Handoff

**As of November 13, 2026:** Software and synthetic CI are tested;
the authentic, independently replicated NIFTY results remain a separate
research/evidence milestone. Use the commands below on your Ubuntu checkout.
Scripts are committed to GitHub; do not download or paste separate scripts.

## 1. Update and diagnose

~~~bash
cd "$HOME/Desktop/codes/nifty50-momentum-backtest"
git switch main
git pull --ff-only origin main
python -m unittest discover -s tests -p 'test_final_research_handoff.py' -v

python scripts/quantlab_finish.py legacy-audit \
  --source nifty50_prices_monthly.csv \
  --output-dir results/legacy_audit_001

python scripts/quantlab_finish.py doctor \
  --data-dir data/research_v1 \
  --config config/research_multifactor.json \
  --output-dir results/doctor_001
~~~

A missing-input doctor exits 2 **and still writes** NEXT_ACTIONS.md,
RESEARCH_RELEASE_STATUS.json, RESEARCH_RELEASE.html,
RESEARCH_PAPER_DRAFT.md and a source-safe ZIP. Inspect NEXT_ACTIONS.md.
Use a new output suffix each time; files are never silently overwritten.

The tracked old price file has 49 stock columns, 162 months
(January 2012–June 2025), 193 missing prices and first-day-of-month
labels. That archive is not source-proven point-in-time NIFTY membership,
trading-session prices, dividend-reinvested wealth or a compatible TRI.
NEVER report its old performance figures as verified historical alpha.

## 2. What needs YOUR original-data access

First party NIFTY 50 Total Returns Index level CSV with a monthly level
preceding the study:
https://www.niftyindices.com/reports/historical-data

Effective-dated historic membership notices, all old/deleted/renamed
securities, and archived monthly weight snapshots:
https://www.niftyindices.com/Press_Release

Original dividends, bonuses, mergers, rights, delisting consideration,
as-first-published corporate filings/market caps, historical
trading volumes/sector histories:
https://www.nseindia.com/companies-listing/corporate-filings-actions

Configure Dhan tokens only in your ignored local .env or shell.
Never paste secrets here or store them in GitHub. In the existing
Data Library read-only interface, map ALL historic ticker/security IDs,
not just today's NIFTY 50. Dhan candles are NOT dividend-inclusive wealth.

NSE may require an approved research license or data-seeking request;
see docs/NSE_DATA_ACCESS_REQUEST.md for a ready-to-personalize template.

## 3. Prepare legally obtained sources (adjust real input filenames)

~~~bash
python scripts/prepare_research_data.py benchmark \
  --source data/sources/NIFTY50_TRI.csv \
  --date-column Date --level-column "Total Returns Index" \
  --index-name "NIFTY 50 TRI" \
  --return-convention gross_total_return \
  --output-dir data/stages/tri_001

python scripts/prepare_research_data.py fundamentals \
  --filings data/sources/first_published_filings.csv \
  --output-dir data/stages/fundamentals_001

python scripts/prepare_research_data.py total-returns \
  --raw-dir data/dhan/raw \
  --instruments data/dhan/instruments.csv \
  --actions data/sources/corporate_actions.csv \
  --price-basis split_bonus_adjusted \
  --output-dir data/stages/stock_wealth_001
~~~

These are runnable commands, but input files must truly exist and match
documented CSV schemas. Adjust the benchmark's column names to the
ACTUAL NSE export. No original dividends, delistings or source dates
are inferred. For an observed monthly price panel AND original PIT
membership with observed trading-session dates:

~~~bash
python scripts/prepare_research_data.py calendar-align \
  --source-dir data/stages/observed_monthly_plus_pit \
  --benchmark data/stages/tri_001/benchmark.csv \
  --output-dir data/stages/aligned_001

python scripts/prepare_research_data.py nse-weight-snapshots \
  --manifest data/sources/nse_weights/manifest.csv \
  --prices data/stages/aligned_001/prices.csv \
  --weight-unit percent \
  --output-dir data/stages/nse_weights_001
~~~

Original monthly weight reports do not establish effective-date events.
Verify the declared first-publication times; unseen securities remain
hard blockers rather than being removed from the historic universe.
See docs/NIFTY_SOURCE_COMPLETION.md for full validation/schema rules.

## 4. Assemble an immutable research dataset from stage folders

~~~bash
python scripts/quantlab_finish.py assemble \
  --prices data/stages/aligned_001 \
  --membership data/sources/membership.csv \
  --benchmark data/stages/tri_001 \
  --fundamentals data/stages/fundamentals_001 \
  --corporate-actions data/sources/corporate_actions.csv \
  --sectors data/sources/sectors.csv \
  --benchmark-weights data/stages/nse_weights_001 \
  --factor-returns data/sources/factor_returns.csv \
  --liquidity data/sources/liquidity.csv \
  --config config/research_multifactor.json \
  --output-dir data/research_v1
~~~

Remove optional arguments ONLY where the real files do not exist. The
relevant advanced study will remain unavailable without them.
The mandatory inputs are prices, membership and benchmark.
The assembler copies matching provenance files, validates aligned
monthly inputs, preserves synthetic warning markers and writes
source SHA-256 plus the immutable FROZEN_CONFIG.json.
For later corrections, use data/research_v2, not an overwrite.

## 5. Execute studies on those exact sources

~~~bash
python scripts/quantlab_finish.py doctor \
  --data-dir data/research_v1 \
  --config data/research_v1/FROZEN_CONFIG.json \
  --output-dir results/study_release_001 \
  --execute

python scripts/prepare_research_data.py coverage-audit \
  --data-dir data/research_v1 \
  --config data/research_v1/FROZEN_CONFIG.json \
  --output-dir results/security_gaps_001
~~~

Read NEXT_ACTIONS.md, RESEARCH_RELEASE_STATUS.json and
RESEARCH_PAPER_DRAFT.md. The paper contains ONLY descriptive results
supported by the local data. It is not publication-approved merely
because computations ran. A separately prepared 20%-extra estimation
history is preferred; the final chronological holdout must be untouched.

## 6. Independent source and research review

A separate reviewer must reconcile true original constituent effective
dates, all dividends/rights/delistings, authentic TRI levels, first
publication financial dates, historic costs and matching source hashes.
Review permissions for publishing derived index figures.
Do not mark reviewer flags complete without actual evidence and signoff.
Only after that review should real NIFTY research returns, Sharpe,
turnover or tracking error be quoted in a paper or résumé.

Existing features are already usable: Index Studio, factor/active risk,
source passports, three-study CLI, SDK/Jupyter, plots and demo video.
What remains is authorized original sources and external replication.
