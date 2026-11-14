# Advanced Model-Selection Validation in QuantLab

## Where this lives

Open **Results Studio → Overfitting & regimes**. Choose two to eight *saved index research runs* and declare **all previously tried configurations**, not just the surviving shortlist. The model-selection API is `POST /api/workspace/results/selection-audit`.

This analysis is deliberately **retrospective**. It does not create new market history, certify alpha, or assert that a final holdout has remained untouched. It requires an exact original dataset ID and matching file checksums, the same benchmark return series on aligned calendar dates, and at least 48 paired monthly returns. **48 is the mathematical minimum; about 58 or more is preferred under QuantLab's +20% historical-depth convention.** Four, six and eight partitions require at least 48, 72 and 96 common months respectively.

## 1. Combinatorial Symmetric Cross-Validation (CSCV) and PBO

QuantLab divides the matched return calendar into an even number of contiguous blocks (4, 6 or 8). For each combination of half the blocks, it ranks candidate strategies by **zero-risk-free-rate, in-split monthly Sharpe**, picks the highest-ranked candidate, and measures the candidate's out-of-split **rank among the same models** on the remaining blocks.

For each combination, the percentile of the selected model's out-of-split rank is transformed to a logit. The **Probability of Backtest Overfitting (PBO)** estimate is the fraction of combinations for which that logit is below zero—meaning the in-split winner fell below the out-of-split median. With four blocks there are 6 combinations, with six there are 20, and with eight there are 70.

This measures **selection instability on the archived candidate family**, not the probability of a future portfolio loss. Tied or flat Sharpe values use documented conservative ranking. CSCV permits training blocks to occur after testing blocks in calendar time. It is **not** a chronological forward-only test. No event label end-times are available, so QuantLab **does not implement or claim purged CPCV, embargo or event-overlap prevention** here.

## 2. Approximate Deflated Sharpe Ratio (DSR)

A strategy selected from many tested configurations has a Sharpe statistic biased upward by selection. QuantLab estimates an expected maximum Sharpe hurdle using a declared trial count, sample length and a normal-maxima approximation, then adjusts for the selected strategy's sampled skewness and kurtosis. It displays a conditional normal-CDF probability and both the selected annualized zero-rate Sharpe and adjusted hurdle.

**Critical assumption:** The user must declare **every** tried configuration, including discarded and earlier runs. The software cannot infer an undisclosed search history from two saved finalists. The calculation assumes approximately iid-like Sharpe estimation and a simple effective-trials approximation. Serial dependence, correlated candidate strategies, nonstationarity and non-normal tails can make the probability unreliable. **Do not interpret the displayed value as a certified p-value for investable alpha.**

If the sample is too short, variance too small, or moment estimates non-finite, the endpoint returns a reason rather than fabricating confidence.

## 3. Trailing benchmark-volatility regimes

Each saved month is assigned to low, middle or high trailing benchmark-volatility regime using only its **prior** 3, 6 or 12 monthly benchmark returns for that label. Within these groups, the engine reports the candidate's arithmetic monthly strategy and active means and the fraction of negative months.

**The regime boundaries themselves are retrospective terciles fitted on the whole archived sample.** They are useful for descriptive diagnostics, not a prospective trading signal or a causal explanation of returns.

## 4. Data and comparison constraints

The engine reuses QuantLab's paired-comparison gate before model-selection statistics:

- Source dataset IDs, original input SHA-256 hashes, benchmark convention and saved benchmark return values must agree.
- All measured strategy/benchmark returns must have valid, nonduplicated, chronological dates, and only the intersection of actually saved dates enters the analysis.
- The original return basis and transaction-cost assumptions must still be audited separately. A matching CSV hash does not establish economic truth.
- Synthetic inputs remain **SYNTHETIC DEMONSTRATION**, even if every numerical test runs successfully.
- Full Dhan history and official NIFTY TRI, publication-dated filings, PIT constituent histories, corporate actions, broker spreads and realistic execution are separate evidence requirements.

## 5. Chronological validation and final testing

Use **Research Workspace → Research Tools → Walk-forward / holdout** for strictly ordered recalibration and future-fold evaluation. Use separately source-bound, **single-use frozen final-test** features before looking at held-out outcomes. Do not tune on a final test and then treat it as fresh. The advanced selection audit complements these steps; it does not replace them.

## Reproduce the numbers

Select a candidate family and export **Complete audit JSON** from Results Studio. It records each source hash, aligned dates, chosen folds, winner frequency, individual PBO split outcomes, declared trial count, DSR assumptions, regime thresholds and descriptive regime table. Retain the original archived runs and source manifests. The endpoint is read-only: it changes neither your datasets nor research configurations.

Run tests with:

```bash
python -m unittest discover -s tests -p 'test_selection_diagnostics.py' -v
```

The synthetic CI fixtures test implementation behavior—not independent market-data accuracy, causal factor effects, or live execution.
