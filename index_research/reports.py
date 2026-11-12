"""Offline HTML research report. Does not require browser/server or network."""
from pathlib import Path
from html import escape
import json
import pandas as pd

def _fmt(value):
    if isinstance(value,float):
        return "n/a" if not (value==value) else f"{value:.5f}"
    return escape(str(value))

def build_html_report(output_dir: str | Path) -> Path:
    root=Path(output_dir)
    meta=json.loads((root/"research_manifest.json").read_text())
    rows=pd.read_csv(root/"monthly_results.csv",parse_dates=["date"])
    if len(rows):
        growth=(1+rows["strategy_net"]).cumprod()
        benchmark=(1+rows["benchmark"]).cumprod()
        preview=pd.DataFrame({"date":rows["date"].dt.strftime("%Y-%m-%d"),
                              "strategy_nav":growth.round(4),
                              "benchmark_nav":benchmark.round(4)})
    else:
        preview=pd.DataFrame()
    splits=meta["metrics_by_split"]
    body="".join(
        f"<h3>{escape(name)}</h3><table><tbody>"+ "".join(
            f"<tr><th>{escape(key)}</th><td>{_fmt(value)}</td></tr>"
            for key,value in values.items()
        )+"</tbody></table>"
        for name,values in splits.items()
    )
    provenance="".join(f"<li>{escape(k)}: {escape(v)}</li>"
                       for k,v in meta.get("input_sha256",{}).items())
    html=f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Equity Index Research Report</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:32px auto;color:#17212f;background:#f8fafc;line-height:1.5;padding:0 20px}}
h1,h2{{color:#17355d}}.card{{background:white;border:1px solid #e2e8f0;padding:22px;border-radius:12px;margin:16px 0}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #eee;text-align:left;padding:8px}}.warning{{background:#fff4db;border-left:4px solid #d49d28;padding:16px}}
small{{color:#555}}</style></head><body>
<h1>Equity Factor Index Research — Experiment Report</h1>
<div class="warning"><strong>Research-only output, not audited or an official index.</strong>
Dataset status: {escape(meta["config"]["dataset_status"])}.
No reported historical return is independently verified. Do not use this report as marketing performance evidence.</div>
<div class="card"><h2>Objective &amp; methodology</h2>
<p>Evaluate a transparent cross-sectional factor ranking and index weighting rule relative to a supplied benchmark, including holding-period alignment, approximate transaction costs, and time-segmented outcomes.</p>
<pre>{escape(json.dumps(meta["config"],indent=2))}</pre></div>
<div class="card"><h2>Quantitative results</h2>{body}</div>
<div class="card"><h2>Monthly index level (first rows)</h2>{preview.head(16).to_html(index=False,escape=True) if len(preview) else "No periods"}</div>
<div class="card"><h2>Data evidence and integrity</h2><p>SHA-256 input checksums:</p><ul>{provenance}</ul></div>
<div class="card"><h2>Limitations and next validation</h2><ul>{''.join('<li>'+escape(s)+'</li>' for s in meta["limitations"])}</ul>
<p>All findings are conditional on the historical dataset and factor definitions. See docs/RESEARCH_PROTOCOL.md for research release gates.</p></div>
<small>Generated UTC: {escape(meta["generated_utc"])}</small></body></html>"""
    target=root/"research_report.html"
    target.write_text(html,encoding="utf-8")
    return target
