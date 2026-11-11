"""Evidence- and reproducibility-gated evaluation for local research studies.

PASS here means deterministic SOFTWARE gates and declared data evidence,
not external audit, exchange certification, or a profitable trading strategy.
No automatic evidence 'approval' is inferred from files being present.
"""
from pathlib import Path
import hashlib
import json
import pandas as pd

REQUIRED_SOURCE_FILES = {
    "prices.csv","membership.csv","benchmark.csv","fundamentals.csv",
    "sectors.csv","corporate_actions.csv"
}
REQUIRED_DECLARATIONS = {
    "constituent_history_source","constituent_effective_dates_verified",
    "fundamental_publication_dates_verified","price_corporate_actions_verified",
    "benchmark_total_return_verified","delistings_and_recoveries_reviewed",
    "revisions_and_lookahead_reviewed","final_holdout_frozen_before_evaluation",
    "data_licensing_reviewed","independent_reviewer","review_date"
}


def evidence_gate(data_dir: str | Path, declaration_file: str | Path) -> dict:
    """Require explicit human review flags and primary evidence references.

    The declaration is self-asserted. There is no cryptographic exchange
    attestation, and this code never automatically sets verified flags.
    """
    directory=Path(data_dir)
    present={x for x in REQUIRED_SOURCE_FILES if (directory/x).is_file()}
    missing=sorted(REQUIRED_SOURCE_FILES-present)
    declaration=json.loads(Path(declaration_file).read_text()) if Path(declaration_file).exists() else {}
    absent=sorted(REQUIRED_DECLARATIONS-set(declaration))
    flags=[x for x in REQUIRED_DECLARATIONS if x.endswith("_verified")
           or x.endswith("_reviewed") or x.startswith("final_holdout_")]
    unchecked=sorted(x for x in flags if declaration.get(x) is not True)
    identity=all(isinstance(declaration.get(k),str) and declaration[k].strip()
                 for k in ["constituent_history_source","independent_reviewer","review_date"])
    status="DECLARED_EVIDENCE_COMPLETE_NEEDS_INDEPENDENT_AUDIT" if not missing and not absent and not unchecked and identity else "BLOCKED"
    hashes={}
    for p in sorted(present):
        hashes[p]=hashlib.sha256((directory/p).read_bytes()).hexdigest()
    return {"status":status,"missing_input_files":missing,
            "missing_declarations":absent,"unchecked_review_flags":unchecked,
            "reviewer_identity_present":identity,"input_sha256":hashes,
            "disclosure":"Flags are human-declared, not independently verified by Python. Never infer empirical validation solely from this output."}


def assess_holdout(results_dir: str | Path, data_dir: str | Path,
                   declaration_file: str | Path) -> dict:
    """Consolidate deterministic split outputs with explicit gate disclosure."""
    root=Path(results_dir)
    manifest=json.loads((root/"research_manifest.json").read_text())
    gate=evidence_gate(data_dir,declaration_file)
    metrics=manifest.get("metrics_by_split",{})
    final=metrics.get("final_test")
    checks={
        "final_test_exists":final is not None,
        "final_test_has_12_periods":bool(final and final.get("observations",0)>=12),
        "final_test_metrics_available":bool(final and
            all(final.get(name) is not None for name in (
                "strategy_cagr","benchmark_cagr","tracking_error"))),
        "data_evidence_declared":gate["status"]!="BLOCKED",
        "has_input_hashes":bool(manifest.get("input_sha256")),
        "price_vs_benchmark_convention_reviewed":gate["status"]!="BLOCKED",
    }
    status="REVIEW_READY_NOT_EXTERNALLY_AUDITED" if all(checks.values()) else "NOT_READY"
    return {
        "status":status,
        "checks":checks,"data_gate":gate,
        "final_test_descriptive_metrics":final,
        "limitations":manifest.get("limitations",[]),
        "warnings":[
            "Do not optimize parameters on final-test returns.",
            "Source provenance and declarations require an independent human reviewer.",
            "Security events, delisting recoveries, survivorship bias and costs are not proven correct by tests.",
            "This program does not claim to have executed a real historical empirical study.",
        ]
    }


def export_holdout_review(results_dir: str | Path,data_dir: str | Path,
                          declaration_file: str | Path) -> Path:
    report=assess_holdout(results_dir,data_dir,declaration_file)
    target=Path(results_dir)/"EMPIRICAL_RESEARCH_STATUS.json"
    target.write_text(json.dumps(report,indent=2,allow_nan=False))
    return target
