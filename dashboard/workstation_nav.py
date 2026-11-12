"""Consistent sidebar navigation and session handoff for the local workstation."""
import streamlit as st

PAGES = (
    ("DATA & INGESTION", (
        ("pages/12_Dhan_Data_Setup.py", "Dhan Data Manager", "📥"),
        ("pages/13_Empirical_Readiness.py", "Empirical Readiness", "🧾"),
    )),
    ("INDEX & FACTORS", (
        ("pages/1_Index_Research.py", "Run Index Research", "📈"),
        ("pages/6_Factor_Laboratory.py", "Factor Laboratory", "🧮"),
        ("pages/7_Index_Comparisons.py", "Index Comparisons", "⚖️"),
    )),
    ("MATHEMATICAL LABS", (
        ("pages/3_Advanced_Mathematics.py", "Advanced Mathematics", "📐"),
        ("pages/5_Quantitative_Models.py", "Quantitative Models", "🔬"),
        ("pages/2_Model_Comparison.py", "Model Comparison", "📊"),
        ("pages/4_Rolling_Validation.py", "Rolling Validation", "⏱️"),
        ("pages/10_Visual_Validation.py", "2D / 3D Validation", "🌀"),
    )),
    ("RISK & EVIDENCE", (
        ("pages/9_Risk_Attribution.py", "Risk Attribution", "🎯"),
        ("pages/9_Robustness.py", "Robustness", "🛡️"),
        ("pages/8_Research_Report.py", "Research Reports", "📑"),
        ("pages/11_Run_History.py", "Saved Run History", "🗂️"),
    )),
)

def show_workflow_nav() -> None:
    """Compact links available on each tab; no additional Streamlit buttons."""
    with st.sidebar:
        with st.expander("🧭 WORKSTATION WORKFLOW", expanded=False):
            st.page_link("app.py", label="Research Home", icon="🏠")
            for category, entries in PAGES:
                st.caption(category)
                for path, name, icon in entries:
                    st.page_link(path, label=name, icon=icon)
        active=st.session_state.get("index_research_result")
        dataset=st.session_state.get("research_input_dir")
        if active:
            st.caption("🟢 Experiment active · " +
                       ("SYNTHETIC" if active.get("demo") else "UNVERIFIED inputs"))
        elif dataset:
            st.caption("🟡 Prepared local folder selected · not yet evaluated")
        else:
            st.caption("⚪ No active experiment · start with Dhan or Index Research")
