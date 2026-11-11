"""Research robustness and data-evidence diagnostics from the active experiment."""
import pandas as pd
import plotly.express as px
import streamlit as st
from index_research.robustness import parameter_dispersion

st.set_page_config(page_title="Robustness & Research Audit",layout="wide")
st.title("Research Robustness & Data Audit")
st.caption("Parameter uncertainty, market-data coverage, chronology and validation gates")

saved=st.session_state.get("index_research_result")
if saved is None:
    st.info("First run an experiment on the Index Research page.")
    st.stop()
if saved.get("demo"):
    st.error("SYNTHETIC RESEARCH EXERCISE — conclusions are not empirical Nifty index findings.")
else:
    st.warning("User data are not independently verified. Audit warnings are not a substitute for official source evidence.")

tab1,tab2,tab3=st.tabs(["Robustness grid","Input audit","Release gates"])
with tab1:
    grid=saved.get("robustness")
    if grid is None or grid.empty:
        st.warning("Robustness grid unavailable: "+str(saved.get("robustness_warning")))
    else:
        st.write("Model sensitivity to rebalance frequency, execution lag and transaction costs.")
        st.dataframe(grid,hide_index=True,use_container_width=True)
        if "strategy_cagr" in grid and grid["strategy_cagr"].notna().any():
            st.plotly_chart(px.scatter(grid,x="transaction_cost_bps",y="strategy_cagr",
                color="reconstitution_months",symbol="execution_lag_months",
                title="Annualized return sensitivity — descriptive only"),use_container_width=True)
            st.json(parameter_dispersion(grid,"strategy_cagr"))
        st.caption("No combination selected as the winner; the grid is exploratory and must not be optimized on a final holdout.")
with tab2:
    audit=saved.get("audit")
    if audit:
        a,b,c=st.columns(3)
        a.metric("Historical dates",audit["number_of_monthly_marks"])
        b.metric("Securities",audit["number_of_securities"])
        c.metric("Missing held-eligible prices",audit["missing_prices_when_eligible"])
        st.json(audit)
        st.warning(audit["caveat"])
with tab3:
    st.markdown("""**Before publication:** verify constituent effective dates and security histories;
record corporate-action adjustments, total-return convention and market-data licensing;
freeze development and validation decisions before final holdout; run local unit,
integration and visual tests; audit source data and research claims.

**Source implementation ≠ empirical validation.** Unknown delisting payouts,
corporate actions, benchmark rights, missing fundamental vintages or market
impact should remain stated limitations rather than being silently invented.""")
    for name,metrics in saved["metadata"].get("metrics_by_split",{}).items():
        st.write(name,":",metrics.get("status","not available"))
