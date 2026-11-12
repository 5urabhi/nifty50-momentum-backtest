# QuantLab Research Workspace — Complete User Guide

**Local-first Multi-Factor Equity Index Construction, Stochastic Modeling & Quantitative Risk Research**

This manual describes the implemented Research Workspace on the
feature/quantlab-model-laboratory-and-guide-20261113 branch. Calculations run
in the existing Python/FastAPI process; React displays results. No broker
orders are submitted. Source prices are not silently synthesized.

## Start the workstation

From the directory containing run.sh:

    git fetch origin
    git switch feature/quantlab-model-laboratory-and-guide-20261113
    git pull --ff-only origin feature/quantlab-model-laboratory-and-guide-20261113
    bash run.sh

Open http://127.0.0.1:5173 . The API and documentation are on the same
machine, via the Vite /api proxy to localhost port 8765. Store your Dhan
token ONLY in the ignored local .env, never in a browser or report.

## Navigation

QuantLab opens the Research Workspace in the sidebar by default. Other
research engines (Index Research, Factor Laboratory, Advanced Mathematics,
Quantitative Models, Risk Attribution) remain available.

| Research Workspace tab | Use |
| --- | --- |
| Start | Resume research, guided tasks, recently saved items |
| Library | Manage datasets, model runs, index runs, saved presets, charts, notes and reports |
| Compare & Graph | Overlay compatible saved graphs; split independent 2D/3D panels |
| Projects & Notes | Create projects, structured notebooks and HTML/Markdown/PDF reports |
| Research Tools | Parameter sweeps, chronological portfolio validation and scenario shocks |
| Data Quality | Inspect missing dates/prices, possible unadjusted jumps, stalled series, disk usage |
| Jobs | Monitor queued and completed Python work, cancel queued tasks, retry safe failed tasks |

Press Ctrl+K **while the Research Workspace is open** to search records,
datasets and saved results. Escape closes the search palette.

## 1. Manage datasets and saved results

Under Library, choose **Datasets & results**, **Saved work**, or **Trash**.
Filter by asset name, model type or tag.

For derived datasets, the archive and trash actions use distinct semantics:

* **Archive:** hides the dataset or result from everyday library screens.
  Its underlying files remain intact, so re-running the configuration is possible.
* **Move to Trash:** moves a user-imported dataset, a derived Dhan batch dataset,
  or an existing research result to a local recoverable directory.
  Its original location becomes unavailable until restoration.
* **Restore:** moves the trashed resource back if its original path is free.
* **Permanently delete:** requires an additional confirmation; the action is
  irreversible. Raw shared Dhan candle cache and canonical shared market data
  are deliberately excluded.
* **Reference protection:** a dataset with dependent saved model runs,
  experiment runs or notes cannot be trashed through the API until the
  references are handled. Archiving is available instead.

Saved configurations, charts, notebooks and reports are JSON-backed
metadata records in data/research_workspace/library.sqlite3.
They can be renamed, favorited, archived, restored and placed in Trash.
The bulk toolbar supports safe multi-selection for metadata records.
Exports generate local JSON, CSV, SVG and PNG where the selected artifact
supports those formats.

Data is **not** duplicated when the same NSE equity appears in NIFTY 50,
BANK NIFTY or a custom watchlist. Canonical Dhan closes are keyed by exchange,
Security ID and date in data/dhan/shared_market.sqlite3. Dataset definitions
are different from raw canonical price files. Deleting a dataset view must not
delete prices needed by another analysis.

## 2. Save and reuse model configurations

In Advanced Mathematics or Quantitative Models select your model, dataset,
mathematical parameters and any random seed. Under **Reusable model
configurations**, click **Save current configuration** and give the preset a
meaningful name.

Later use **Load** to restore its parameters, source dataset and model family.
Presets can also be copied, favorited or trashed. Unfinished parameter edits
are locally autosaved per model in the browser. Autosave is convenience only:
a named preset is the durable, shareable research record.

Every successful Python model run is separately snapshotted under
results/model_laboratory/. Source files are SHA-256 checked when available.
After extending a shared dataset, new runs use the enlarged sample, but the
old result still describes its own prior source checksum.

## 3. Compare saved results and design graphs

In **Compare & Graph**:

1. Select two to eight saved model or index-experiment runs.
2. For multi-figure runs choose the exact figure you want.
3. Select the comparison layout:
   * **Overlay:** align X observations; require compatible units and
     evidence classes. Intersections do not forward-fill missing values.
   * **Independent figure panels:** compare otherwise incompatible
     2D/3D plots side by side, explicitly labeled as different outputs.
4. Decide whether to preserve original units, **rebase positive level
   series to 100**, or **standardize to z-scores**. The last two operations
   change interpretation; they do not create equivalent evidence.
5. Customize the title, chart format, visible range and annotation.
6. **Save comparison** persists the settings and linked runs.
   **Save graph** persists the layout/plot snapshot.
7. Export CSV/JSON for numerical results or SVG/PNG for a visible chart.

2D/3D surface data is generated by the Python research engine. A 3D surface
is not overlaid with an unrelated line graph, because doing so would imply
mathematical compatibility that has not been established.

**What counts as a valid comparison?** Confirm common trading periods,
return conventions, adjustment basis, currency, risk-free assumptions and
whether results are theoretical, simulated or empirically observed.
A visually better in-sample curve is not evidence of predictive power.

## 4. Research projects, notebooks and reports

Projects organize a research question, hypothesis and scope.
Create a project and one or more notebooks under **Projects & Notes**.

Each notebook supports a sequence of saved cells:
* Text or mathematical assumptions
* References to immutable saved model runs
* Figure notes and table/findings descriptions

Cells can be reordered and edited. Notebook changes are automatically saved
after a short pause; **Save notebook** writes immediately. Raw Python code
and arbitrary HTML are not executed from notebook cells.

**Generate report** creates downloadable HTML, Markdown and PDF snapshots
from the saved notebook. Reports can be edited as text; editing updates all
three exports while leaving original model computations unchanged.
The PDF uses a paginated, selectable-text layout. Always inspect generated
reports before external publication.

Full historical index reports may also contain separate HTML and PDF
artifacts generated by the original Index Research report pipeline.

## 5. Research automation with valid computation

### Parameter sweeps

Choose a registered mathematical model, one numeric parameter and 2-16
distinct parameter values. For observed models choose a dataset.

The backend executes each configuration using the actual Python model
implementation, validates numeric bounds, and saves every successful result
with its parameters. A parameter-response plot and associated run IDs are
saved as a research study.

**Critical caveat:** Choosing the best value from in-sample or simulated
figures is not a valid holdout selection protocol. Freeze a separate
validation and final test design before making performance claims.

### Strict chronological validation

Available portfolio allocation methods: equal weight, inverse volatility,
minimum variance, risk parity and maximum diversification.

Select a historical dataset, asset count, training-window length, holdout
step and a feasible maximum weight. Choose one frozen holdout or rolling
recalibration. The backend estimates each portfolio using dates strictly
before that fold's test window and evaluates the fixed weights only on
subsequent observed returns.

Outputs include fold dates, estimated portfolio weights, net-of-no-cost
hypothetical return path, equal-weight baseline, return/risk metrics,
historical tail loss and a circular moving-block bootstrap interval for
active returns. The block bootstrap is exploratory, and repeated model
selection can invalidate nominal confidence coverage.

This is NOT point-in-time index certification or live-trading validation:
unadjusted stock prices, dividends, delistings, independent benchmark
provenance, execution costs and realistic fills remain important.

### Hypothetical scenario shocks

Select an observed saved portfolio-model run and enter asset shocks as
decimal fractions, e.g. SYMBOL=-0.05. The engine checks asset membership
and computes simple weighted contribution. If optimized weights cannot
be reconstructed from the stored result, it explicitly uses an illustrative
equal-weight basket. This is a linear instantaneous price shock—not a
nonlinear options simulation.

### Reproducibility

Every saved model run can be SHA-256 checked against its recorded source.
Recompute/compare can also rerun seeded and theoretical models and compare
their figures. Unchanged input bytes are necessary but insufficient for
external data correctness. Python/library versions matter.

## 6. Data-quality and storage center

Select an observed dataset and run the audit. The Data Quality tab reports
price dates, columns, invalid or duplicated dates, missing prices,
non-positive observations, moves larger than 40%, and recent constant
series. Outliers are flags for human source audit, NOT proof of an error;
a raw unadjusted split can look like an extreme return.

Disk usage separates raw Dhan history, canonical shared data, prepared
datasets, research results, model runs, reports and Trash. Do not delete
canonical prices simply to remove a derived dataset view.

## 7. Job lifecycle and safe recovery

The Job Manager shows queued, running, completed and failed tasks.
Queued jobs can be cancelled. Running numerical tasks do not promise
immediate interruptibility. Failed local research/report jobs may be
retried while their original configuration remains in this server process.

A compact job summary is stored in the workspace SQLite database.
After a server restart, unfinished jobs are labeled interrupted rather
than reported as completed. For reliable reproduction, use the saved
study/configuration and submit a new job.

## 8. Keyboard, display and privacy

* Ctrl+K: open local research search while the workspace is mounted.
* Escape: close the search palette.
* Favorites and recent-item panels help resume work.
* Dark and light workspace theme preferences are saved in browser storage.
* Model setup drafts are also saved locally, not sent to Dhan.
* Credentials are never included in saved configurations, chart templates
  or generated notebook reports.
* This is a loopback-only single-user workstation, not a cloud application
  with multiuser authentication.

## 9. Automated acceptance checks

The repository CI verifies the React/Vite TypeScript build, Dhan cache
and research core regressions, plus the Research Workspace's:
record lifecycle, dataset Trash safety, aligned model comparison,
strict chronological holdouts, actual parameter sweeps, source
reproducibility, data quality, and report HTML escaping.

    python -m unittest discover -s tests -p 'test_research_workspace.py' -v
    python -m unittest discover -s tests -v
    npm run build

## 9A. Pinning results and moving preferences between browsers

The Start page includes **My custom research dashboard**. Choose up to six
saved model-run IDs. QuantLab retrieves their archived numerical metrics and
first figure and places them together on a personal dashboard. Pinned items
are stored locally in browser preferences. A named dashboard can also be
stored in the research library and restored later.

The **Research workspace settings** panel can export and import a JSON
bundle containing local interface preferences, saved view layout controls,
pins and model configuration drafts. It does not export market prices, saved
model results, Dhan credentials, or secrets. Reload the app after importing
preferences. Use the research library and notebook export for actual saved
research artifacts.

## 9B. Putting real saved figures into a notebook report

First build a chart in **Compare & Graph**, then click **Save graph**.
Open **Projects & Notes**, select your notebook and add **Saved chart
figure**. Choose the saved chart and add your interpretation. The notebook
shows the actual saved figure, not merely a text placeholder.

When generating a report, QuantLab freezes up to 16 selected figure
snapshots. Two-dimensional series are embedded as safe, selectable SVG
vectors in HTML and vector shapes in PDF. Some interactive 3D surfaces
cannot be meaningfully flattened into the same two-dimensional report;
those figures retain their numerical source and a disclosure directing
readers to the full interactive QuantLab surface. Editing the written
report preserves its frozen figure snapshots even if a source chart is
later archived or moved to Trash.

## 10. Important limitations

QuantLab can run 26 registered mathematical, stochastic, option,
optimization and tail-risk models, but it does not assert the presence of
trained PPO/SAC/LSTM/Random-Forest agents. The new automated research tools
are Python implementations of their documented methods; **nothing is
pretending to be a trained alpha model**.

The optional +20% buffer in model readiness is additional observations,
not an automatically valid test split. Historical constituent membership,
source-dated fundamentals, corporate actions, dividends, delistings and a
compatible TRI benchmark require separate evidence, even when the shared
daily-price store is complete. The software does not send broker orders.


---

# Research Workspace v2 — Advanced Guide (November 13, 2026)

## Eight destinations, preserving the original research modules

The sidebar now has eight main destinations: Home, Data Library, Model
Laboratory, Experiment Studio, Compare & Visualize, Results Library, Research
Projects, and Help & Settings. Earlier model/risk modules remain available
in nested navigation. The Research Workspace has Start, Library, Compare &
Graph, Plot Builder, Guided & Grids, Projects & Notes, Research Tools,
Data Quality and Jobs.

Press **Ctrl+K** from the Research Workspace to search saved results,
datasets, mathematical models and documentation. Escape closes the palette.

## Plot Builder, Graph Studio and outputs

Open Compare & Visualize -> Plot Builder, choose observed source data and
numeric columns, then select line, two-series scatter, histogram, KDE,
normal Q–Q, drawdown, cumulative wealth, rolling volatility or correlation
heatmap. Choose original price, simple return, log return, base-100 or
z-score. Graph types reject mathematically inappropriate columns and the
engine never forward-fills missing return samples.

Graph Studio supports 2D multi-series overlays, trace hiding, colors,
user axis labels, optional log10 transform for positive Y values, exact
X-axis event markers, annotations, and saved chart templates. Exports
include SVG, PNG, CSV, JSON and self-contained 2D HTML with pan and zoom.
The 3D mathematical surfaces offer interactive drag/keyboard rotation and
zoom in QuantLab; full 3D interactions are not flattenable into PDF.
Supported 2D scatter/heatmap/line plots export as static PDF/HTML vectors.

A saved figure can be attached directly to a selected research notebook
using the **Add to report** action in Plot Builder or Compare & Graph.
Notebook reports freeze the saved numerical figure snapshot.

## Statistical Center

Statistics & Diagnostics computes nominal Jarque–Bera, Ljung–Box and
ARCH LM tests on observed returns, with named assumptions and caveats.
Return-series factor-proxy attribution estimates OLS using earlier returns,
then evaluates unchanged coefficients on a later holdout. These are proxies,
not publication-dated fundamental risk-factor libraries.

The Significance Center reads saved chronological validation return CSVs,
computes Newey–West HAC mean statistics, moving-block bootstrap intervals
and Holm-adjusted p-values. If an active-return series has zero variance,
a p-value is unavailable, not significant by default.

Help & Settings -> Metric Guide includes clickable definitions, formulas,
interpretation, and limits for VaR, ES, Sharpe, Sortino, drawdown, HHI,
factor exposure and common inference metrics. The comprehensive formula
reference is docs/METRIC_REFERENCE.md.

## Guided and Advanced modes; multi-parameter grids

Guided & Grids supports rule-based model selection by objective:
portfolio allocation, volatility, tail risk, stochastic models, derivatives
or factor proxies. Guidance comes from the same actual model catalog as
Advanced Mathematics. For historical models, data-readiness shows required
common observations, missing count and preferred **+20% buffer**.

When available, the local Dhan data extension prompts for explicit user
approval. It requests only uncovered mapped date windows, reusing the shared
NIFTY/BANK NIFTY stock price cache. The estimated date scope represents
calendar weekdays, not a guaranteed NSE session count or provider quote.

Multi-parameter grids validate one or two numeric axes before allowing
execution; they cap a grid at 36 saved real Python runs, calculate relative
work units, and save the parameter-response graph/heatmap. Relative work
units are not a promise of wall-clock time. Optimization dashboard compares
saved metrics without replacing missing entries with fabricated zeros.
Research Tools also contains single-axis sweeps, historical walk-forward
validation, stress decomposition and source/recompute audits.

## Library metadata, versioning, notebooks and portable projects

Library resource details support rename, tags, description and favorites
for datasets, saved model runs and saved index experiments. Model runs may
be duplicated as clearly labeled copies of the original mathematical
output; a duplicate does not constitute a new independent model execution.
Shared Dhan data is protected from user-level dataset deletion.

Research metadata supports batch archive/restore/Trash, favorites and
search. Dataset dependencies block unsafe deletion. Research notebooks
support re-running a referenced saved model with its recorded parameters
while retaining earlier run identifiers for comparison. Old numerical
results are never overwritten.

Export portable project ZIP creates a checksum-manifested package of
project-linked safe JSON metadata, figures, settings, and metrics-only
summaries of referenced model runs. It excludes raw licensed OHLCV, secret
tokens and executable source code. Import creates independent local IDs
and remaps saved chart references; old run summaries are non-executable.
Rebind market sources and rerun rather than treating imported summaries
as live verified data.

Reports are editable text and can be downloaded as HTML, PDF and Markdown.
The source notebook and supported charts are independently retained.

## Job progress, quality audits and reproducibility

Jobs now shows stage-level percentage for parameter sweeps, grid research,
and chronological validation. Running numerical tasks can be cancelled
only between safe checkpoints. The Job Manager marks tasks interrupted
after a Python restart; it never represents an interrupted calculation
as successful.

Data Quality reports invalid/duplicate dates, missing prices, extreme
returns, flat series, data freshness, source SHA-256 and weekday gaps.
Weekday counts include NSE holidays and do not certify a missing exchange
session. A deliberately old research window may appropriately be stale.

Newly saved model runs record source SHA-256, model parameters and
execution time, plus Git commit (when locally available), Python, NumPy,
pandas and SciPy versions. The Reproducibility Checker distinguishes
unchanged source input from actual deterministic recomputation.

## Automated acceptance

Run from the repository root:

    npm run build
    python -m unittest discover -s tests -p 'test_research_advanced.py' -v
    python -m unittest discover -s tests -p 'test_research_workspace.py' -v
    python -m unittest discover -s tests -v

Even a passing regression suite does not certify historical investability.
Corporate actions, dividends, delistings, point-in-time index memberships,
risk-free rates, benchmark TRI, fees, and broker execution must be independently
audited. A +20% sample buffer is not itself a valid holdout. The workstation
never sends broker trading orders.



## Evidence & ML (additional research integrity workflow)

From **Compare & Visualize → Research Workspace → Evidence & ML**, you can:

- Examine source hashes, dated PIT membership, dividend/corporate-action,
  benchmark TRI, delisting, vintage fundamentals, costs and prospective
  execution evidence requirements. Source links are **submitted/unverified**
  and turn stale when the original price file changes.
- Run a user-approved **read-only Dhan sample comparison** for one actually
  mapped instrument. This compares saved closes to the current vendor
  endpoint, records overlap/mismatches, and never overwrites OHLCV or submits
  orders. A real credential is still necessary on your local machine.
- Train CPU Ridge, Random Forest, Histogram Gradient Boosting or long/cash
  tabular Q-learning on daily research data using purged historical training
  and later chronological evaluation. The result includes a one-bar
  execution delay, explicit transaction costs, a saved graph and complete
  downloadable holdout observations.
- Inspect explicit minimum and preferred (+20%) historical sample lengths
  before training. Download shortfalls using the existing canonical Dhan
  manager, never by creating a duplicate NIFTY/BANK NIFTY price dataset.

The Data Requirements panel now estimates existing cached instrument/date
coverage, genuinely uncovered windows, and newly needed vendor request
chunks using verified cache manifests. These are estimates, not a Dhan bill.

Read docs/RESEARCH_INTEGRITY_AND_LEARNING.md for the formula, as-of data
limits, and live-check instructions. No source link, vendor sample match or
trained retrospective model establishes independently certified alpha.
