"""Local quantitative-mathematics acceptance harness.

Run:
    python scripts/verify_mathematics.py --output-dir results/math_acceptance

No GitHub Actions. Exit nonzero if a numerical test fails.
The JSON/HTML report is reproducible, but passing numerical identities
does NOT establish real-market calibration, point-in-time inputs or alpha.
"""
import argparse
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import subprocess
import sys

SUITES = (
    "test_math_acceptance.py",
    "test_additional_mathematics.py",
    "test_model_validation.py",
    "test_visual_validation.py",
)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",default="results/math_acceptance")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=Path(args.output_dir).resolve()
    output.mkdir(parents=True,exist_ok=True)
    results=[]
    for name in SUITES:
        command=[sys.executable,"-m","unittest","discover","-s","tests",
                 "-p",name,"-v"]
        run=subprocess.run(command,cwd=root,stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT,text=True,check=False)
        results.append({"test_file":name,"passed":run.returncode==0,
                        "exit_code":run.returncode,"command":" ".join(command),
                        "output":run.stdout[-250000:]})
        (output/(name+".log")).write_text(run.stdout,encoding="utf-8")
    total=len(results)
    passed=sum(row["passed"] for row in results)
    report={
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "overall_status":"PASS" if total==passed else "FAIL",
        "completed_suites":passed,"total_suites":total,
        "suites":results,
        "scope":"Deterministic mathematical and software checks only",
        "not_verified":[
            "Actual historical data provenance or complete corporate actions",
            "Point-in-time fundamentals or index constituents",
            "Out-of-sample investment performance",
            "Economic assumptions or market calibration",
            "Streamlit visual rendering or hosted deployment",
        ],
    }
    (output/"mathematics_acceptance.json").write_text(
        json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    cards=[]
    for item in results:
        name=escape(item["test_file"])
        state="PASS" if item["passed"] else "FAIL"
        cards.append(f'<section><h2>{name} — {state}</h2>'
                     f'<pre>{escape(item["output"])}</pre></section>')
    html=f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Quantitative Mathematics Acceptance</title>
<style>body{{background:#091424;color:#eff5fe;font:15px system-ui;margin:auto;max-width:1050px;padding:32px}}
h1{{font-size:36px}}section{{padding:22px;border:1px solid #34516b;background:#13253e;
margin:18px 0;border-radius:12px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}
p{{color:#bbcee0}}.warn{{background:#3a2918;padding:16px;border-left:4px solid #f1be70}}</style>
</head><body><h1>Mathematics Acceptance</h1>
<p>Test suites passed: {passed}/{total} · Status: {report["overall_status"]}</p>
<p class="warn">Analytical and deterministic mathematical checks only.
PASS does not mean historical investment research or external data are validated.</p>
{''.join(cards)}</body></html>"""
    (output/"mathematics_acceptance.html").write_text(html,encoding="utf-8")
    print(f"Mathematics acceptance: {passed}/{total} suites passed")
    print("Evidence:",output/"mathematics_acceptance.html")
    return 0 if passed==total else 1


if __name__=="__main__":
    sys.exit(main())
