"""Research report viewer and artifact downloads for the active experiment."""
import json
import pandas as pd
import streamlit as st
st.set_page_config(page_title="Research Report & Evidence",layout="wide")
st.title("Research Report & Reproducibility")
st.caption("Methods, holdout periods, provenance, reproducibility exports")
saved=st.session_state.get("index_research_result")
if saved is None:
    st.info("Run Index Research to generate reproducible artifacts and the offline report.")
    st.stop()
meta=saved["metadata"]
if saved.get("demo"):
    st.error("SYNTHETIC DATASET — report is for local demonstration only.")
else:
    st.warning("MARKET DATA UNVERIFIED — do not use outputs as resume performance claims yet.")
tabs=st.tabs(["Research Summary","Performance by Split","Evidence","Downloads"])
with tabs[0]:
    st.subheader("Research hypothesis")
    st.markdown("Evaluate whether transparent rules-based multi-factor equity selection improves risk-adjusted and benchmark-relative outcomes, while controlling issuer, sector, active risk and turnover.")
    st.json(meta["config"])
    st.write("**Coverage and concentration**")
    st.json(meta["coverage"])
with tabs[1]:
    for name,metrics in meta["metrics_by_split"].items():
        st.subheader(name.replace("_"," ").title())
        st.dataframe(pd.DataFrame([metrics]),hide_index=True,use_container_width=True)
    st.info("Chronological segment labels are descriptive. The user must freeze model choices before opening the final holdout.")
with tabs[2]:
    st.subheader("Input file fingerprints")
    st.json(meta.get("input_sha256",{}))
    st.subheader("Limitations")
    for item in meta["limitations"]:
        st.write("• "+item)
    st.caption("SHA-256 fingerprints enable traceability; they do not prove data accuracy or license rights.")
with tabs[3]:
    st.download_button("Offline HTML research report",data=saved["html"],
                       file_name="index_research_report.html",mime="text/html")
    st.download_button("Reproducible CSV/JSON/HTML bundle",data=saved["archive"],
                       file_name="index_research_artifacts.zip",mime="application/zip")
    st.markdown("Open the HTML report locally. Share it publicly only after the dataset, methodology and results have been independently validated.")
