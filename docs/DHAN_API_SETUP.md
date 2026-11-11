# Connecting DhanHQ API and preparing historical market data

**Read-only local data workflow · DhanHQ v2 · Updated 2026-11-11**

This guide connects the local Python research framework to the **historical
market-data** endpoints of DhanHQ. It does **not** place orders, access brokerage
funds, or automate live trading. The credentials are read from your local
terminal; never paste tokens in GitHub issues, commits, screenshots, the
Streamlit UI, or a Vercel environment used by a public website.

## 1. Create / enable your DhanHQ Data API access

1. Sign in to **Dhan Web** (not the mobile app).
2. Open **My Profile → Get Trading & Data APIs** / **Access DhanHQ APIs**
   (exact label may differ).
3. Generate an access token. The DhanHQ v2 authentication guide documents
   a **24-hour validity** for a directly generated token; plan to refresh it.
4. Check the **Data APIs** tab and whether your account has an active historical
   data entitlement. Trading API access does not imply a Data API subscription.
5. Record your Client ID **privately** if needed for other account API uses;
   this historical candle downloader authenticates with the access token
   only. It does not need your password, TOTP secret, or trading PIN.

Official guides:
- DhanHQ v2 authentication:
  https://dhanhq.co/docs/v2/authentication/
- DhanHQ v2 historical data:
  https://dhanhq.co/docs/v2/historical-data/
- DhanHQ instrument list:
  https://dhanhq.co/docs/v2/instruments/
- Dhan support (access/data subscription):
  https://dhan.co/support/platforms/dhanhq-api/how-to-access-dhan-api/

Dhan's support page currently lists a Data API subscription price of
₹499 plus tax per month, subject to change. Verify today's entitlement and
pricing in your own account before subscribing.

## 2. Ubuntu local setup

From the **development branch**:

```bash
git clone --branch research/multi-factor-equity-index https://github.com/5urabhi/nifty50-momentum-backtest.git
cd nifty50-momentum-backtest
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r dashboard/requirements.txt
```

Put your access token in a **local shell environment variable**:

```bash
read -rsp "Dhan access token: " DHAN_ACCESS_TOKEN; echo
export DHAN_ACCESS_TOKEN
```

The token is not echoed and is not stored by the downloader.
Open a new terminal or log out and the shell environment value will need to
be entered again. Do **not** use `echo token >> ~/.bashrc`, commit a
`.env` file, or include your token in a command argument that can appear in
shell history. The project's `.gitignore` excludes local `.env` files and
`data/` but that is not a substitute for secret handling.

If the token expires, create another token on Dhan Web and repeat the
local environment-variable step. HTTP 401/403 errors generally warrant
checking the token and your Data API subscription first.

## 3. Download the instrument-master CSV and find Security IDs

Dhan uses a **Security ID**, not a stock ticker, in historical chart requests.
A ticker can change or refer to different exchange instruments over time.

```bash
python scripts/dhan_data.py instrument-master \
  --output data/dhan/instrument_master.csv
```

This downloads the official **detailed scrip-master CSV**. Inspect it to
identify the correct exchange, segment, series, company/security identifier,
and instrument type. Dhan's master is a *current* reference snapshot; it does
not replace historical Nifty 50 constituent or identifier-event files.

Find candidate instruments interactively in your terminal:

```bash
python scripts/dhan_data.py instrument-search --query "RELIANCE"
# Or search a company name, then inspect the matching exchange/security IDs
```

Create your own reviewed mapping file, e.g.
`config/dhan_instruments.example.csv`, then copy it into ignored `data/`:

```bash
cp config/dhan_instruments.example.csv data/dhan/instruments.csv
```

Edit the file and replace the **placeholder** numeric Security IDs with IDs
taken from the downloaded official instrument master. Fields:

```csv
label,security_id,exchange_segment,instrument,expiry_code
EQUITY_A,00000,NSE_EQ,EQUITY,0
EQUITY_B,00001,NSE_EQ,EQUITY,0
```

**These IDs are examples, not valid instrument mappings.** Never trust a
hardcoded Security ID without confirming the master and exchange segment.
Use a unique `label` per security. Use stable IDs across splits and symbol
changes only if your vendor confirms continuity.

## 4. Download historical daily OHLCV

Dhan's documented request is:
`POST https://api.dhan.co/v2/charts/historical`, with
`securityId`, `exchangeSegment`, `instrument`, `expiryCode`,
`fromDate`, and `toDate` (end date **exclusive**).

After reviewing the local instrument mapping:

```bash
python scripts/dhan_data.py download \
  --instruments data/dhan/instruments.csv \
  --from-date 2018-01-01 \
  --to-date 2026-11-11 \
  --output-dir data/dhan/raw
```

The utility uses conservative 365-calendar-day chunks, validates array
lengths and OHLCV ordering, retries HTTP 429/temporary server errors, and
stores one CSV and one SHA-256 manifest per security. Daily data range
availability depends on the instrument and your API access. If a file already
exists, the tool refuses to silently overwrite the existing evidence.
To refresh, save to a new versioned directory.

**Security note:** The manifest includes public instrument identifiers and
retrieval metadata, never your access token.

## 5. Download intraday candles (optional research, not needed for monthly factors)

Dhan's `/v2/charts/intraday` supports 1, 5, 15, 25, and 60 minute intervals.
The v2 documentation describes up to five years for active instruments,
but **each request is limited to 90 calendar days**. Availability depends on
the account/instrument and the vendor's current rules.

```bash
python scripts/dhan_data.py download \
  --instruments data/dhan/instruments.csv \
  --from-date 2026-09-01 \
  --to-date 2026-11-11 \
  --interval 5 \
  --output-dir data/dhan/intraday_5m
```

The downloader automatically splits into 90-day chunks. Times are submitted
using Dhan's documented date-time format; received UNIX epoch seconds are
converted to **Asia/Kolkata** for research. It does not fabricate missing
candles or interpolate across market holidays.

## 6. Convert daily data into monthly close matrix

```bash
python scripts/dhan_data.py monthly \
  --instruments data/dhan/instruments.csv \
  --raw-dir data/dhan/raw \
  --output-dir data/dhan/monthly_research
```

Creates `data/dhan/monthly_research/prices.csv`. This is a **raw close-price**
panel, labeled by calendar month-end for alignment; the actual last trading
close can precede the calendar month-end. The CSV is **not necessarily adjusted
for splits, dividends, mergers, spinoffs, symbol changes, or delisting cash**.

Before a credible portfolio total-return backtest, source and audit a
security-level corporate-action adjusted series (and delisting payouts) from
a qualified source, and compare to an official return-convention-compatible
benchmark. Never substitute raw Dhan close for an audited total-return price.

## 7. What Dhan alone does NOT supply to this index project

The research engine requires the following *separate* evidence:

| Input | Needed for | Where to get it / limitation |
| --- | --- | --- |
| `prices.csv` | Monthly returns | Dhan raw closes for exploration; qualified corporate-action-adjusted vendor for defensible total returns |
| `membership.csv` | Historical index universe | NSE effective-dated constituent changes, archival index notices, or licensed history; **not** Dhan's current scrip master |
| `benchmark.csv` | Tracking error/IR | Official compatible Nifty price or total-return index history, with usage rights |
| `fundamentals.csv` | Value/Quality/Size | Publication-dated filings, accounting observations, cap histories from licensed or validated primary sources |
| `sectors.csv` | Historical sector caps | Effective-dated sector classification history |
| `corporate_actions.csv` | Evidence and audit | Exchange/company events; currently audit-only; not a corporate-action adjustment engine |

The importer deliberately **does not generate fake membership or a synthetic
benchmark** to pass off as a genuine Nifty index. There is no verified
point-in-time index replication until these other inputs are sourced.

## 8. Validate, run, and present results

With independently verified files in the same monthly research directory:

```bash
python -m index_research.cli run \
  --input-dir data/dhan/monthly_research \
  --output-dir results/dhan_research \
  --config config/research_multifactor.json
```

This will **fail** if `membership.csv` or `benchmark.csv` is missing;
that is intentional. Value/Quality/Size also require publication-dated
`fundamentals.csv`. The comparison dashboards and reports should be
labeled exploratory until historical inputs are validated.

For numerical and UI tests when ready:

```bash
bash scripts/run_local.sh tests
bash scripts/run_local.sh acceptance
bash scripts/run_local.sh dashboard
```

The Streamlit **Index Research** page accepts the resulting files packaged
in a flat ZIP; use only validated sources when presenting investment findings.

## 9. When moving the UI to Vercel

Do **not** expose an access token through client-side JavaScript or a static
site. The current Vercel viewer is static and intentionally has no Dhan
connector. If a future hosted server-side data service is added, use a
server-side secret store, authentication, least-privilege tokens, data
entitlements, request limits, audit logs and licensed storage/redistribution.
Never embed secrets in web bundles, CSV exports, manifests or public plots.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| 401 / 403 | Generate a new access token; check data entitlement |
| 429 | Downloader retries with backoff; reduce request frequency |
| Unknown Security ID | Inspect latest official instrument master |
| Missing candles | Check trading dates, segment, account plan, current instrument status and historical availability |
| Duplicate/nonpositive OHLC | Investigate vendor response instead of interpolating |
| No adjusted total return | Source adjusted/corporate action data; do not assert an investable backtest |
| Missing membership/benchmark | Expected hard stop: data pipeline does not invent those datasets |

## Official references

- Authentication: https://dhanhq.co/docs/v2/authentication/
- Historical data: https://dhanhq.co/docs/v2/historical-data/
- Instrument list: https://dhanhq.co/docs/v2/instruments/
- DhanHQ Python SDK: https://dhanhq.co/docs/DhanHQ-py/api/_historical_data/

The Streamlit **Dhan Data Setup** page shows local instrument-mapping status,\nrequired data readiness, and 2D charts of downloaded raw closes/volumes. It\nnever asks for your token or invokes order endpoints.\n\n**No orders, trading automation, broker secrets or investment advice are part
of this read-only historical-data integration.**

## Preparing dividend-reinvested total-return series

**Source clarification:** Dhan specifically states that its **daily** history
is adjusted for splits and bonus shares. The daily historical-candle docs do
not certify that cash dividends and delisting payoffs are already reinvested.
Use the new `scripts/prepare_research_data.py total-returns` command with a
**sourced, verified** corporate action ledger and the default
`--price-basis split_bonus_adjusted` to avoid double-counting stock splits.

The returned month-end `prices.csv` is a normalized *wealth-index* matrix,
not a quoted rupee stock-price matrix. Its percent changes represent modeled
shareholder returns under the documented dividend convention. Read the
[Empirical Data Guide](EMPIRICAL_DATA_GUIDE.md) before using it.
