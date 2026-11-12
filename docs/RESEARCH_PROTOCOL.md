# Equity Index Research Protocol — V1

Status: **development; no audited performance claims**.

## Objective
Investigate whether transparent, implementable equity factor index rules
improve benchmark-relative outcomes without unacceptable tracking error,
turnover, sector concentration or estimation risk.

## Existing baseline
Original `main.ipynb` and root-level outputs are retained without rewriting.
The legacy README reports an optimized Sharpe of 3.34 and 132.86% annualized
return. **These figures have not been reproduced or independently validated
by the new research engine and must not be used as verified project results.**

## Non-negotiable data rules
- Maintain effective-dated constituent membership (entry/exit dates);
  the legacy static ticker list is **not** historical point-in-time membership.
- Apply prices, corporate-action adjustments, financial statements and
  eligibility rules only after their actual availability dates.
- Record source, retrieval date, publication/filing date, data vintage,
  missing-value handling, and revision policies.
- Do not silently forward-fill through delisting, long suspensions or stale marks.
- If point-in-time constituents or fundamentals are unavailable, explicitly
  label the analysis a static-universe demonstration, not an investable backtest.
- License/accessibility may limit benchmark and fundamental datasets.

## Research design
1. Reproduce and audit legacy notebook on a fixed environment.
2. Implement auditable momentum-only baseline with specified month-end timing.
3. Build point-in-time membership and publication-lag evidence gates.
4. Add Value, Quality, Size and Low-Volatility factors one at a time, only when
   credible as-of fundamental/market-cap histories are available.
5. Specify index eligibility, ranking, weighting, caps and reconstitution.
6. Split historical development / validation / final test chronologically;
   freeze rules before the final test and document parameter search.
7. Evaluate price-only versus total-return benchmarks consistently; report
   tracking error, active return, information ratio, drawdown, turnover and costs.
8. Stress plausible execution lag, transaction costs, missing data and sectors.
9. Publish reproducible charts, configuration files and a short research memo.

## Timing semantics of new core
- Price row t is the monthly close at decision date t.
- Momentum with formation=12 and skip=1 uses P[t-1]/P[t-13] - 1.
- Weights selected at t are applied to monthly return t -> t+1; costs charged
  at interval start. This is idealized close execution and is *not* a
  live investable trading simulator.
- Benchmark returns are aligned to holding period end dates.

## Publication gates
No percentage improvement or resume performance claim until a clean run,
reviewed data provenance, transaction costs, timing, holdout discipline and
benchmark consistency have been recorded.

## Deliverables
- Tested Python research engine, separate from preserved original notebook.
- Machine-readable factor/index configurations and metrics with provenance.
- Streamlit/Plotly dashboard reading the same experiment outputs.
- Research report covering methodology, findings and limitations.
- Resume bullets restricted to actually implemented and verified work.
