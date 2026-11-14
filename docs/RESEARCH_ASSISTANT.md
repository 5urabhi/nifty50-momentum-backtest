# Ask QuantLab — Source-grounded Research Assistant

QuantLab's **Results Studio → Ask QuantLab** is a read-only research explainer for a *selected, archived* model run or index experiment.

## What you can ask

Choose a saved result, open **Ask QuantLab**, then select one of the example questions or type a question up to 400 characters. Switch explanation depth between **Beginner**, **Researcher**, and **Mathematical**.

The assistant understands narrowly scoped requests about:

- **Saved measurements:** Sharpe, Sortino, CAGR, drawdown, volatility, tracking error, information ratio, beta, VaR, Expected Shortfall, and other source-supported research metrics.
- **Interpretation:** what a fitted model or index construction can and cannot establish.
- **Sources:** the archived dataset identity, observation count (when available), source classification, and original-source evidence blockers.
- **Validity:** why source auditing, point-in-time index membership, dividend adjustments, compatible TRI, statistically untouched tests, and realistic execution evidence matter.
- **Why a result happened:** the *configured* factor weights and saved descriptive statistics, without claiming that those parameters establish causal attribution.
- **Next tests:** an action grounded in recorded evidence blockers plus suitable chronological/benchmark research methods.
- **Comparison:** an explicit route to compare compatible saved runs; the assistant will not fabricate a second run or claim a model improved without paired evidence.

Each answer contains a human-readable explanation, **raw source-backed numeric facts with their declared units**, interpretation limitations, recommended actions, and clickable references to Results Studio **Diagnostics**, **Evidence audit**, **Sources & methods**, or **Compare runs**. Click a reference to inspect the exact saved evidence.

## Correct interpretation

This release is intentionally an **offline deterministic evidence assistant**, *not an LLM chat provider*. No OpenAI/third-party model or external inference service is called. It interprets common natural-language questions using an audited set of scientific definitions and the existing saved-run evidence calculation.

It **does not**:

- Generate missing prices, option quotes, financial statements, corporate actions, or statistical test results.
- Call Dhan, NSE, broker-order APIs, or other outside services.
- Fetch new history without explicit user confirmation through the existing Data Library / Model Laboratory workflow.
- Run backtests or rewrite stored configurations merely because a question requested a new result.
- Invent numerical metrics, return series, causal explanations, or unseen comparison results.
- Upgrade synthetic demonstrations into observed results or treat checksums as proof of source truth.
- Certify Sharpe, historical alpha, significance, point-in-time investability, or real fill quality.

If a saved model does not contain Sharpe or another requested metric, the assistant shows **no numeric value** and explains that the requested metric is unavailable. It will not substitute a different metric.

## Mathematical and numerical sources

The assistant reads existing Python functions:

- `workstation_api.result_evidence.summarize(kind, run_id)`: complete source-bound evidence for saved runs, computed risk statistics, explicit validation status and source checks. Index-run statistics use a saved matched return calendar; the test is not a prospective certification.
- `workstation_api.research_next.explain_saved(kind, run_id, level)`: archived model definitions, mathematical formulas, explicitly saved configuration and limitations.
- `workstation_api.research_assistant.answer`: interpretation only, based on those structures.

Endpoint: `POST /api/workspace/results/{model_run|research_run}/{run_id}/ask` with a small JSON body, for example:

```json
{"question": "Can I trust this result?", "level": "researcher"}
```

The request accepts 2–400 characters and a fixed explanation level. Responses are scoped to a single validated saved run ID and return **structured evidence citations**, not arbitrary external links.

Metric display follows the saved unit. Fractions explicitly identified as return/drawdown/ES/weight measurements are rendered as percentages; Sharpe and beta remain unitless; money gets a symbol only when its currency is supplied. Exported saved data preserve the original unmodified numeric values.

## Research integrity and reproducibility

A passing Python/React/Chromium CI run verifies software pathways on synthetic fixtures, **not** live Dhan rights or authentic NIFTY historical evidence. Compare runs on compatible dates, source versions, and benchmark conventions. The assistant cannot replace source access, independent replication or a predeclared untouched final test.

Questions and answers are kept in the browser component's memory for the currently selected run (up to eight turns). They are **not** saved as a retrievable conversation archive. Choose another run to switch contexts. Never enter brokerage credentials or secrets in a question.

## Local verification

```bash
python -m unittest discover -s tests -p 'test_research_assistant.py' -v
python -m unittest discover -s tests -v
npm run build
```

The `.github/workflows/workstation-browser-smoke.yml` workflow checks that a user can select a saved result, ask a question, read its evidence label, and navigate to the real saved evidence audit.
