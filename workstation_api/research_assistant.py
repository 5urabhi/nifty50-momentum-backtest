"""Local, source-grounded questions about archived QuantLab research results.

No network requests, LLM calls, order endpoints, data mutation, or new model
calculations. Every numeric fact is read from a saved run's evidence audit.
If the archive does not contain an answer, say so instead of estimating it.
"""
from __future__ import annotations

import math
import re
from typing import Literal

from . import research_next, result_evidence

Kind = Literal["model_run", "research_run"]
Level = Literal["beginner", "researcher", "mathematical"]

METRIC_DEFINITIONS = {
    "sharpe": (
        "Sharpe ratio", "Annualized average excess return divided by annualized "
        "standard deviation of excess return.",
        "A zero-rate Sharpe assumes risk-free return = 0. In-sample or synthetic "
        "Sharpe is not evidence of investable alpha.", ("sharpe",)),
    "sortino": (
        "Sortino ratio", "Annualized average excess return relative to a chosen "
        "threshold, divided by downside deviation.",
        "Its value depends on the threshold, calculation convention and number "
        "of downside observations.", ("sortino",)),
    "cagr": (
        "Compound annual growth rate", "Geometrically compounded annual growth "
        "over the saved sequence; a fraction of 0.10 is 10% per year.",
        "Requires a meaningful sample and correctly adjusted, economically "
        "comparable returns.", ("cagr",)),
    "drawdown": (
        "Maximum drawdown", "Largest recorded peak-to-trough decline in the "
        "wealth index, expressed as a fraction or percentage.",
        "Observed drawdown is not a bound on future downside.", ("drawdown",)),
    "volatility": (
        "Volatility", "Annualized standard deviation of periodic returns.",
        "Square-root-of-time annualization assumes a sufficiently stable sampling "
        "process; clustered volatility weakens the approximation.", ("volatility",)),
    "tracking": (
        "Tracking error", "Annualized dispersion of strategy returns minus "
        "benchmark returns on an aligned calendar.",
        "A price-index benchmark cannot be substituted for TRI in a "
        "total-return comparison.", ("tracking error",)),
    "information": (
        "Information ratio", "Annualized arithmetic average active return "
        "divided by annualized tracking error.",
        "Requires a compatible benchmark, costs, and an honestly isolated test.",
        ("information ratio",)),
    "beta": (
        "Beta versus benchmark", "Sample covariance of strategy and benchmark "
        "returns divided by benchmark variance.",
        "Beta is an estimated historical association, not a causal exposure.",
        ("beta",)),
    "var": (
        "Historical value at risk", "Loss quantile at the declared confidence "
        "level and observation horizon.",
        "95% VaR does not cap the worst 5% of possible losses.", ("var",)),
    "es": (
        "Expected shortfall", "Mean observed loss in the tail at or beyond "
        "the specified VaR threshold.",
        "Unstable when only a small number of tail observations are available.",
        ("expected shortfall", "tail loss", "cvar")),
    "return": (
        "Observed strategy and benchmark returns", "Strategy net returns "
        "and benchmark returns must be compared on the same dates and convention.",
        "Descriptive backtested returns are not independently audited alpha.",
        ("cagr", "return")),
    "risk": (
        "Saved risk measures", "Historical volatility, drawdown, tracking error "
        "and tail estimates describe the archived sample.",
        "No risk measure guarantees future outcomes.",
        ("volatility", "drawdown", "tracking error", "var", "shortfall")),
}

EVIDENCE_LABELS = {
    "synthetic_demo": "Synthetic demonstration — no observed-market performance claim",
    "theoretical": "Theoretical mathematics — outputs are conditional on assumptions",
    "observed_unverified": "Observed input — original-source truth not independently audited",
    "unknown": "Source classification incomplete — do not presume market evidence",
}


def _intent(question: str) -> tuple[str, str]:
    q = re.sub(r"\s+", " ", question.casefold()).strip()
    if re.search(r"\b(why|cause|driver|driven|attribution)\b", q) and re.search(
            r"\b(performance|perform|profit|loss|outperform|underperform|better|"
            r"worse|changed|increase|decrease|factors?|alpha)\b", q):
        return "drivers", ""
    matchers = (
        ("sharpe", r"\bsharpe\b"), ("sortino", r"\bsortino\b"),
        ("cagr", r"\bcagr\b|\bcompound growth\b"),
        ("drawdown", r"\bdrawdown\b"), ("tracking", r"\btracking error\b"),
        ("information", r"\binformation ratio\b"), ("beta", r"\bbeta\b"),
        ("es", r"\bexpected shortfall\b|\bcvar\b|\btail loss\b"),
        ("var", r"\bvar\b|\bvalue at risk\b"),
        ("volatility", r"\bvolatility\b|\bstd(?:\.|andard deviation)?\b"),
    )
    for key, pattern in matchers:
        if re.search(pattern, q):
            return "metric", key
    if re.search(r"\b(compare|comparison|versus|vs\.?|baseline|different run)\b", q):
        return "compare", ""
    if re.search(r"\b(data|missing|source|coverage|history|download|complete|"
                 r"provenance|checksum|inputs?)\b", q):
        return "data", ""
    if re.search(r"\b(next|improv|suggest|recommend|research plan|"
                 r"experiment|test next|try next)\b", q):
        return "next", ""
    if re.search(r"\b(trust|valid|verified|certif|significan|"
                 r"reliable|bias|overfit|safe|confidence|evidence|good result)\b", q):
        return "trust", ""
    if re.search(r"\b(assumption|formula|equation|math|method|"
                 r"how is|how does|calculate)\b", q):
        return "method", ""
    if re.search(r"\b(return|performance|profit|gain|risk)\b", q):
        return "metric", "risk" if "risk" in q else "return"
    if re.search(r"\b(what|explain|summary|overview|result|"
                 r"model|show|understand|tell)\b", q):
        return "overview", ""
    return "unsupported", ""


def _facts(report: dict, keywords: tuple[str, ...], limit: int = 5) -> list[dict]:
    result = []
    for metric in report.get("metrics") or []:
        name = str(metric.get("name") or "")
        if not any(keyword in name.casefold() for keyword in keywords):
            continue
        value = metric.get("value")
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            continue
        result.append({"name": name, "value": value, "unit": str(metric.get("unit") or ""),
                       "detail": str(metric.get("detail") or ""),
                       "source": "saved_evidence.metrics"})
        if len(result) >= limit:
            break
    return result


def _references(kind: Kind, run_id: str, *, metrics: bool = False,
                evidence: bool = False, source: bool = False, method: bool = False,
                comparison: bool = False) -> list[dict]:
    refs = []
    if metrics:
        refs.append({"title": "Archived numerical measurements", "tab": "diagnostics",
                     "locator": f"{kind}/{run_id}: saved_evidence.metrics"})
    if evidence:
        refs.append({"title": "Exact validation checks and statistical evidence",
                     "tab": "validation",
                     "locator": f"{kind}/{run_id}: saved_evidence.checks"})
    if source:
        refs.append({"title": "Source type, hashes, and saved configuration",
                     "tab": "evidence",
                     "locator": f"{kind}/{run_id}: saved_evidence.source"})
    if method:
        refs.append({"title": "Recorded model assumptions and methods", "tab": "evidence",
                     "locator": f"{kind}/{run_id}: archived_explanation"})
    if comparison:
        refs.append({"title": "Compare archived runs on compatible inputs", "tab": "compare",
                     "locator": f"{kind}/{run_id}: run_comparison"})
    return refs


def answer(kind: Kind, run_id: str, question: str,
           level: Level = "beginner") -> dict:
    """Answer from the selected immutable run, never invent missing measurements."""
    if kind not in ("model_run", "research_run"):
        raise ValueError("Select a saved model_run or research_run")
    if level not in ("beginner", "researcher", "mathematical"):
        raise ValueError("Choose beginner, researcher, or mathematical explanation")
    query = question.strip()
    if not 2 <= len(query) <= 400 or not any(ch.isalnum() for ch in query):
        raise ValueError("Ask a question of 2–400 characters about the saved run")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,90}", run_id):
        raise ValueError("Invalid saved run identifier")
    # These existing read-only endpoints are the only source of reported facts.
    report = result_evidence.summarize(kind, run_id)
    explanation = research_next.explain_saved(kind, run_id, level)
    classification = str(report.get("evidence_class") or "unknown")
    classification_label = EVIDENCE_LABELS.get(classification,
                                                EVIDENCE_LABELS["unknown"])
    intent, key = _intent(query)
    facts = []
    steps = []
    limits = []
    title = "Saved research interpretation"
    message = ""
    refs = _references(kind, run_id, evidence=True, source=True)
    blocked = [item for item in report.get("checks") or []
               if item.get("status") in {"blocked", "warning"}]
    checks = blocked[:4]
    first_issue = next((c for c in blocked
                        if c.get("next_action") and "publication" not in
                        str(c.get("name", "")).casefold()), None)

    if intent == "metric":
        title, definition, caution, keys = METRIC_DEFINITIONS[key]
        facts = _facts(report, keys)
        message = definition
        if not facts:
            message += (" This archived run has no matching numeric metric; "
                        "QuantLab will not calculate or invent a value from an unrelated model.")
        limits.append(caution)
        refs = _references(kind, run_id, metrics=True, evidence=True)
        steps.append("Inspect the exact metric table and sampling assumptions.")
    elif intent == "overview":
        title = "What this run establishes"
        message = str(explanation.get("explanation") or
                      "This is an archived computation; interpret its source classification.")
        facts = _facts(report, ("cagr", "sharpe", "volatility", "drawdown"), 4)
        if report.get("observations") is not None:
            facts.insert(0, {"name": "Saved eligible observations",
                             "value": report["observations"], "unit": "count",
                             "detail": "Count reported by the evidence audit",
                             "source": "saved_evidence.observations"})
        limits.append(str(explanation.get("warning") or "Saved calculations are not proof of alpha."))
        refs = _references(kind, run_id, metrics=True, evidence=True, method=True)
    elif intent == "trust":
        title = "Can this result be trusted?"
        message = ("The Python result is inspectable, but it is classified as "
                   + classification_label + ". Independent empirical certification "
                   "is not established. Validation must be judged separately from "
                   "whether the code ran.")
        if checks:
            message += " The current audit flags: " + "; ".join(
                f"{c['name']} ({c['status']})" for c in checks[:3]) + "."
        if report.get("uncertainty") is None:
            limits.append("No saved block-bootstrap confidence interval exists for this run.")
        else:
            limits.append("Exploratory confidence intervals do not fix data snooping or source errors.")
        steps.append(str(first_issue.get("next_action")) if first_issue else
                     "Review all source and final-test evidence before publication.")
        refs = _references(kind, run_id, evidence=True, source=True)
    elif intent == "drivers":
        title = "What may explain the result?"
        message = ("A saved association or factor setting does not identify a causal "
                   "driver of return changes. This archive cannot establish why a "
                   "price moved or whether any performance difference was skill.")
        config = explanation.get("parameters") or {}
        if kind == "research_run" and isinstance(config, dict):
            weights = config.get("factor_weights") or {}
            for name, value in list(weights.items())[:6] if isinstance(weights, dict) else []:
                if isinstance(value, (int, float)) and math.isfinite(float(value)):
                    facts.append({"name": "Configured " + str(name) + " factor weight",
                                  "value": value, "unit": "fraction",
                                  "detail": "Input setting, NOT observed factor attribution",
                                  "source": "archived_explanation.parameters.factor_weights"})
        facts.extend(_facts(report, ("cagr", "information ratio"), 3))
        steps.append("Open factor diagnostics or a matched-calendar baseline comparison.")
        limits.append("Causal attribution requires a separately specified identification design.")
        refs = _references(kind, run_id, metrics=True, evidence=True, method=True,
                           comparison=True)
    elif intent == "data":
        title = "What data does this result actually use?"
        src = report.get("source") or {}
        dataset_id = src.get("dataset_id") or "not recorded"
        message = (f"The saved source is {classification_label}. Dataset ID: {dataset_id}. "
                   "This answer refers to the archived run, not live brokerage coverage. "
                   "A source checksum identifies archived bytes, not data correctness.")
        if src.get("frequency"):
            message += " Reported observation frequency: " + str(src["frequency"]) + "."
        for check in checks[:3]:
            steps.append(str(check.get("next_action") or check.get("detail")))
        if classification == "synthetic_demo":
            steps.insert(0, "Use observed licensed market data before interpreting returns as historical.")
        if not steps:
            steps.append("Inspect the Data Library and original-source evidence passport.")
        refs = _references(kind, run_id, source=True, evidence=True)
    elif intent == "method":
        title = "How the saved calculation works"
        message = str(explanation.get("explanation") or "No archived methodology is available.")
        formula = explanation.get("formula")
        if level == "mathematical" and formula:
            message += " Governing relation: " + str(formula)
        assumptions = explanation.get("assumptions") or []
        if isinstance(assumptions, list):
            limits.extend(str(x) for x in assumptions[:2])
        limitations = explanation.get("limitations") or []
        if isinstance(limitations, list):
            limits.extend(str(x) for x in limitations[:2])
        refs = _references(kind, run_id, method=True, source=True)
    elif intent == "compare":
        title = "How to compare this run fairly"
        message = ("A second run has not been selected. A defensible comparison needs "
                   "compatible source files and hashes, evaluation dates, return "
                   "conventions, and a declared benchmark. The Compare runs view "
                   "checks compatibility rather than overlaying unrelated values.")
        steps.append("Select 2–8 saved runs in Compare runs; use paired evidence only for compatible index returns.")
        refs = _references(kind, run_id, comparison=True, evidence=True)
    elif intent == "next":
        title = "Next defensible research step"
        message = ("Keep the source and model decisions explicit. "
                   "The next test should address an actual limitation of this saved result.")
        if first_issue:
            steps.append(str(first_issue.get("next_action") or first_issue.get("detail")))
        if classification == "synthetic_demo":
            steps.append("Switch to an observed dataset before making any historical claim.")
        if kind == "research_run":
            steps.append("Freeze one untouched chronological test and compare against a matched, net-of-cost benchmark.")
        else:
            steps.append("Check holdout diagnostics against a simple baseline, not only fitted charts.")
        refs = _references(kind, run_id, evidence=True, source=True, method=True)
    else:
        title = "What I can answer from a saved result"
        message = ("I can explain exact saved metrics, methodology, source requirements, "
                   "evidence limits, model drivers, fair comparisons, and valid next tests. "
                   "Your question is outside these source-grounded topics, so I cannot "
                   "construct a speculative answer.")
        steps.append("Try: Can I trust this result? What is its Sharpe ratio? What should I test next?")
        refs = _references(kind, run_id, evidence=True, source=True)

    if not limits and intent != "unsupported":
        limits.append("This is not independent source verification or a trading recommendation.")
    limits = [x for x in limits if x][:4]
    return {
        "kind": kind, "run_id": run_id, "question": query, "intent": intent,
        "title": title, "answer": message, "evidence_class": classification,
        "evidence_label": classification_label, "facts": facts[:6],
        "references": refs[:6], "next_actions": [s for s in steps if s][:3],
        "limitations": limits, "engine": "offline_deterministic_saved_evidence",
        "warning": "No external LLM, broker order, vendor fetch or empirical certification.",
    }
