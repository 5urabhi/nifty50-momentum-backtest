# Local input data contract (CSV files)

Keep market data and paid datasets local. `.gitignore` excludes `data/`
except this README. Local files remain on your computer.

## prices.csv
Wide month-end adjusted CLOSE price matrix. First column `date` as
YYYY-MM-DD, remaining columns exactly stable security identifiers. Example:

```csv
date,STOCK_A,STOCK_B
2023-01-31,101,95
2023-02-28,104,98
2023-03-31,100,102
```

Use *adjusted* total-return-compatible values if benchmark represents total
returns. Prices are strictly positive; missing values allowed only for
securities not held in affected periods. **Never backfill delistings.**
In a true investable backtest, account for delisting payouts, dividends,
splits, trading halts and ticker-to-security ID mappings.

## membership.csv
Effective-dated changes in historical eligible universe.
`date,ticker,eligible` with true/false. EVERY security needs a
state record at or before the first price date. Example:

```csv
date,ticker,eligible
2023-01-31,STOCK_A,true
2023-01-31,STOCK_B,false
2023-03-31,STOCK_B,true
```

This is **not** derivable from a current Nifty 50 list. Historical constituent
files, corporate-action/deletion records, and effective dates must be sourced.

## benchmark.csv
`date,return` with decimal *monthly simple returns*. Dates match prices
exactly. E.g. 0.02 means +2%. First return row is unused by the backtester.

## fundamentals.csv (optional for momentum-only)
Long-format `ticker,period_end,available_at,value,quality,size`:

- `available_at` is first date/time this specific observation was published
  and became usable. It must NOT be earlier than `period_end`.
- `value` is a **higher-is-better** score defined transparently by the data
  owner, NOT automatically a book-to-price ratio.
- `quality` is a **higher-is-better** quality score.
- `size` is a positive market capitalization amount; current implementation
  ranks **smaller size** higher via -log(market capitalization).
- Data revisions require explicit publication versions, not backfilled values.

The current reader accepts date-level publication evidence and uses observations
strictly *before* each decision date, guarding against same-close ambiguity.

## Important historical limitations

This is a local research scaffold, not an official MSCI or NSE index calculator.
Static-universe demonstrations lack historical membership validity. Missing
factor vendor coverage, dividend adjustments or benchmark licenses must be
reported, not silently filled with estimates. A public resume claim requires
audited source evidence, frozen specifications and out-of-sample reproduction.


## sectors.csv (optional; mandatory for sector caps)

Effective-dated historical sector classification events:
```csv
date,ticker,sector
2020-01-31,STOCK_A,Banking
2020-01-31,STOCK_B,Consumer
2022-04-30,STOCK_A,Financial Services
```

All **held** securities must be classified on the relevant historical date.
A missing classification cannot be inferred from the present-day sector label.
The local fixture now includes `sectors.csv`, with explicitly synthetic names.
A sector cap is enforced on the weight vector at each scheduled reconstitution;
post-rebalance weights can drift over the cap until the next rebalance.

## Research controls and documentation

The data contract does not by itself reconstruct historical NSE membership,
benchmark constituents, official factor definitions or delisting payouts. The
research code fails on missing held-price observations rather than inserting
fictional recoveries. Production-correct corporate-action and investability
support still requires licensed event histories and a documented rulebook.


## sectors.csv (optional; required for sector caps)

Historical, date-effective sector classifications. Each row is one effective
change, not the company's **current** sector label. Format:

```csv
date,ticker,sector
2023-01-31,STOCK_A,Financials
2023-01-31,STOCK_B,Information Technology
2023-10-31,STOCK_B,Communication Services
```

Every *selected* constituent must have a known sector at the decision date
when sector constraints are enabled. Unknown or missing classifications block
portfolio construction; sectors are not silently substituted from today's
classification. The research dashboard accepts `sectors.csv` in the ZIP.

## Generated research artifacts

The local experiment and dashboard produce period returns, target/held
weights, concentration diagnostics, rolling benchmark-relative metrics,
factor-specific rank IC, portfolio factor exposures, optional sector exposure,
cost sensitivity, comparison variants, experiment manifest with source hashes,
a self-contained HTML report, and an offline PDF research-paper draft.
These files are descriptive until market source evidence is independently audited.

## corporate_actions.csv (optional EVIDENCE ONLY)

Use `date,ticker,event_type,event_source` rows to document relevant
corporate-action events and their primary source. This file is validated by
`data_audit.py` and included in the local evidence manifest, **but is not
used to transform price series or estimate delisting payouts**. Adjusted
prices/return conventions must already incorporate the appropriate dividend,
split, merger, spin-off and other economic outcomes before simulations.
Never claim adjusted total-return or survivorship-free accuracy from the
presence of this metadata file alone.
