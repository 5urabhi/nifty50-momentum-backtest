# QuantLab Research Workstation — Roadmap Acceptance Register

**Scope:** Feature branch feature/quantlab-model-laboratory-and-guide-20261113.
**Date:** November 13, 2026. **Evidence:** Repository implementations and
automated CI (not a substitute for interactive browser acceptance).

The roadmap's software features were implemented with explicit limits.
Where the original vision described a general research tool, QuantLab uses
a *bounded local-first implementation* whose output is numerical evidence,
not a representation of live trading profitability.

| Roadmap area | Implemented acceptance behavior | Relevant implementation |
| --- | --- | --- |
| Dataset management | User-visible labels, tags, descriptions, favorites, protected archive/Trash/restore/purge | research_library.py |
| Shared-price reuse | Canonical Dhan data reused across NIFTY/BANK NIFTY and derived dataset views | shared_market_data.py, model_data_manager.py |
| Smart data need (+20%) | Minimum sample and target, explicit extension offer; only uncovered mapped Dhan windows; no fabricated sessions | model_data_manager.py, ModelLaboratory.tsx |
| Download estimates | Suggested date scope and upper-bound weekdays, clearly not a vendor invoice | model_data_manager.py |
| Saved configurations | Save, load, duplicate, favorite; autosaved unfinished draft | ModelLaboratory.tsx |
| Experiment history | Source-checked result snapshots with Git and numerical environment when available; paginated run discovery | model_lab.py, app.py, ResearchWorkspace.tsx |
| Model result management | Rename, tag, favorite, duplicate archival evidence, archive/Trash/restore | research_library.py, ResearchWorkspace.tsx |
| Report library | Generate/edit/export HTML, Markdown, PDF; frozen vector figures | research_library.py, report_charts.py |
| Compare Studio | 2–8 saved models, aligned compatible outputs, separate 2D/3D, rebasing/z-score | research_insights.py, ResearchWorkspace.tsx |
| Graph Studio | Colors, axis titles, positive-Y log display, annotations, trace visibility, time range, reusable template | ResearchAdvanced.tsx, ResearchWorkspace.tsx |
| General Plot Builder | Real observed columns with line/scatter/histogram/KDE/QQ/drawdown/cumulative/rolling vol/correlation | research_advanced.py, ResearchAdvanced.tsx |
| 3D mathematical graphs | Interactive rotate/zoom/key controls; source-computed static report warning | ResearchPlots.tsx |
| PNG/SVG/CSV/JSON/HTML | Direct figure exports; self-contained 2D HTML pan/zoom | ResearchAdvanced.tsx |
| Data Quality | Source SHA-256, missing/nonpositive, extreme jumps, stalled series, freshness, weekday gaps, audit limits | research_insights.py |
| Jobs | Persisted job history, stage/percentage, queue cancellation and checkpoint cancellation for supported tasks | app.py, research_library.py |
| Research Projects | Structured goal, notebooks, saved figures and findings | ResearchWorkspace.tsx, research_library.py |
| One-click Add to Report | Directly attach graph/run to notebook; old calculations frozen | app.py, research_library.py, ResearchWorkspace.tsx |
| Notebook reruns | Re-execute saved validated Python settings; retain previous run ID | ResearchWorkspace.tsx |
| Portable project bundles | ZIP checksum, metadata/figures/metrics summaries; safe import with ID remapping and no raw licensed data | project_bundles.py |
| Parameter sweeps | Run 2–16 validated one-axis configurations on the real Python model engine | research_insights.py |
| Multi-parameter grid | Validate up to 36 one/two-axis variants before approved execution, numeric response heatmap | research_advanced.py |
| Workload preview | Relative work units and count rather than fabricated wall-clock estimate | research_advanced.py |
| Chronological holdout | Training-only constituent eligibility and strictly later test dates; full CSV + bounded plot | research_insights.py |
| Stress analysis | Explicit hypothetical asset shocks with contribution table and assumptions | research_insights.py |
| Statistical Significance | HAC/ARCH/Jarque–Bera/Ljung–Box, block-bootstrap, Holm corrections and unavailable p-values | research_advanced.py |
| Factor attribution | Earlier-fit observed-return proxy OLS, later holdout, no unverified fundamental factor claims | research_advanced.py |
| Reproducibility | Source file checksum and optional actual figure recomputation, execution environment checks | model_lab.py, research_insights.py |
| Guided vs advanced | Objective-based same model catalog vs direct mathematical controls | ResearchGuided.tsx, ModelLaboratory.tsx |
| Metric explanations | Clickable metric formulas and limitations, full linked reference document | ResearchGuide.tsx, docs/METRIC_REFERENCE.md |
| Favorites/recent work | Persistent metadata flags, recent library and custom dashboard | ResearchWorkspace.tsx |
| Autosave/undo | Model drafts, notebook drafts, graph editing undo/redo | ModelLaboratory.tsx, ResearchWorkspace.tsx |
| Keyboard & search | Ctrl+K global palette, Ctrl+Alt+1..8 main navigation | ResearchWorkspace.tsx, Workstation.tsx |
| Batch actions | Metadata item multi-select archive/Trash/restore, protected purge | research_library.py |
| Disk usage | Source/report/model/Trash disk overview, overlapping category caveat | research_library.py |
| Export/import settings | Portable browser preferences JSON (no Dhan token) | ResearchWorkspace.tsx |
| Custom dashboard | Pin six immutable model results and save workspace layout | ResearchWorkspace.tsx |
| Eight destinations | Main nav condensed; older functionality nested, not deleted | Workstation.tsx |

## Required acceptance and data cautions

Software-level unit/regression validation: CI checks strict TypeScript build,
Python FastAPI routes, Dhan cache and no-order policies, model calculations,
source isolation, dataset source protections, Chart/Report exports, OOS,
statistical tests, portable bundles and long-run downloadable artifacts.

**Manual workstation UI acceptance remains separate:** use an actual Ubuntu
browser to exercise responsive layouts, mouse drag/pinch and shortcuts,
downloaded file opens, Dhan credential configuration and large local
data/graph performance. A green GitHub test run does NOT prove those actions
were observed in a browser. Run the manual checklist below before merging.

1. Open a project, download only uncovered historical Dhan data, confirm
   existing dataset rows are appended and older downloaded windows reused.
2. Choose a historical model with insufficient observations; confirm both
   minimum and +20% target and explicit approval prompt.
3. Run a stochastic and an observed historical model; verify evidence labels.
4. Compare compatible saved results and inspect an incompatible 3D split view.
5. Build KDE, Q–Q, scatter and heatmap charts; export/open SVG, PNG, JSON and
   self-contained HTML; verify axes, markers and labels.
6. Save a chart, click Add to Report, rerun model notebook cell, generate and
   open PDF/HTML/Markdown report; confirm old result remains accessible.
7. Archive, restore, rename, tag, favorite, and duplicate model/dataset views.
   Confirm shared raw market history is protected from deletion.
8. Export and re-import project ZIP; inspect that secrets and raw licensed
   price files are excluded.
9. Run two-axis grid and chronological validation; check true progress and
   cancellation semantics; export and count the complete holdout-return CSV.
10. Test Ctrl+K, Ctrl+Alt+1..8, dark/light preferences and mobile layout.

## What must never be claimed by software alone

Unadjusted OHLCV does not equal audited dividend-reinvested total return.
Historical index membership needs valid point-in-time announcements.
External price adjustments, published fundamentals, delisting, borrow,
fee and market execution evidence are separate prerequisites for claims
of investable strategy performance. No trained Random Forest/XGBoost/LSTM/
PPO/SAC agents are claimed in the existing 26-model deterministic finance
catalog. No broker trading-order endpoints are used.

**Release decision:** merge only after the specific branch's complete CI
passes and meaningful local UI smoke tests are reviewed. The feature branch
can be run directly without merging.
