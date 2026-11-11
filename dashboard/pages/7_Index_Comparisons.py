"""Interactive index research comparisons, driven by one experiment's data."""
import pandas as pd
import plotly.express as px
import streamlit as st
from index_research.research_analytics import (
    benchmark_comparison, rolling_relative_metrics, cost_sensitivity
)

st.set_page_config(page_title="Index Comparisons and Risk",layout="wide")
st.title("Index Comparisons & Portfolio Risk")
st.caption("Benchmark-relative analytics, rolling tracking error, costs and drawdowns")
saved=st.session_state.get("index_research_result")
if saved is None:
    st.info("Run an experiment from Index Research. Comparisons never use hardcoded performance.")
    st.stop()
if saved.get("demo"):
    st.error("SYNTHETIC research exercise — cannot be cited as real index performance.")
else:
    st.warning("User-supplied input data remain unverified.")
data=saved["data"]
strategy=data["strategy"]
benchmark=data["benchmark"]
metrics=benchmark_comparison(strategy,benchmark,data["turnover"])
rows=pd.DataFrame(list(metrics.items()),columns=["Statistic","Value"])
left,right=st.columns(2)
with left:
    st.subheader("Full-period descriptive comparison")
    st.dataframe(rows,hide_index=True,use_container_width=True)
with right:
    st.subheader("Concentration profile")
    st.plotly_chart(px.line(saved["concentration"][["hhi","largest_weight","top_five_weight"]],
                           title="Concentration history"),use_container_width=True)
st.subheader("Absolute and active risk")
roll=rolling_relative_metrics(strategy,benchmark,window=12)
st.plotly_chart(px.line(roll[["rolling_tracking_error","rolling_volatility"]],
                       title="Rolling annualized risk (12 monthly observations)"),use_container_width=True)
st.plotly_chart(px.line(roll[["rolling_information_ratio","rolling_active_return"]],
                       title="Rolling active return and information ratio — different units"),
                use_container_width=True)
st.caption("The last chart overlays different units for exploration; interpret each series separately.")
st.plotly_chart(px.line(roll[["drawdown","cumulative_relative_wealth"]],
                       title="Drawdown and relative wealth — different units"),
                use_container_width=True)
st.subheader("Cost sensitivity")
if len(data)>=12:
    sensitivity=cost_sensitivity(
        (1+strategy)/(1-data["cost"])-1,
        data["turnover"],cost_levels_bps=[0,5,10,20,40,75])
    st.plotly_chart(px.line(sensitivity,x="cost_bps",y="annualized_return",markers=True,
                           title="Fixed-trade-path sensitivity to transaction costs"),use_container_width=True)
    st.dataframe(sensitivity,use_container_width=True,hide_index=True)
else:
    st.info("At least 12 monthly observations required to annualize cost sensitivity.")
st.warning("This is a single-methodology result view; a controlled multi-method experiment must run separately under identical data, splits and costs.")
