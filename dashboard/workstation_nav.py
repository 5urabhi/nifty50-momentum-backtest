"""Consistent sidebar navigation and session handoff for the local workstation."""
import streamlit as st

PAGES = (
    ("DATA & INGESTION", (
        ("dashboard/pages/12_Dhan_Data_Setup.py", "Dhan Data Manager", "📥"),
        ("dashboard/pages/13_Empirical_Readiness.py", "Empirical Readiness", "🧾"),
    )),
    ("INDEX & FACTORS", (
        ("dashboard/pages/1_Index_Research.py", "Run Index Research", "📈"),
        ("dashboard/pages/6_Factor_Laboratory.py", "Factor Laboratory", "🧮"),
        ("dashboard/pages/7_Index_Comparisons.py", "Index Comparisons", "⚖️"),
    )),
    ("MATHEMATICAL LABS", (
        ("dashboard/pages/3_Advanced_Mathematics.py", "Advanced Mathematics", "📐"),
        ("dashboard/pages/5_Quantitative_Models.py", "Quantitative Models", "🔬"),
        ("dashboard/pages/2_Model_Comparison.py", "Model Comparison", "📊"),
        ("dashboard/pages/4_Rolling_Validation.py", "Rolling Validation", "⏱️"),
        ("dashboard/pages/10_Visual_Validation.py", "2D / 3D Validation", "🌀"),
    )),
    ("RISK & EVIDENCE", (
        ("dashboard/pages/9_Risk_Attribution.py", "Risk Attribution", "🎯"),
        ("dashboard/pages/9_Robustness.py", "Robustness", "🛡️"),
        ("dashboard/pages/8_Research_Report.py", "Research Reports", "📑"),
        ("dashboard/pages/11_Run_History.py", "Saved Run History", "🗂️"),
    )),
)

def show_workflow_nav() -> None:
    """Compact links available on each tab; no additional Streamlit buttons."""
    with st.sidebar:
        with st.expander("🧭 WORKSTATION WORKFLOW", expanded=False):
            st.page_link("dashboard/app.py", label="Research Home", icon="🏠")
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
