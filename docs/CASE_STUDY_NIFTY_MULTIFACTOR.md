# Case study protocol — NIFTY multi-factor index research

**Status: RESEARCH PROTOCOL READY; INDEPENDENT EMPIRICAL VALIDATION NOT COMPLETE.**
**Do not quote a NIFTY return, Sharpe, alpha or tracking-error figure until the
identified historical inputs are obtained and independently reviewed.**

## Research question

Does a predeclared multi-factor rule using Momentum, Value, Quality and
Low Volatility achieve a meaningful improvement in net benchmark-relative
performance relative to a compatible NIFTY benchmark, subject to caps on
single-name exposures, sectors, and turnover?

This is a *hypothesis*, not a claim of success.

## Proposed preregistration

- Null: the truly later holdout information ratio of the strategy is not
  positive after specified implementation costs.
- Alternative: later holdout IR is positive without violating concentration,
  turnover and tracking-error requirements.
- Primary response: holdout information ratio using a compatible
  dividend-reinvested benchmark, with the return frequency declared.
- Secondary responses: CAGR and drawdown, realized tracking error, factor
  exposure, net turnover, turnover-constrained sensitivity and factor IC.
- Ex ante decisions: factor score construction, factor weights, eligibility,
  reconstitution schedule, benchmark basis, missing-security policy,
  liquidity screens, taxes and explicit transaction costs.
- Reserve development, validation, and a never-explored final holdout.
  The final period and success criteria must be fixed *before* the final
  outcomes are viewed.

## Non-negotiable data requirements

| Input | Required evidence | Current status |
| --- | --- | --- |
| Parent universe | Time-stamped actual NSE constituent notices and effective dates, not today's NIFTY 50 members | Pending independent verification |
| Prices | Actual properly adjusted stock return inputs for the relevant historical securities | Pending independent verification |
| Dividends/corporate actions | Event-date splits, bonuses, distributions, and exceptions | Pending independent verification |
| Value / Quality | Public financial-statement figures with original first-available dates and issuer identities | Pending independent verification |
| Benchmark | Official period-compatible total-return index, not an unadjusted Dhan spot price index | Pending independent verification |
| Delisted names | Historical identifiers, recoveries and survivorship-sensitive treatment | Pending independent verification |
| Sector/industry | Actual historically effective classifications, not modern labels silently backfilled | Pending independent verification |
| Liquidity and costs | Historical volume, tradability, turnover, brokerage, slippage, market impact and relevant taxes | Pending independent verification |
| Independent review | Named source reviewer, dated corrections, unresolved exceptions and licensing eligibility | Pending external review |

Dhan can supply historical observations, not the complete evidence above.
The application's Data Passport displays available files and blockers and
does not automatically approve any source category.

## Methodology

1. Register the research hypothesis in **Research Workspace → Index Research
   Studio → Publication & Protocol**, recording evaluation metrics and splits.
2. Import or prepare the actual historical source using the canonical market
   cache. Keep original source files unchanged and preserve SHA-256.
3. Review historical parent membership against dated source evidence; reconcile
   stock identifier changes, delisting and eligibility.
4. Normalize published fundamentals only at their first known availability,
   never at period end or a future publication timestamp.
5. Standardize factor scores cross-sectionally on eligible securities using
   documented clipping and missing-data rules. Run factor IC diagnostics.
6. Set factor weights and weight caps ex ante; reconstitute only on scheduled
   decision dates. Enforce historical sector constraints using effective dates.
7. Simulate explicitly delayed entries and drifting holdings, independent
   benchmark-relative risk, turnover and cost assumptions.
8. Test on development and validation; freeze parameters; evaluate only once
   on the held-out final segment, including multiple-testing caveats.
9. Use the constituent explainer to audit ten sampled inclusions/exclusions;
   generate source-checked methodology and one-command numerical reproduction.
10. Commission independent source and methodology review before describing
    the result as investable historical performance.

## Study A: Multi-factor methodology versus parent benchmark

Compare fixed preregistered factors and factor blends on identical
constituent universes, return conventions and evaluation dates. Record both
positive and negative findings. Avoid selecting the winning blend using
test-period results.

## Study B: Benchmark-relative risk under constraints

Provide dated benchmark_weights.csv with every tracked ticker (explicit
zero weights included) and real factor_returns.csv with 1–12 documented
factor-proxy return columns. Train beta risk strictly before the analysis
date. Compare estimated factor/specific risk, sector exposure, tracking
error, and realized outcomes. Risk is a model estimate, not an audited
MSCI/Barra risk model or a causal explanation.

## Study C: Historical-data and selection-bias robustness

Compare (a) fully documented PIT universe against a knowingly static-universe
*demonstration* and (b) a compatible total-return benchmark against an
unadjusted price-index reference, provided both are actually available.
Record how the interpretation changes, never silently use one convention
for another. Repeat over multiple fixed evaluation windows without selecting
the strongest after seeing the results.

## Reproducing a completed observed-data study

    git switch main
    bash run.sh
    # Visit Research Workspace → Index Research Studio → Data Passports
    # Select actual source, inspect blockers and run Index Studio preflight
    # After an approved archived experiment:
    python scripts/reproduce_study.py --run-id <local_archived_run_id>

The exported methodology ZIP contains exact source hashes, parameters,
descriptive results and a reproduction command, **not licensed raw OHLCV**.
The raw original data must remain accessible locally to rerun.

## Publish only when supported

A résumé or paper may cite completed software engineering features, algorithms
and test counts when verified. Do **not** cite strategy outperformance,
historical alpha, institution-certified factor scores or real market profitability
until authentic source evidence and a reproducible empirical run support them.

**Evidence categories still unverified as of publication of this protocol:**
actual PIT universe completeness, dividend-reinvested stock returns, official
TRI alignment, all delisting events and broker execution. Synthetic fixtures
are explicitly labeled and cannot resolve these gaps.
