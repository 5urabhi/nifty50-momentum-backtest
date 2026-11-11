"""Empirical evidence dashboard, no broker tokens and no remote calls."""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.workstation_nav import show_workflow_nav
from index_research.empirical_validation import evidence_gate, assess_holdout

st.set_page_config(page_title="Empirical Research Readiness",layout="wide")
show_workflow_nav()
st.title("Empirical Research Readiness")
st.caption("Corporate-action evidence, publication-date factors, Nifty TRI, frozen holdout")
st.warning("A complete source-code module does not certify actual market data. No automatic approval.")

default_root=Path("data/research_v1")
candidate=st.session_state.get("research_input_dir")
known=[default_root]
monthly_root=Path("data/dhan/monthly_research")
if monthly_root.exists():
    known.extend(sorted(p.parent for p in monthly_root.glob("*/prices.csv")))
if candidate:
    selected_candidate=Path(candidate)
    allowed=any(selected_candidate.resolve()==p.resolve() for p in known)
    if allowed and selected_candidate not in known:
        known.append(selected_candidate)
idx=next((i for i,p in enumerate(known) if candidate and str(p.resolve())==str(Path(candidate).resolve())),0)
root=st.selectbox("Inspect local research input directory",known,index=idx,format_func=str)
st.session_state["research_input_dir"]=str(root.resolve())
runs=Path("results/research_v1")
st.page_link("dashboard/pages/12_Dhan_Data_Setup.py",label="Back to Dhan Historical Data →",icon="📥")
st.page_link("dashboard/pages/1_Index_Research.py",label="Continue to Index Research →",icon="📈")
items=[
    ("prices.csv","Normalized shareholder-return wealth indices"),
    ("corporate_actions.csv","Dated cash dividends, splits and delistings"),
    ("fundamentals.csv","Publication-date Value, Quality and Size"),
    ("membership.csv","Nifty historical membership effective dates"),
    ("sectors.csv","Historical sector classifications"),
    ("benchmark.csv","Official compatible Nifty TRI benchmark"),
    ("EVIDENCE_REVIEW.json","Human source-review declarations"),
]
table=pd.DataFrame([{"Evidence":name,"Purpose":purpose,
                     "Local":"Available" if (root/name).is_file() else "MISSING"}
                    for name,purpose in items])
st.subheader("Historical data inventory")
st.dataframe(table,hide_index=True,use_container_width=True)
a,b,c=st.columns(3)
a.metric("Files available",int((table.Local=="Available").sum()))
b.metric("Expected files",len(table))
c.metric("Readiness","BLOCKED" if (table.Local=="MISSING").any() else "Review required")
st.write("Local inputs are selected above and kept under ignored data/ folders. Data presence does not certify provenance.")
st.write("See docs/EMPIRICAL_DATA_GUIDE.md for authorized data export and preparation.")
st.code("python scripts/prepare_research_data.py --help",language="bash")

tab1,tab2,tab3,tab4=st.tabs(["Return series","Fundamental vintages","Evidence gate","Results"])
with tab1:
    file=root/"prices.csv"
    if file.exists():
        try:
            df=pd.read_csv(file,parse_dates=[0])
            df=df.set_index(df.columns[0])
            numeric=df.apply(pd.to_numeric,errors="coerce")
            if numeric.empty: raise ValueError("no security columns")
            selected=st.selectbox("Security wealth index",list(numeric.columns))
            chart=pd.DataFrame({"date":numeric.index,"wealth":numeric[selected].to_numpy()})
            st.plotly_chart(px.line(chart,x="date",y="wealth",
                title="Sourced shareholder-return wealth index"),
                use_container_width=True)
            st.caption("Data presence alone cannot establish complete event adjustments.")
        except Exception as exc:
            st.error(f"Price matrix invalid: {exc}")
    else:
        st.info("First prepare dated corporate-action and market-return series.")
with tab2:
    path=root/"fundamentals.csv"
    if path.exists():
        try:
            frame=pd.read_csv(path)
            if not {"ticker","available_at","value","quality","size"}.issubset(frame):
                raise ValueError("missing factor fields")
            frame["available_at"]=pd.to_datetime(frame["available_at"],errors="raise")
            st.dataframe(frame.tail(50),use_container_width=True)
            asset=st.selectbox("Security filing-vintage history",sorted(frame.ticker.unique()))
            slice=frame[frame.ticker==asset]
            st.plotly_chart(px.line(slice,x="available_at",y=["value","quality"],
                title="Published financial factor observations"),use_container_width=True)
            st.caption("Availability dates must be first-public evidence, not restatements backfilled into history.")
        except Exception as exc:
            st.error(f"Filing matrix invalid: {exc}")
    else:
        st.info("No publication-dated financial factor file supplied.")
with tab3:
    try:
        gate=evidence_gate(root,root/"EVIDENCE_REVIEW.json")
        st.json(gate)
        if gate["status"]=="BLOCKED":
            st.error("Empirical evidence gate blocked.")
        else:
            st.warning("Evidence declared; underlying source accuracy still requires independent review.")
    except Exception as exc:
        st.error(f"Evidence review unavailable: {exc}")
with tab4:
    if (runs/"research_manifest.json").exists():
        try:
            report=assess_holdout(runs,root,root/"EVIDENCE_REVIEW.json")
            st.json(report)
            if report["status"]!="REVIEW_READY_NOT_EXTERNALLY_AUDITED":
                st.error("Results are not ready for publication.")
            else:
                st.warning("Review-ready only; not externally audited.")
        except Exception as exc:
            st.error(f"Holdout review failed: {exc}")
    else:
        st.info("No genuine historical experiment has been run locally. No hypothetical results shown.")
