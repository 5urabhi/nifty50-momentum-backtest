# QuantLab — Evidence Gates, Live Dhan Reconciliation and ML/RL Research

## Three new workflows

The Research Workspace → **Evidence & ML** page contains:

1. **Evidence & Certification**: eight historical research evidence checks, each
   tied to the current source-data SHA-256. Adding a dated public HTTPS source
   is *user-submitted evidence*, not verification or an approval. If prices
   change, the citation is marked stale. Historical investability and
   prospective execution are NEVER automatically certified.
2. **Live Dhan Check**: one read-only vendor candle request for a mapped
   daily equity, performed only after explicit confirmation. Before requesting
   history, QuantLab checks GET /v2/profile and Dhan Data API entitlement.
   The resulting saved report contains overlap counts, mismatches and hashes,
   not tokens, account details or raw vendor prices. Price tolerance is
   INR 0.03 + 0.05% of the queried close. No broker orders or price writes.
3. **ML / RL Holdout**: real CPU ridge, random forest, histogram gradient
   boosting, and bounded long/cash tabular Q-learning. Sources are observed
   DAILY prices, never silently forward-filled. Trained settings and frozen
   models are tested on strictly later returns, with a one-bar execution
   delay and explicit cost assumptions. Full held-out returns are CSV
   artifacts, graphs are limited to 600 sample points.

### Eight categories in the evidence gate

| Category | Needed external evidence |
| --- | --- |
| Prices | Original observed close source and adjustment rules |
| Membership | PIT notices with publication timestamps |
| Actions | Split, bonus, dividend records and ex-dates |
| Benchmark | Properly aligned independently reviewed total-return index |
| Delistings | Complete historical symbols and explicit mapping exceptions |
| Fundamentals | Publication-time vintages, no post-decision availability |
| Costs | Brokerage, transaction fees, spread, impact and taxes |
| Execution | Dated broker fills and market availability records |

Source references require a public HTTPS URL without embedded credentials,
a publication-as-of date, and a written note. They are recorded in
results/integrity_evidence and pinned to the observed price file hash.
Even all eight documented categories do not constitute independent
certification from the software itself.

### Live broker data validation

In Data Library, prepare a daily mapped Dhan dataset or reuse the shared
Dhan market-data view. Open Evidence & ML → Live Dhan Check and inspect
the one-instrument safe probe plan. Approve the live history sample request.
The token stays in the local environment. Inspect the returned completed Job
and Refresh to display its status: matched, mismatch, or insufficient overlap.
If the underlying price file changed after a probe, the interface marks the
old result stale. A match verifies only that historical vendor sample, not
total returns or point-in-time index membership.

The earlier +20% sample buffer and consent-based data extension still use the
one canonical Dhan store and append only observations not already cached.
No new NIFTY/BANK NIFTY duplicate data store is created.

### Learning conventions and mathematical guardrails

Return: r_t = P_t/P_(t-1)-1.

Signal features use observed past 1/5/20-session momentum, volatility and
downside information at close t. Action is assumed filled no earlier than
close t+1 and earns r_(t+2); this is a conservative research timing convention,
not actual fill verification. Training samples end two decision steps before
the first test decision to ensure all training labels are observed strictly
before holdout. No future holdout labels enter training or feature scaling.

Ridge: train-only standardization and L2 penalty. Random Forest: 90 seeded
trees with restricted depth/leaves. Histogram Gradient Boosting: seeded
bounded ensemble. Tabular Q-learning: fixed momentum/volatility regime,
long/cash actions only; no leverage or neural policy, train-only updates.
All parameters are predefined in code; no claim of an optimized alpha.

Per-position cost in basis points is explicit and applies on position changes.
A single-asset passive price-only reference is used. Outputs must be treated
as exploratory research: no dividends, complete action adjustment, capacity,
fill slippage, full taxes or broker records are claimed.

Requirement: at least 240 lagged samples, preferred 288 (+20%).
The additional 20% is NOT an out-of-sample guarantee; train and untouched
holdout are explicitly separated. Run metadata includes source SHA-256,
seed, training cutoff, earliest test decision, delayed entry and recorded
test observations. Download the complete CSV for independent review.

### Verification

    npm run build
    python -m unittest discover -s tests -p 'test_research_remaining.py' -v
    python -m unittest discover -s tests -v

GitHub CI also runs actual Ubuntu Chromium browser smoke tests using a
deterministic synthetic local fixture. This does not mean live Dhan account
verification has happened. A real Data API entitlement remains a user-side
dependency. No order submission endpoints are enabled.

### External data limitations remain

Code cannot create independently valid historic NSE membership notices,
dividends, delisted constituent mappings, benchmark TRI, publication-date
fundamentals, actual broker execution or live Dhan API credentials.
Do not fill these as zero, infer approval, or claim them certified.
This increment also does not claim LSTM/PPO/SAC production algorithms
or independently validated strategy profitability.
