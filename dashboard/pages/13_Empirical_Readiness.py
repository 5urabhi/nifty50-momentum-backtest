"""Empirical evidence dashboard, no broker tokens and no remote calls."""
from pathlib import Path
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

st.subheader("Import missing evidence into this local dataset")
st.caption("Upload reviewed CSV/JSON files here instead of moving files in a terminal. The tool only checks basic structure; importing a file does NOT independently validate its origin or historical correctness.")
allowed_names={
    "prices.csv": {"date"},
    "membership.csv": {"date","ticker","eligible"},
    "benchmark.csv": {"date","return"},
    "fundamentals.csv": {"ticker","available_at","value","quality","size"},
    "sectors.csv": {"date","ticker","sector"},
    "corporate_actions.csv": set(),
    "EVIDENCE_REVIEW.json": set(),
}
uploads=st.file_uploader("Select source evidence files",type=["csv","json"],
    accept_multiple_files=True,key="evidence_import")
replace_existing=st.checkbox("Replace matching existing local files after explicit review",
    value=False,key="evidence_overwrite")
acknowledge=st.checkbox("I understand that file upload does not certify market-data provenance",
    value=False,key="evidence_ack")
if st.button("Save reviewed evidence files to selected local dataset",
             disabled=not(bool(uploads) and acknowledge),type="primary"):
    import io
    import json
    import tempfile
    try:
        payloads={}
        for upload in uploads:
            filename=upload.name
            if filename not in allowed_names:
                raise ValueError("Unrecognized filename: "+filename+
                    ". Use the exact contract names from the evidence inventory.")
            if filename in payloads:
                raise ValueError("Duplicate uploaded filename: "+filename)
            data=upload.getvalue()
            if not data or len(data)>25*1024*1024:
                raise ValueError("Each file must contain 1–25 MiB maximum: "+filename)
            if (root/filename).exists() and not replace_existing:
                raise FileExistsError(filename+" already exists. Check explicit replace option to overwrite.")
            if filename.endswith(".csv"):
                frame=pd.read_csv(io.BytesIO(data),nrows=100,dtype=str)
                required=allowed_names[filename]
                missing=required-set(frame.columns)
                if missing:
                    raise ValueError(filename+" lacks mandatory columns: "+", ".join(sorted(missing)))
            else:
                review=json.loads(data)
                if not isinstance(review,dict):
                    raise ValueError(filename+" must contain a JSON object")
            payloads[filename]=data
        root.mkdir(parents=True,exist_ok=True)
        # Each file is fully validated and staged before any destination change.
        staged=[]
        try:
            for filename,data in payloads.items():
                with tempfile.NamedTemporaryFile(dir=root,prefix=".evidence_",delete=False) as temp:
                    temp.write(data)
                    staged.append((Path(temp.name),root/filename))
            for temporary,destination in staged:
                temporary.replace(destination)
        finally:
            for temporary,_ in staged:
                temporary.unlink(missing_ok=True)
        st.success(f"Saved {len(payloads)} input files locally. Now review the evidence gate and inspect data before running experiments.")
        st.rerun()
    except Exception as exc:
        st.error("Import blocked: "+str(exc))
st.caption("Never upload broker credentials or private customer holdings. The files remain in the ignored local data folder and are never sent to the React website.")

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
