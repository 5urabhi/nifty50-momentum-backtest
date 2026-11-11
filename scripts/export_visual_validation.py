"""Generate an offline self-contained 2D/3D mathematical validation report.

This produces local HTML and machine-readable CSV/JSON evidence. No GitHub
execution, no network calls, no historic investment-performance claims.
"""
import argparse
import json
from datetime import datetime,timezone
from html import escape
from pathlib import Path
import numpy as np
import plotly.graph_objects as go
from plotly.io import to_html

from index_research.visual_validation import (
    option_price_surface,portfolio_risk_surface,option_convergence,
    identity_checks,gbm_moments,risk_contribution_test,
    validation_table,three_asset_covariance
)
from index_research.portfolio_theory import optimize_portfolio


def report(outdir: str | Path) -> Path:
    out=Path(outdir)
    out.mkdir(parents=True,exist_ok=True)
    convergence, c1=option_convergence()
    c2=identity_checks()
    gbm,c3=gbm_moments()
    contributions,c4=risk_contribution_test()
    checks=validation_table([*c1,*c2,*c3,*c4])
    checks.to_csv(out/"mathematical_checks.csv",index=False)
    convergence.to_csv(out/"option_convergence.csv",index=False)
    gbm.to_csv(out/"gbm_moments.csv",index=False)
    surface=option_price_surface()
    surface.to_csv(out/"option_surface.csv",index=False)
    risk=portfolio_risk_surface(three_asset_covariance())
    risk.to_csv(out/"portfolio_risk_surface.csv",index=False)
    contributions.to_csv(out/"risk_contributions.csv",index_label="asset")

    figs=[]
    f=go.Figure()
    for name,group in convergence.groupby("method",sort=False):
        f.add_trace(go.Scatter(x=group.budget,y=group.absolute_error,
            mode="lines+markers",name=name))
    f.update_layout(title="2D · Option pricing: numerical convergence",
        xaxis_title="Method-specific calculation budget",
        yaxis_title="Absolute pricing error")
    figs.append(f)

    fixed=surface.pivot(index="volatility",columns="strike",values="price")
    f=go.Figure(go.Surface(x=fixed.columns.to_numpy(),y=fixed.index.to_numpy(),
                            z=fixed.to_numpy(),colorscale="Viridis"))
    f.update_layout(title="3D · European call-price surface",
        scene=dict(xaxis_title="Strike",yaxis_title="Volatility",zaxis_title="Price"))
    figs.append(f)

    cov=three_asset_covariance()
    opt=optimize_portfolio(cov)
    f=go.Figure(go.Scatter3d(x=risk.weight_1,y=risk.weight_2,
        z=risk.annual_volatility,mode="markers",
        marker=dict(size=3,color=risk.annual_volatility,colorscale="Viridis",showscale=True),
        name="Feasible long-only weights"))
    f.add_trace(go.Scatter3d(x=[opt.weights.iloc[0]],y=[opt.weights.iloc[1]],
          z=[opt.volatility],mode="markers",name="Minimum variance",
          marker=dict(size=8,color="#ffda70",symbol="diamond")))
    f.update_layout(title="3D · Portfolio risk landscape",
        scene=dict(xaxis_title="Asset A weight",yaxis_title="Asset B weight",
                   zaxis_title="Annualized volatility"))
    figs.append(f)

    f=go.Figure()
    f.add_trace(go.Scatter(x=gbm.year,y=gbm.p95,line=dict(width=0),showlegend=False))
    f.add_trace(go.Scatter(x=gbm.year,y=gbm.p05,
        line=dict(width=0),fill="tonexty",name="5th–95th percentiles"))
    f.add_trace(go.Scatter(x=gbm.year,y=gbm.analytical_mean,
        mode="lines",name="Analytical expected value"))
    f.add_trace(go.Scatter(x=gbm.year,y=gbm.simulated_mean,
        mode="lines",name="Simulated average",line=dict(dash="dash")))
    f.update_layout(title="2D · GBM mathematical moments",
        xaxis_title="Elapsed years",yaxis_title="Theoretical asset price")
    figs.append(f)

    f=go.Figure(go.Bar(x=contributions.index,
                       y=contributions.volatility_contribution))
    f.update_layout(title="2D · Euler volatility risk decomposition",
                    xaxis_title="Illustrative asset",yaxis_title="Volatility contribution")
    figs.append(f)

    allpass=bool((checks["Status"]=="PASS").all())
    results={"generated_utc":datetime.now(timezone.utc).isoformat(),
        "dataset":"DETERMINISTIC MATHEMATICAL TEST FIXTURES - NOT MARKET PERFORMANCE",
        "total_checks":len(checks),"passed":int((checks["Status"]=="PASS").sum()),
        "failed":int((checks["Status"]=="FAIL").sum()),
        "note":"Reports calculated tolerances only. Empirical financial validity is not asserted."}
    (out/"visual_validation_manifest.json").write_text(json.dumps(results,indent=2))
    chunks=[]
    for i,fig in enumerate(figs):
        fig.update_layout(template="plotly_dark",paper_bgcolor="#0b1424",
                          plot_bgcolor="#16263b",font=dict(color="#f0f5fc"),
                          height=520,margin=dict(l=15,r=15,t=60,b=15))
        chunks.append(to_html(fig,full_html=False,include_plotlyjs=True if i==0 else False))
    rows="".join(
        "<tr>"+ "".join("<td>"+escape(str(v))+"</td>" for v in line)+"</tr>"
        for line in checks.round(8).itertuples(index=False,name=None))
    page=f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Mathematical Visual Validation Report</title>
<style>body{{font-family:system-ui;background:#081326;color:#eaf2fd;margin:0;line-height:1.5}}
main{{max-width:1150px;margin:auto;padding:36px 24px}}h1{{font-size:38px;letter-spacing:-.04em}}
p{{color:#b8cbdb}}.warn{{background:#302616;border-left:4px solid #fac77a;padding:16px}}
.card{{background:#12233a;border:1px solid #2a4160;border-radius:14px;padding:18px;margin:20px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #2e4662;text-align:left;font-size:13px}}
th{{color:#a8d6ef}}a{{color:#89d9ed}}small{{color:#8da6bb}}</style></head>
<body><main><h1>Mathematical Model Verification</h1>
<p>Deterministic numerical evidence and interactive two- and three-dimensional charts.</p>
<div class="warn"><strong>Not historical investment evidence.</strong> These plots
validate mathematical identities, example covariances and simulated price models.
They do not verify an index backtest, market data, execution or returns.</div>
<div class="card"><h2>Numerical assertions</h2>
<p>{results["passed"]} / {results["total_checks"]} checks within stated tolerances;
{results["failed"]} outside tolerance.</p><table><thead><tr>
<th>Test</th><th>Observed</th><th>Reference</th><th>Tolerance</th><th>Error</th><th>Result</th><th>Interpretation</th>
</tr></thead><tbody>{rows}</tbody></table></div>
{''.join('<section class="card">'+fragment+'</section>' for fragment in chunks)}
<footer><small>Generated: {escape(results["generated_utc"])} · Local-only independent research</small></footer>
</main></body></html>"""
    output=out/"visual_validation_report.html"
    output.write_text(page,encoding="utf-8")
    return output


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",default="results/visual_validation")
    args=p.parse_args()
    print(report(args.output_dir))
    print("Local output only. Mathematical fixtures are not empirical market data.")


if __name__=="__main__":
    main()
