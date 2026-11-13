# QuantLab for researchers, interviewers and quantitative-index roles

**Product:** Independent, local-first Multi-Factor Equity Index Construction,
Stochastic Modeling & Quantitative Risk Research workstation.

**Not:** An MSCI/NSE commercial product, certified proprietary factor engine,
live trading system, or independently published profitable NIFTY strategy.

## A five-minute researcher tour

1. Run bash run.sh and open http://127.0.0.1:5173.
2. **Data Library:** inspect the observed dataset and its canonical Dhan
   historical-cache provenance. Existing cached instruments are reused.
3. **Compare & Visualize → Research Workspace → Index Research Studio →
   Data Passports:** inspect source SHA-256 files, original benchmark basis,
   historically dated membership evidence and unresolved blockers.
4. **Index Studio:** define factor weights, top-N constituents, security caps,
   reconstitution frequency, delayed execution and transaction costs.
   Click **Check assumptions & data** before executing.
5. **Why This Result?:** choose a saved index experiment. Beginner,
   Researcher and Mathematical tabs explain the archived calculation, not
   a fabricated causal reason. For index runs, select a security to see its
   exact effective-date membership, factor z-score contributions, rank,
   selection and reconstructed target weight.
6. **Active Risk:** supply dated benchmark_weights.csv and real named
   factor_returns.csv. The model estimates historical regression exposures
   and a B F Bᵀ + D factor covariance structure; no equivalent inputs means
   no claim of factor attribution.
7. **Publication & Protocol:** preregister your question before viewing the
   final test. Publish a frozen research methodology ZIP with input hashes,
   settings, results and reproduction command. Raw/licensed candles and
   credentials never leave the workstation.

## What makes it reproducible

- One source-of-truth Python factor/index engine shared by React and the SDK.
- Numerical seeds and run config recorded; source hashes checked at replay.
- Running the same inputs and settings produces comparable numerical tables:
  python scripts/reproduce_study.py --run-id <run-id>.
- Archived models and derived figures remain available after shared data
  extension. Old runs cannot be retroactively re-labeled as verified.
- Parameter-sensitivity and chronology tests, source-exact constituent
  explanations, notebook reports, and safe portable research bundles.
- Mathematical source tests, React/TypeScript builds and Ubuntu Chromium
  browser-acceptance flows, with artifacts attached to GitHub Actions.

## Python / Jupyter entry points

    from quantlab_sdk import QuantLabClient

    lab = QuantLabClient()
    sources = lab.datasets()
    methods = lab.models()
    passport = lab.data_passport("synthetic")
    assert passport["investability_certified"] is False

Try notebooks/QuantLab_Research_Starter.ipynb for an opt-in notebook demonstration.
No market-data token is supplied in browser or notebook examples.

### Performance reproducibility

    python scripts/benchmark_research.py --assets 20,50,100 --periods 120

This measures observed local CPU runtime and Python peak allocations on
synthetic fixed-seed universes. It does not measure financial alpha or live
execution quality. Do not quote timings without hardware and version metadata.

## Skills mapped to index-research and quantitative-analytics job descriptions

This is a generic skills map. Replace it with a **specific employer's actual
JD** before claiming full alignment.

| Common hiring requirement | Verifiable QuantLab artifact | Important limitation |
| --- | --- | --- |
| Python research/data engineering | Reusable index_research package, FastAPI, local SDK, unit tests | Benchmark real workloads before scalability claims |
| Factor research and index design | Composite PIT-aware scores, constrained weighting, Index Studio | Real dates/member/fundamental vintages require independent evidence |
| Benchmark-relative quantitative risk | Tracking error optimizer, return-factor risk and active weights | Return-proxy factors are not Barra/MSCI licensed factor returns |
| Statistical testing | OOS splits, HAC/bootstrap, inference and scenario suites | Exploratory search cannot be called confirmatory without prereg |
| Corporate action and data quality | Original source checksums, evidence passport, blocked missing fields | No independent event completeness certification |
| Quantitative communication | Interactive explanations, charts, notebooks and methodology ZIP | A beautiful chart is not proof of empirical validity |
| Reproducibility | Replay command, run manifest, immutable archived outputs | Archived licensed data are not redistributed |
| Research judgment and model governance | Source blockers, hypothesis registration, chronology guards | Local SHA is not an external audit stamp |

## Résumé and interview presentation — evidence-first

A defensible project title is:

**QuantLab — Multi-Factor Equity Index Research & Explainability Platform**

Example project statement, valid only after reviewing the actual repository
and run evidence:

"Engineered a local-first Python/FastAPI and React research workstation for
cross-sectional factor scoring, constrained index construction, statistical
validation, source-level data provenance and saved-run reproducibility."

If the index-decision replay, active-risk prerequisites and CI acceptance
are verified, a more detailed explanation could mention:

"Added source-exact constituent attribution, provenance-gated benchmark-
relative factor-risk decomposition, archived hypothesis protocols and
downloadable methodology bundles; trained/holdout examples remain clearly
separated from independently validated historical market research."

Do not insert unobserved outperformance percentages, a made-up dataset
coverage percentage, invented speedups or proprietary methodology claims.

### Suggested three-minute recorded demonstration

- 0:00–0:25 — Research question and source readiness, including one blocker.
- 0:25–1:05 — Factor methodology, constraints and preflight.
- 1:05–1:45 — An actual archived constituent explanation with math and weights.
- 1:45–2:15 — Benchmark-relative attribution prerequisites or a genuine
  measured estimate when input files exist.
- 2:15–2:45 — Reproduction command and numerical comparison.
- 2:45–3:00 — Findings, limitations, and next required evidence.

Suggested interviewer questions: how you avoid lookahead in issuer factors;
how you reconstruct a reconstitution trade; how factor risk differs from
security-specific risk; how you distinguish a software test from an audited
market result; what happens if benchmark weights or delisted symbols are
missing; and what gets invalidated after a historical price correction.

## Case studies

- **A. Multi-factor index design:** docs/CASE_STUDY_NIFTY_MULTIFACTOR.md
- **B. Active risk and tracking error:** see source-required
  workstation_api/active_risk_lab.py and the math in docs/RESEARCH_METHODS.md
- **C. Research robustness/data integrity:** use Data Passports, source hashes,
  PIT evidence checks, sensitivity plots and the reproducibility checker.

The published NIFTY research protocol is *not* an independently validated
empirical paper. Work begins with acquiring original PIT member/fundamental
and appropriately adjusted historical returns, not inserting estimates in
place of those inputs.
