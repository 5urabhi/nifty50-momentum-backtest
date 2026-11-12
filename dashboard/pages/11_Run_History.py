"""Persistent local research run browser: charts, artifacts and evidence status."""
from pathlib import Path
import json
import io
import zipfile

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
# Ensure project packages resolve when Streamlit runs a page by file path.
import sys
from pathlib import Path as _ProjectPath
_PROJECT_ROOT = str(_ProjectPath(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dashboard.workstation_nav import show_workflow_nav

st.set_page_config(page_title="Saved Research Runs", layout="wide")
show_workflow_nav()
st.title("Saved Research Runs")
st.caption("Local persistent experiment outputs · compare methodology and export evidence")
st.warning("Files here are research artifacts, NOT independently audited historical performance. Synthetic runs must never be presented as real Nifty results.")
ROOT=Path(__file__).resolve().parents[2]
RUNS=ROOT/"results"/"workstation_runs"
RUNS.mkdir(parents=True,exist_ok=True)
folders=sorted((p for p in RUNS.iterdir() if p.is_dir() and (p/"research_manifest.json").is_file()),reverse=True)

if not folders:
    st.info("No saved experiments yet. Run Index Research with a synthetic or approved dataset to create a run.")
    st.page_link("pages/1_Index_Research.py",label="Open Index Research →",icon="📈")
    st.stop()

summary=[]
for folder in folders:
    try:
        m=json.loads((folder/"research_manifest.json").read_text())
        config=m.get("config",{})
        summary.append({"Run":folder.name,"Experiment":config.get("name","Unknown"),
                        "Dataset status":config.get("dataset_status","unverified"),
                        "Files":len(list(folder.iterdir())),"Path":str(folder.relative_to(ROOT))})
    except (ValueError,OSError):
        summary.append({"Run":folder.name,"Experiment":"Invalid manifest",
                        "Dataset status":"BLOCKED","Files":0,"Path":str(folder.relative_to(ROOT))})
st.dataframe(pd.DataFrame(summary),hide_index=True,use_container_width=True)

default=st.session_state.get("index_research_last_run_dir")
idx=next((i for i,f in enumerate(folders) if str(f)==str(default)),0)
selected=st.selectbox("Inspect a saved experiment",folders,index=idx,format_func=lambda p:p.name)
try:
    manifest=json.loads((selected/"research_manifest.json").read_text())
except (ValueError,OSError) as exc:
    st.error(f"Manifest failed to load: {exc}")
    st.stop()
status=manifest.get("config",{}).get("dataset_status","unverified")
if status in ("static_universe_demo","synthetic"):
    st.error("SYNTHETIC OR STATIC-UNIVERSE DEMONSTRATION · NOT HISTORICAL PERFORMANCE")
else:
    st.warning("MARKET DATA SOURCE NOT INDEPENDENTLY VERIFIED · REVIEW REQUIRED")
st.subheader("Run metadata")
st.json({"config":manifest.get("config",{}),
         "metrics_by_split":manifest.get("metrics_by_split",{}),
         "coverage":manifest.get("coverage",{}),
         "limitations":manifest.get("limitations",[])})

tabs=st.tabs(["Performance & risk","Holdings & factors","Validation artifacts","Export"])
with tabs[0]:
    path=selected/"monthly_results.csv"
    if path.is_file():
        try:
            df=pd.read_csv(path)
            if {"strategy_net","benchmark"}.issubset(df.columns):
                r=df[["strategy_net","benchmark"]].apply(pd.to_numeric,errors="raise")
                if not np.isfinite(r.to_numpy()).all():
                    raise ValueError("Nonfinite returns")
                wealth=(1+r).cumprod()
                wealth.columns=["Strategy wealth","Supplied benchmark wealth"]
                if "date" in df.columns:
                    wealth.index=pd.to_datetime(df.date,errors="raise")
                st.plotly_chart(px.line(wealth,title="Cumulative wealth of one unit"),use_container_width=True)
                dd=wealth["Strategy wealth"]/wealth["Strategy wealth"].cummax()-1
                st.plotly_chart(px.line(dd,title="Strategy drawdown"),use_container_width=True)
            st.dataframe(df.tail(25),hide_index=True,use_container_width=True)
        except (ValueError,KeyError) as exc:
            st.error(f"Cannot plot saved return table: {exc}")
    else:
        st.info("This run does not contain monthly_results.csv")
with tabs[1]:
    for filename,title in [
        ("post_rebalance_weights.csv","Post-rebalance holdings"),
        ("factor_scores.csv","Factor scores"),
        ("factor_rank_ic.csv","Factor rank information coefficient")]:
        path=selected/filename
        if path.is_file():
            st.subheader(title)
            st.dataframe(pd.read_csv(path).tail(30),hide_index=True,use_container_width=True)
with tabs[2]:
    for filename,title in [
        ("data_quality.json","Data quality"),
        ("dataset_audit.json","Data audit"),
        ("robustness_grid.csv","Robustness grid"),
        ("methodology_summary.csv","Methodology comparison"),
        ("concentration.csv","Concentration")]:
        path=selected/filename
        if path.is_file():
            st.subheader(title)
            if path.suffix==".json":
                st.json(json.loads(path.read_text()))
            else:
                st.dataframe(pd.read_csv(path).tail(100),hide_index=True,use_container_width=True)
with tabs[3]:
    st.subheader("Download reproducible run outputs")
    files=[p for p in selected.iterdir() if p.is_file()]
    st.dataframe(pd.DataFrame([{"Filename":p.name,"Size (KiB)":round(p.stat().st_size/1024,1)}
                              for p in files]),hide_index=True,use_container_width=True)
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path,path.name)
    st.download_button("Download experiment artifacts ZIP",archive.getvalue(),
                       file_name=selected.name+".zip",mime="application/zip",type="primary")
    html=selected/"research_report.html"
    pdf=selected/"research_paper_draft.pdf"
    if html.is_file():
        st.download_button("Download HTML research report",html.read_bytes(),
            file_name=selected.name+".html",mime="text/html")
    if pdf.is_file():
        st.download_button("Download PDF research draft",pdf.read_bytes(),
            file_name=selected.name+".pdf",mime="application/pdf")
st.page_link("pages/1_Index_Research.py",label="Run another experiment →",icon="📈")
