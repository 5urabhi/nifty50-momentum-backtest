# QuantLab — 12-Item Completion Acceptance and Remaining Evidence

**Last integrated software milestone:** PR #27 (November 14, 2026). This checklist distinguishes a delivered application capability from a completed *real-market* research outcome. Do not mark an empirical claim certified until evidence has been independently checked.

| Priority | Capability | Connected implementation | Software acceptance and residual limits |
| --- | --- | --- | --- |
| P0 | Unified research workflow | **Guided Research** is the default five-step Select data → Choose model → Run → Analyze → Save page. It embeds the existing Model Laboratory and Results Studio, not a parallel model engine. | Browser test covers a synthetic completed run and evidence ZIP. Real Dhan/model-family user acceptance remains device-dependent. |
| P0 | Intelligent data acquisition | Per-model input recovery, shared Dhan candle cache reuse, missing-date extension and confirmed imports; +20% preferred sample buffer. | Exact source availability and vendor entitlements are checked locally. Original TRI, PIT memberships and filings cannot be synthesized from prices. |
| P0 | Documentation cleanup | `GETTING_STARTED.md`, in-app five-step guide, advanced model guide, metric reference and this acceptance checklist. | External provider policies and every interactive edge case require ongoing review. |
| P0 | Financial units | Central `metricDisplay.ts` used by model, Results Studio, guided assistant, pinned dashboard and model metric comparison. Ratios dimensionless; percent only where source unit supports it; currency symbol only when declared. | Free-form CSV field names, legacy data imports and arbitrary custom plots may still need manual unit declarations. |
| P0 | Model readiness | Registry-backed minimums, exact selected symbols, source-specific actions, option-quote import and read-only Dhan access. | Readiness to compute is distinct from input correctness, out-of-sample evidence and publishability. |
| P1 | Financial results dashboard | Saved-run Sharpe, Sortino, CAGR, drawdown, volatility, beta, tracking error and matched benchmark statistics, when defined; source/audit warnings. | Theoretical or short-sample models cannot supply every financial return metric. Missing values remain unavailable. |
| P1 | Advanced chart interaction | Hover/keyboard, annotations, uncertainty bands, 3D rotation/zoom and 2D pan/zoom/reset plus synchronized crosshairs on identical date labels. Full CSV exports retain raw rows. | Date-only and equivalent midnight UTC labels synchronize crosshairs; zoom/pan require shared exact observed dates. No interpolation or unsupported comparisons. |
| P1 | Research job management | Bounded six-job local FIFO queue with **one serial worker**, queue positions, progress, cancellation only at checkpoints, eligible retry and source-specific error actions. | Explicit restart retry is available for source-hash-locked local research jobs only; data downloads, frozen-test consumption and unsafe jobs never auto-resume. |
| P1 | Dataset lifecycle management | Recoverable Trash, archive/restore, dependency-protected deletion, disk usage, vendor cache reuse, read-only byte-identical prepared view scan. | Only user-confirmed, byte-identical complete prepared views without dependencies can move to recoverable Trash. Raw Dhan cache is protected. |
| P1 | Experiment comparison | Saved overlays with compatible axes and strict paired return comparisons using identical source hashes, common calendar, matched benchmark and Holm-adjusted inference. | Different models may lack comparable economic estimands. A descriptive overlay is not a valid performance ranking. |
| P2 | Reproducibility | Saved results and source manifests, environment/code version, source-integrity audit, portable ZIP package and offline `verify_bundle.py`. | Licensed original source inputs are not shipped; full replication requires authorized inputs and matching environment. |
| P2 | Advanced statistical validation | Walk-forward/holdout; paired HAC and block bootstrap; CSCV/PBO, approximate DSR with declared trial count, lagged benchmark-volatility descriptive regimes. | CSCV is retrospective, **not purged CPCV**, and not a frozen independent final test. Original PIT/TRI/cost audits remain required. |

## Explicit authentic-source worklist

Experiment Studio now provides a **read-only missing-evidence worklist** tied to the actual selected dataset: exact missing security-months, missed next-month return observations, unresolved historical ticker identities, missing months, +20% preferred training history and source-specific NSE/Dhan import actions. One click exports a portable, source-safe ZIP containing identifiers and checksums **without licensed prices**. Python and Chromium acceptance enforce zero automatic source certification. A malformed calendar remains actionable and fails closed.

## Evidence gates that cannot be bypassed by software

- Authentic and licensed original NIFTY/BANKNIFTY historical constituent observations, all effective-dated deletions and changes, dividends and corporate actions.
- Index TRI and stock total returns aligned under the appropriate return conventions.
- Publication-dated financial statements and relevant original market/liquidity/execution records for the selected research design.
- Valid user-specific Dhan provider entitlements and local credential setup (never uploaded to GitHub).
- Predeclared chronological training/validation and untouched final testing, with independent source review.
- Comparison against a credible benchmark and realistic portfolio capacity/cost assumptions, not simply an attractive simulated Sharpe.

## Local software acceptance

On Ubuntu, `bash run.sh check` now validates the current React/FastAPI software path and research-source doctor; the archived Streamlit smoke is opt-in. GitHub Actions Chromium tests remain separate from this terminal command. The source doctor can report **NOT READY** when genuine licensed historical files are absent without causing a false software failure.


```bash
python -m unittest discover -s tests -v
npm run build
```

GitHub CI also runs real Chromium acceptance with isolated synthetic fixtures. In a live user setup, verify the full five-step journey, a mapped observed Dhan ticker and +20% data extension, quote access where applicable, failed/incomplete downloads, source-aware results, export ZIP verification, archive/restore, dependency blocking, and statistical comparisons over a sufficiently long original dataset. No source is independently certified merely because a test passed.
