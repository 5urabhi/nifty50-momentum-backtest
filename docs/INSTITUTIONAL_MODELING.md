# Institutional Research — Index Optimization, Yield, Market Capacity and Research Acceptance

**Research status:** advanced software capabilities are implemented for source-supplied observations. This does **not** certify index replication or historical alpha.

## 1. Institutional-style benchmark-relative index optimization

Inside **Research Workspace → Index Research Studio**, select **Benchmark Relative** in Portfolio Weighting.

The optimizer uses the source's actual as-of benchmark constituent weights (\`benchmark_weights.csv\`) and annualized covariance estimated using strictly earlier monthly security returns. It chooses eligible top-N securities by the selected *research factor z-scores*. Those factor scores are ranking signals, **not validated forecasts of security alpha**.

Objective:

\[
\max_w \quad s^\top w - \lambda(w-b)^\top\Sigma(w-b)
-\gamma\sum_i \sqrt{(w_i-w_i^\mathrm{old})^2+\epsilon^2}
\]

Constraints: fully invested, long-only, single-name cap, effective-dated sector cap, optional annualized tracking error limit, and optional single-name trade cap. Previous-target weights are a *proxy* for turnover in optimization; the trading simulator reports separate drift-aware realized model turnover. This is an independent open research method, not proprietary MSCI/Barra logic.

**Missing benchmark constituent weights (including explicit zeros) block the optimizer**. Missing past returns used by the risk model are not filled with zeros. Infeasible sector/security/risk/trade limits raise an actionable error; they do not produce fictitious weights.

Benchmarks must share the exact security universe and a dated \`date,ticker,weight\` snapshot. All snapshots sum to 1 and cannot be more than 95 days old at a decision.

### Interpreting risk and turnover parameters

* \`optimizer_risk_aversion\` penalizes *annualized active return variance*, not portfolio volatility or a user risk profile.
* \`optimizer_turnover_penalty\` penalizes approximate absolute changes from previously targeted positions, not actual fill prices.
* \`optimizer_tracking_error_limit\` is an optional annualized volatility fraction, e.g. \`.15\` for 15%; an infeasible limit raises an error.
* \`optimizer_max_trade_weight\` limits changes in each constituent portfolio weight, e.g. \`.2\` for twenty percentage points.
* A larger risk penalty does not automatically imply better realized out-of-sample returns.

## 2. Yield factor — source-only

Optionally add \`cash_dividends_per_share_ttm\` to the original normalized filing export. This must be a sourced trailing-twelve-month **per-share** total known at the filing's \`published_at\` date. QuantLab computes:

\[
\mathrm{Yield}=\frac{\mathrm{TTM\,cash\,dividends\,per\,share}\times
\mathrm{historical\,shares\,outstanding}}{\mathrm{historical\,market\,cap}}
\]

It writes an optional \`yield\` column to \`fundamentals.csv\`, with the same first-public-availability guard as Value and Quality. If the source does not provide the dividend field, the exporter omits Yield rather than making it zero. Sourced payout timing and share-basis adjustments still require audit before claims about actual dividend yields.

## 3. Liquidity, capacity and square-root market impact

For execution-capacity scenarios, import a ZIP containing required research CSVs plus \`liquidity.csv\`:

\`\`\`csv
date,ticker,adv_currency,half_spread_bps
2024-05-31,EXAMPLE_A,50000000,7
2024-05-31,EXAMPLE_B,80000000,4
\`\`\`

**These rows are fictitious schema examples, not actual NSE observations.** The user must supply backward-looking average daily traded **notional in portfolio capital's currency** and contemporaneous half spreads. Missing or stale observations block execution cost estimates.

The model uses declared capital, execution days, maximum share of ADV, and a square-root coefficient:

\[
p_i=\frac{|\,\Delta w_i\,|\times\mathrm{capital}}
{\mathrm{ADV}_i\times\mathrm{execution\ days}},
\quad
\mathrm{impactBps}_i=k\sqrt{p_i},
\]

\[
\mathrm{extraCostFraction}=
\sum_i|\Delta w_i|
\frac{\mathrm{halfSpreadBps}_i+\mathrm{impactBps}_i}{10000}.
\]

If **any** trade exceeds the configured participation limit, the model rejects the backtest instead of assuming infinite capacity. Existing fixed \`cost_bps\` remains a separate fee scenario and must **exclude spread** when this overlay is enabled to prevent double counting. This is hypothetical research execution, not real order-book fills or institutional trade-cost certification.

Saved runs include \`liquidity_capacity.csv\` where enabled. Charts and comparisons must use these **net** returns rather than older cost assumptions.

## 4. Three research studies

The command-line research workflow is documented in [Three Studies Research Acceptance](THREE_STUDIES_RESEARCH_ACCEPTANCE.md). It now includes:

* **Study A:** chronological factor index research, development/validation/final test outputs, exploratory HAC/bootstrap holdout analysis, and **Holm-adjusted multiple-candidate tests on validation only**.
* **Study B:** ex-ante source-fitted factor/specific risk at strictly earlier estimation dates, with up to 36 historical period estimates exported as \`STUDY_B_RISK_HISTORY.csv\` when factor returns and full benchmark weights are available.
* **Study C:** membership disagreement counts; when real data support both variants, an explicit **lookahead-contaminated static-final-universe counterfactual** compared with point-in-time methodology using identical settings. Missing historical prices block the counterfactual rather than being filled. This counterfactual is a sensitivity experiment, not a causal estimate of survivorship alpha.
* Optional user-supplied price-only index comparison and modeled turnover/cost drag.

The exported evidence ZIP contains **source hashes and derived metrics only**, not redistributed raw licensed historical candles or filings.

### Source verification that cannot be automated honestly

There is no tracked complete NSE-source-audited NIFTY historical dataset in this repository. Source review still needs original constituent notices, dividend/split/bonus/merger/delisting evidence, publication-date financial statements, benchmark TRI, sector mapping, 20% extra sample buffers where appropriate, and independently verified liquidity/quotes.

No script should auto-mark \`verified_point_in_time\` based on a file existing, simulated Dhan candles or fabricated expected returns. A green CI is a **software acceptance**, not a financial-result audit.

## 5. Reproduction, mathematical failure and researcher communication

Source checksums are pinned at archived execution. If an input changes, older analysis is not silently rewritten. Any infeasible optimization raises a concise mathematical reason; to repair it, inspect the relevant maximum name/sector weight, benchmark coverage, prior return history, or ADV/trade participation. The final empirical claims require a genuinely preregistered experiment and independent review of a frozen final holdout.

**Recruiter-safe description:** Implemented benchmark-relative active-risk optimization, source-vintage Yield handling, source-gated liquidity/market-impact modeling, multiple-testing controls, static-universe robustness counterfactual and saved-run research reproducibility. Do **not** quote historical NIFTY alpha, independently validated Sharpe, or genuine market capacity without audited inputs.
