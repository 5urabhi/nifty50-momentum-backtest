# QuantLab — Three Studies: Execution and Research Acceptance

**Current software status:** Research pipeline implemented; empirical validation of real NIFTY historical performance is **not complete**.

The source-aware runner `scripts/complete_research_studies.py` joins the previously separate study protocols into an executable, inspectable workflow. It does **not** download proprietary/licensed market history, submit broker orders, or certify any public return claim.

## Before execution

Use a local folder containing `prices.csv`, `membership.csv`, and `benchmark.csv` on the **same observed monthly calendar**. Value/Quality/Size also require first-available-date `fundamentals.csv`; constrained sector research requires effective-dated `sectors.csv`. Complete `corporate_actions.csv` and human-reviewed source evidence are indispensable before publication.

For fully evidenced Indian equity research, provide and review:

1. Actual historical effective-date NSE membership notices and security identities, including delisted and renamed names. QuantLab's independent reconstructed PIT source is a *starting point*, not a primary-source audit.
2. Complete, appropriately adjusted prices with confirmed Dhan split/bonus convention, independently checked cash dividends and terminal corporate outcomes. An empty events CSV does **not** establish that there were no events.
3. Official NIFTY total-return index levels with a prior monthly close, compatible sampling dates and documented license. Dhan spot index candles are *not* a TRI.
4. Original first-public-date financial statements and historical market capitalization for Value/Quality/Size. Never use current fundamentals for past formation dates.
5. Effective-dated historical sector mapping, benchmark constituent weights, authentic factor proxy return series, realistic trading costs and explicit timestamped execution assumptions.
6. A frozen analysis plan and untouched test-period design, recorded *before* evaluating holdout results; independent source/methodology review is still mandatory.

See `docs/EMPIRICAL_DATA_GUIDE.md`, `docs/CASE_STUDY_NIFTY_MULTIFACTOR.md`, and `docs/RESEARCH_INTEGRITY_AND_LEARNING.md`.

## Commands (local Ubuntu, repo root)

Preflight only — **no files are modified and no studies execute**:

```bash
python scripts/complete_research_studies.py \
  --data-dir data/research_v1 \
  --config config/research_multifactor.json
```

Execute on actual validated local input **after freezing the configuration**:

```bash
python scripts/complete_research_studies.py \
  --execute \
  --data-dir data/research_v1 \
  --config config/research_multifactor.json \
  --output-dir results/three_studies_20261113
```

Each output path must be new to prevent accidental overwrite. Check `PREFLIGHT.json`, then `THREE_STUDIES_RESULTS.json`, `RESEARCH_MEMO.md`, the full index study folder and the safe `PUBLICATION_SAFE_EVIDENCE.zip`. The ZIP contains **no raw vendor data**, so reproduction requires access to the unchanged original local source folder. Compare source SHA-256 values against the preflight manifest.

### Study A — Multi-Factor Index Construction

Executes the actual cross-sectional factor ranking, constrained reconstitution and return simulation through the shared `index_research.experiment` engine. Reports development/validation/final-test descriptive results and exploratory HAC/block-bootstrap uncertainty on the final holdout. **A computed p-value is not proof of outperformance**; exploratory selection and multiple testing may invalidate its interpretation.

### Study B — Benchmark-Relative Factor Risk

Requires optional `factor_returns.csv` (1–12 named monthly factor proxy return columns) and `benchmark_weights.csv` (date,ticker,weight; all modeled names including zero weights). Uses strictly earlier historical observations to fit factor exposures, then decomposes annualized active variance into `B F Bᵀ` and security-specific risk. The pipeline **reports unavailable** when the required inputs are absent; it does not synthesize them. This is a transparent OLS proxy risk estimate, not licensed MSCI/Barra output or causal attribution.

### Study C — Data Integrity and Robustness

Reports how many historical security-month eligibility decisions disagree with using only the *final* constituent universe. That is a **contamination diagnostic**, not a quantitative estimate of survivorship alpha. Where independently obtained `benchmark_price_only.csv` exists with matching dates, reports the index price-versus-total-return convention difference. Also reports observed **modeled** cost drag, not broker fills.

## What constitutes completion

| Gate | Current evidence | Result |
| --- | --- | --- |
| Code paths and unit/integration CI | GitHub workflow checks | Check current PR CI; never infer external market accuracy |
| Automated Chromium browser | GitHub Actions smoke for mock/synthetic data | Does not exercise user's local Dhan entitlement |
| Original PIT stock-history review | Independent third-party reconstruction available | Official notices, corrections and coverage not fully reviewed |
| Proper total-return security prices | Event handling and importer code | No complete independently audited data folder in repo |
| Official benchmark TRI | Import utility with explicit no-imputed-first-month policy | Source levels, rights and dates still needed |
| As-published factor fundamentals | Date-aware import machinery | Genuine historical filing vintages still needed |
| Complete index empirical holdout | Executable study A | Needs real reviewed inputs, frozen design and source review |
| Factor risk validation | Executable study B | Requires genuine factor returns and benchmark weights |
| Selection-bias and robustness study | Executable study C | Full counterfactual performance experiment requires reliable PIT and static comparison |
| Independent reproduction and review | Saved source hashes, methodology bundles and replay | Needs reviewer and unchanged licensed input access |
| Recruiter demonstration | Tour, guide, feature code, storyboard | Final measured claims and recorded video not completed |

**For the résumé:** Until these independent gates are met, describe the **built and CI-tested Python/FastAPI/React research platform**, methodology, explainability, factor risk and provenance controls. Do **not** claim observed positive alpha, an independently verified NIFTY Sharpe ratio, or completed original-data validation.

## Technical limitations of this first pipeline

* The three-study workflow is a deterministic exploratory **research CLI**, not an unattended exchange-data harvester or institutional source certifier.
* Original data acquisition and exchange/vendor licensing are separate from code. The user must place permitted source exports in their local private data store.
* Study B estimates risk at one selected archived return period end, using previous-month formation information; it is not a complete multi-year active-risk backtest.
* Study C quantifies membership-state disagreement, not the performance effect of survivorship. Additional matched counterfactual runs will be necessary for a fully quantified historical bias study.
* Synthetic fixtures remain useful for CI and mathematical acceptance but cannot establish empirical NIFTY performance.
* Avoid altering the frozen study configuration after viewing final holdout results; use a new preregistered study for revisions.
