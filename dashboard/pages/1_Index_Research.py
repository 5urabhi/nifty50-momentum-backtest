"""Streamlit page: transparent index research, reproducible output and diagnostics."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
# Ensure project packages resolve when Streamlit runs a page by file path.
import sys
from pathlib import Path as _ProjectPath
_PROJECT_ROOT = str(_ProjectPath(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dashboard.workstation_nav import show_workflow_nav

from index_research.data import load_research_inputs
from index_research.experiment import ExperimentConfig, run_experiment, save_experiment
from index_research.reports import build_html_report
from index_research.pdf_report import generate_pdf_report
from index_research.fixtures import make_fixture
from index_research.sector_data import read_sector_history, asof_sectors, sector_exposure, concentration_metrics
from index_research.research_analytics import rolling_relative_metrics, cost_sensitivity
from index_research.comparison import compare_index_methods
from index_research.data_audit import audit_dataset
from index_research.robustness import sensitivity_grid, parameter_dispersion
from index_research.diagnostics import evaluate_factor_panel, exposure_panel, data_quality_report
from index_research.data_audit import audit_dataset
from index_research.robustness import sensitivity_grid

st.set_page_config(page_title="Index Construction Research",layout="wide")
show_workflow_nav()
st.title("Equity Factor Index Construction")
st.caption("Custom index research · Point-in-time evidence gates · Offline/local-first")

st.page_link("pages/12_Dhan_Data_Setup.py",label="Get historical Dhan data →",icon="📊")
st.page_link("pages/13_Empirical_Readiness.py",label="Verify source evidence →",icon="🧾")
st.info("The repository's historic optimized results are not independently audited. "
        "This page does not claim to reproduce official Nifty or MSCI indexes.")

with st.sidebar:
    st.header("Research configuration")
    demo=st.toggle("Use deterministic SYNTHETIC example",value=False)
    upload=None
    local_dir=None
    source_mode="Synthetic" if demo else "Upload ZIP"
    if not demo:
        source_mode=st.radio("Dataset source",["Local prepared folder","Upload ZIP"],
            horizontal=False,key="research_data_mode")
        if source_mode=="Upload ZIP":
            upload=st.file_uploader("Upload research data ZIP",type="zip",
                help="ZIP containing prices.csv, membership.csv, benchmark.csv, optionally fundamentals.csv")
        else:
            # Search only known local data roots; never arbitrary user-supplied filesystem paths.
            roots=[Path("data/research_v1"),Path("data/dhan/monthly_research")]
            folders=[]
            for root in roots:
                if root.is_dir() and (root/"prices.csv").exists():
                    folders.append(root)
                if root.is_dir():
                    folders.extend(sorted(p.parent for p in root.glob("*/prices.csv")))
            seen={str(p.resolve()):p for p in folders}
            folders=list(seen.values())
            preferred=st.session_state.get("research_input_dir")
            idx=next((i for i,p in enumerate(folders) if str(p.resolve())==str(Path(preferred).resolve())),0) if preferred else 0
            if folders:
                local_dir=st.selectbox("Prepared research folder",folders,index=idx,
                    format_func=lambda p:str(p))
                st.session_state["research_input_dir"]=str(local_dir.resolve())
                missing=[name for name in ("prices.csv","membership.csv","benchmark.csv")
                         if not (local_dir/name).is_file()]
                if missing:
                    st.warning("Dataset is NOT ready for index research. Missing: "+", ".join(missing)+
                               ". Dhan only creates prices.csv; add independently verified benchmark and membership.")
                else:
                    st.success("Required file names present. Provenance still requires independent review.")
            else:
                st.info("No local dataset with prices.csv found. Start in Dhan Historical Data or upload a ZIP.")
    top_n=st.number_input("Target constituents",min_value=2,max_value=500,value=10)
    method=st.selectbox("Weighting method",["equal","score","inverse_volatility","minimum_variance","risk_parity"])
    cap=st.slider("Maximum stock weight",0.05,1.0,0.20,step=0.01)
    sector_limit=st.toggle("Enable historical sector cap (requires sectors.csv)",False)
    max_sector=st.slider("Maximum sector allocation",0.10,1.0,0.40,step=0.05,disabled=not sector_limit)
    rebalance=st.selectbox("Reconstitution / rebalancing (months)",[1,3,6,12],index=1)
    cost=st.number_input("Cost per unit turnover (bps)",0.0,500.0,10.0,5.0)
    lag=st.selectbox("Execution timing",["1 month delayed (conservative)","Same-close idealization"],index=0)
    st.markdown("**Factor allocation (relative weights)**")
    mom=st.slider("Momentum",0.0,1.0,1.0,0.1)
    low=st.slider("Low volatility",0.0,1.0,0.0,0.1)
    val=st.slider("Value",0.0,1.0,0.0,0.1)
    quality=st.slider("Quality",0.0,1.0,0.0,0.1)
    size=st.slider("Size",0.0,1.0,0.0,0.1)
    development_end=st.text_input("Validation start (YYYY-MM-DD, optional)",value="")
    final_start=st.text_input("Final test start (YYYY-MM-DD, optional)",value="")
    go=st.button("Run research experiment",type="primary",use_container_width=True)

factor_weights={k:v for k,v in {
    "momentum":mom,"low_volatility":low,"value":val,"quality":quality,"size":size
}.items() if v>0}

def safe_zip_extract(blob: bytes, folder: Path) -> None:
    required={"prices.csv","membership.csv","benchmark.csv"}
    allowed=required|{"fundamentals.csv","sectors.csv","corporate_actions.csv"}
    if len(blob)>25*1024*1024:
        raise ValueError("ZIP upload exceeds 25 MB size limit")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=z.infolist()
        if len(members)>10 or any(m.file_size>40*1024*1024 for m in members):
            raise ValueError("ZIP has too many or oversized files")
        observed=set()
        for member in members:
            name=member.filename
            if name not in allowed:
                raise ValueError(f"Unexpected filename: {name}. ZIP must use flat CSV filenames.")
            if name in observed:
                raise ValueError("Duplicate file names")
            observed.add(name)
            (folder/name).write_bytes(z.read(member))
        if not required.issubset(observed):
            raise ValueError("Missing one or more required CSVs")

if go:
    try:
        if not factor_weights:
            raise ValueError("Choose at least one factor.")
        if not demo and source_mode=="Upload ZIP" and upload is None:
            raise ValueError("Upload historical inputs or select a prepared local dataset.")
        if not demo and source_mode=="Local prepared folder" and local_dir is None:
            raise ValueError("No local research dataset selected.")
        if top_n*cap<1:
            raise ValueError("Constituent count × max stock weight must be >= 1.")
        config=ExperimentConfig(
            name="synthetic_factor_demonstration" if demo else "user_supplied_index_research",
            factor_weights=factor_weights,top_n=int(top_n),
            weighting=method,max_weight=float(cap),
            rebalance_every=int(rebalance),cost_bps=float(cost),
            execution_lag=1 if lag.startswith("1 month") else 0,
            validation_start=development_end or None,
            final_test_start=final_start or None,
            dataset_status="static_universe_demo" if demo else "unverified",
            benchmark_name="synthetic_market" if demo else "user_supplied",
            source_note="SYNTHETIC — do not cite" if demo else "User data: provenance NOT independently verified",
            sector_cap=max_sector if sector_limit else None)
        with tempfile.TemporaryDirectory(prefix="index_research_") as temporary:
            root=Path(temporary)
            input_dir=root/"inputs"
            input_dir.mkdir()
            if demo:
                make_fixture(input_dir)
            elif source_mode=="Upload ZIP":
                safe_zip_extract(upload.getvalue(),input_dir)
            else:
                required=["prices.csv","membership.csv","benchmark.csv"]
                optional=["fundamentals.csv","sectors.csv","corporate_actions.csv"]
                missing=[name for name in required if not (local_dir/name).is_file()]
                if missing:
                    raise ValueError("Research dataset missing "+", ".join(missing)+
                        ". Dhan close prices alone are insufficient; do not infer benchmark/membership.")
                import shutil
                for name in required+optional:
                    source=local_dir/name
                    if source.is_file():
                        shutil.copyfile(source,input_dir/name)
            audit=audit_dataset(input_dir)
            prices, membership, benchmark, fundamentals=load_research_inputs(input_dir)
            sector_file=input_dir/"sectors.csv"
            sectors=asof_sectors(read_sector_history(str(sector_file)),prices.index,prices.columns) if sector_file.exists() else None
            if config.sector_cap is not None and sectors is None:
                raise ValueError("Historical sector cap requires sectors.csv")
            result,scores,metadata=run_experiment(prices,membership,benchmark,fundamentals,config,sectors=sectors)
            output=root/"output"
            output.mkdir(parents=True,exist_ok=True)
            factor_ic,factor_score_panels=evaluate_factor_panel(
                prices,membership,fundamentals,
                momentum_formation=config.momentum_formation,
                momentum_skip=config.momentum_skip,
                volatility_lookback=config.volatility_lookback)
            factor_portfolio_exposures,_=exposure_panel(result.weights,factor_score_panels,sectors)
            quality=data_quality_report(prices,membership,fundamentals,sectors)
            audit=audit_dataset(input_dir)
            (output/"dataset_audit.json").write_text(json.dumps(audit,indent=2,allow_nan=False))
            factor_ic.to_csv(output/"factor_rank_ic.csv",index_label="date")
            factor_portfolio_exposures.to_csv(output/"portfolio_factor_exposures.csv",index_label="date")
            (output/"data_quality.json").write_text(json.dumps(quality,indent=2,allow_nan=False))
            robustness_warning=None
            try:
                grid=sensitivity_grid(prices,membership,benchmark,fundamentals,
                    config,sectors=sectors,segment="validation" if config.validation_start else "full_history")
                grid.to_csv(output/"robustness_grid.csv",index=False)
            except (ValueError,RuntimeError) as exc:
                robustness_warning=str(exc)
                grid=None
            comparison_warning=None
            try:
                comparison_returns,comparison_summary=compare_index_methods(
                    prices,membership,benchmark,fundamentals,config,sectors=sectors)
                comparison_returns.to_csv(output/"methodology_returns.csv",index_label="date")
                comparison_summary.to_csv(output/"methodology_summary.csv",index_label="methodology")
            except (ValueError,RuntimeError) as exc:
                comparison_warning=str(exc)
                comparison_returns,comparison_summary=None,None
            save_experiment(result,scores,metadata,output,input_dir,sectors=sectors)
            (output/"data_audit.json").write_text(json.dumps(audit,indent=2,allow_nan=False))
            robustness_warning=None
            try:
                sensitivity=sensitivity_grid(prices,membership,benchmark,fundamentals,config,sectors=sectors,
                    costs_bps=(0.,20.),rebalance_months=(1,3),execution_lags=(0,1),
                    segment="validation" if config.validation_start else "full_history")
                sensitivity.to_csv(output/"sensitivity_grid.csv",index=False)
            except (ValueError,RuntimeError) as exc:
                robustness_warning=str(exc)
                sensitivity=None
            build_html_report(output)
            generate_pdf_report(output)
            # Keep only generated research artifacts, never re-publish API secrets
            # or raw licensed datasets. Results are ignored by Git.
            from datetime import datetime, timezone
            from uuid import uuid4
            from shutil import copytree
            run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid4().hex[:8]
            persistent=Path("results/workstation_runs")/run_id
            persistent.parent.mkdir(parents=True,exist_ok=True)
            copytree(output,persistent)
            st.session_state["index_research_last_run_dir"]=str(persistent)
            zipfile_path=root/"research_artifacts.zip"
            with zipfile.ZipFile(zipfile_path,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                for file in output.iterdir():
                    if file.is_file():
                        archive.write(file,file.name)
            st.session_state["index_research_result"]={
                "research_inputs":{"prices":prices.copy(),"membership":membership.copy(),
                                   "benchmark":benchmark.copy(),
                                   "sectors":sectors.copy() if sectors is not None else None},
                "data":pd.DataFrame({
                    "strategy":result.returns,"benchmark":result.benchmark_returns,
                    "turnover":result.turnover,"cost":result.costs}),
                "weights":result.weights.copy(),
                "scores":scores.copy(),
                "concentration":concentration_metrics(result.weights),
                "sectors":sector_exposure(result.weights,sectors.reindex(index=result.weights.index,columns=result.weights.columns)) if sectors is not None else None,
                "rolling":rolling_relative_metrics(result.returns,result.benchmark_returns),
                "sensitivity":cost_sensitivity(result.gross_returns,result.turnover) if len(result.returns)>=12 else None,
                "metadata":metadata,
                "factor_ic":factor_ic,
                "factor_portfolio_exposures":factor_portfolio_exposures,
                "data_quality":quality,
                "audit":audit,
                "robustness":grid,
                "robustness_warning":robustness_warning,
                "comparison_returns":comparison_returns,
                "comparison_summary":comparison_summary,
                "comparison_warning":comparison_warning,
                "audit":audit,
                "robustness":sensitivity,
                "robustness_warning":robustness_warning,
                "html":(output/"research_report.html").read_text(),
                "pdf":(output/"research_paper_draft.pdf").read_bytes(),
                "archive":zipfile_path.read_bytes(),
                "demo":demo,
                "saved_run_dir":str(persistent),
            }
    except Exception as exc:
        st.error(f"Research run blocked: {exc}")

if "index_research_result" not in st.session_state:
    st.markdown("""### Start here

Choose a **SYNTHETIC demonstration** to explore the workflow, select a
**local prepared folder** from the Dhan workspace, or upload a ZIP with complete
historical data. Synthetic results are for testing code and interface
only and must not appear in professional performance claims.

For real research, obtain publication-dated fundamentals, historic constituent
membership events, aligned adjusted prices and a compatible benchmark return series.
See `docs/LOCAL_RUN.md` for data formats and validation policies.
""")
    st.stop()

st.success("Research experiment generated. Local outputs saved under results/workstation_runs/.")
st.page_link("pages/11_Run_History.py",label="Open saved run history →",icon="🗂️")
saved=st.session_state["index_research_result"]
meta=saved["metadata"]
if saved["demo"]:
    st.error("SYNTHETIC DEMONSTRATION — NOT HISTORICAL MARKET RESULTS")
else:
    st.warning("USER DATA NOT INDEPENDENTLY VERIFIED — ALL RESULTS ARE RESEARCH-ONLY")

tabs=st.tabs(["Executive Overview","Index Construction","Factors","Risk & Turnover","Research Evidence"])
data=saved["data"]
growth=(1+data[["strategy","benchmark"]]).cumprod()
growth.columns=["Research index (illustrative)","User-supplied benchmark"]
with tabs[0]:
    st.subheader("Benchmark-relative performance")
    st.plotly_chart(px.line(growth,title="Normalized cumulative level (starts at 1)",labels={"value":"Wealth multiple","index":"Date","variable":"Series"}),use_container_width=True)
    st.caption("Holdout segments are reported separately below; historical return claims require data audit.")
    for name,values in meta["metrics_by_split"].items():
        st.markdown("**"+name.replace("_"," ").title()+"**")
        st.dataframe(pd.DataFrame([values]),hide_index=True,use_container_width=True)
with tabs[1]:
    st.subheader("Methodology and weights")
    st.json(meta["config"])
    st.write("Monthly weights shown during each holding interval, including drifted holdings on non-rebalance dates.")
    st.dataframe(saved["weights"].tail(12).round(4),use_container_width=True)
    latest=saved["weights"].iloc[-1].sort_values(ascending=False).head(20)
    st.plotly_chart(px.bar(x=latest.index,y=latest.values,labels={"x":"Security","y":"Portfolio weight"},title="Last modeled holding-period weights"),use_container_width=True)
with tabs[2]:
    st.subheader("Cross-sectional factor scores")
    st.caption("Factor values reflect configurable research definitions, not official index factor calculations.")
    latest_scores=saved["scores"].iloc[-1].dropna().sort_values(ascending=False)
    st.dataframe(latest_scores.rename("composite_score").to_frame().head(50),use_container_width=True)
    st.metric("Average one-step rank IC (descriptive)",str(meta["coverage"]["rank_ic_mean_descriptive"]))
    st.write("**Weight concentration through time**")
    st.plotly_chart(px.line(saved["concentration"][["hhi","largest_weight","top_five_weight"]],
                   title="Issuer concentration history"),use_container_width=True)
    if saved["sectors"] is not None:
        st.write("**Historically dated sector exposures**")
        st.plotly_chart(px.area(saved["sectors"],title="Portfolio sector weight through time"),
                        use_container_width=True)
    else:
        st.info("Sector exposures unavailable: supply date-effective sectors.csv. No historical sector allocations are invented.")
with tabs[3]:
    st.subheader("Risk, drawdown and implementation turnover")
    wealth=(1+data["strategy"]).cumprod()
    drawdown=wealth/wealth.cummax()-1
    st.plotly_chart(px.line(drawdown,labels={"value":"Drawdown","index":"Date"},title="Portfolio drawdown"),use_container_width=True)
    st.plotly_chart(px.bar(data,y="turnover",title="One-way absolute portfolio turnover"),use_container_width=True)
    st.plotly_chart(px.line(data,y="cost",title="Modeled trading-cost fraction"),use_container_width=True)
    st.plotly_chart(px.line(saved["rolling"][["rolling_volatility","rolling_tracking_error"]],
                    title="Rolling annualized volatility and tracking error"),use_container_width=True)
    if saved["sensitivity"] is not None:
        st.plotly_chart(px.line(saved["sensitivity"],x="cost_bps",y="annualized_return",
                        markers=True,title="Fixed-trade-path cost sensitivity"),use_container_width=True)
        st.caption("Cost sensitivity holds trade decisions fixed, not a reoptimized backtest.")
with tabs[4]:
    st.subheader("Research provenance and limitations")
    st.json(meta)
    st.download_button("Download reproducible experiment artifacts (ZIP)",
                       saved["archive"],file_name="index_research_artifacts.zip",
                       mime="application/zip")
    st.download_button("Download offline research report (HTML)",saved["html"],
                       file_name="index_research_report.html",mime="text/html")
    st.warning("Dashboard displays calculated results; it does not verify ownership, publication vintage, survivorship bias, adjustment policy or investability of uploaded data.")
