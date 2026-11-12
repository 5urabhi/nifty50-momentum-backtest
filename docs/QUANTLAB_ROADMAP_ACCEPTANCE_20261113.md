# QuantLab Research Workstation — Roadmap Acceptance Register

**Scope:** Main branch, merged through Pull Request #2.
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


## Verified release record (November 13, 2026)

GitHub PR #2 merged to main on merge commit
d5708c4c1d466f983389c627898c351deae224ac after CI validation.

- React TypeScript build and Python regression suite: **passed** on feature commit
  cb1afffd277975ad3098bd290b3e46d5f421df8f (workflow 43320383793).
- Actual Ubuntu 24.04 headless Chromium browser smoke: **11/11 steps passed**
  (workflow 43320383609, artifact 13990610928).
- Browser connected to real local Vite and FastAPI servers and exercised:
  all eight navigation destinations; observed-column plotting; chart saving,
  notebook attachment and interactive HTML export; statistics; parameter-grid
  preflight; generated PDF/HTML/Markdown report downloads; saved-run comparison;
  global search; metric help; and mobile navigation.
- Browser smoke also asserts no unhandled JavaScript exceptions and no
  backend HTTP 5xx during those flows.
- Fixtures are deterministic **synthetic CI test inputs**, clearly labeled;
  no broker credential was present, no orders were placed, and no shared
  licensed market observations were modified.
- GitHub workflows are configured to run on future main pushes and PRs.

**Scope of verification:** automated browser/system checks in GitHub Actions,
not a claim to have viewed or controlled the user's personal Ubuntu desktop.
A user-device smoke is recommended for their browser, historical data volume,
file permissions and Dhan token configuration. This is not a prerequisite to
the successful CI-validated merge but remains an environment-specific check.

**Run the merged application:**

    git fetch origin
    git switch main
    git pull --ff-only origin main
    bash run.sh

Open the local address printed by the launcher (normally
http://127.0.0.1:5173). No separate Vercel deployment is required or claimed.



## Additional research-depth software completion — PR #3 candidate

This increment addresses the previously identified software gaps without
pretending that independent external data is available:

- **Vendor comparison:** explicit one-instrument read-only Dhan history
  request after profile entitlement verification and user confirmation.
  Reports vendor/cache overlapping dates, mismatches and source checksum;
  no price overwrite and no broker order submission.
- **Evidence gate:** eight research criteria with a SHA-bound source-link
  ledger. Submitted provenance is never auto-certified. A source change
  invalidates previously submitted references.
- **Learning and RL:** train-only CPU ridge, random forest, histogram
  gradient boosting and four-state tabular Q-learning, with purged
  chronological training labels, fixed holdout policy, one-session delayed
  entry, explicit costs and full holdout CSVs. No production LSTM/PPO/SAC
  agent, unattended live execution or prediction-performance guarantee.
- **Graph Studio:** valid graph-type suggestions by series count, exact-X
  highlighted regions and event annotations preserved in exported report
  vectors.
- **Cache visibility:** pre-download details distinguish covered
  instrument-calendar days, uncovered windows and estimated only-new Dhan
  API requests. Canonical market-data reuse remains unchanged.
- **Expanded browser acceptance:** source-evidence status, learning sample
  sufficiency, actual trained holdout job, recorded chronology and
  downloadable CSV; all vendor probes remain mocked without credentials.

This is a *software implementation and automated verification* item.
**Live account connection** and **independent dividend/TRI/PIT/fee/fill
certification** still require actual third-party inputs and cannot truthfully
be marked done from isolated CI fixtures. Advanced LSTM/PPO/SAC architectures
are not part of this bounded study; do not label them completed.

Details: docs/RESEARCH_INTEGRITY_AND_LEARNING.md
