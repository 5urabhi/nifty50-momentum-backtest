"""Factor research: as-of composite scores, rank IC, quantile diagnostic and exposures."""
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

st.set_page_config(page_title="Factor Research Laboratory",layout="wide")
show_workflow_nav()
st.title("Factor Research Laboratory")
st.caption("Factor selection, robustness, information coefficients and portfolio exposure")
saved=st.session_state.get("index_research_result")
if saved is None:
    st.info("Run an experiment in Index Research first; this page uses the same validated input path.")
    st.stop()
if saved.get("demo"):
    st.error("SYNTHETIC data: factor observations are not genuine historical market signals.")
else:
    st.warning("Factor data provenance and point-in-time availability require independent audit.")
scores=saved["scores"]
weights=saved["weights"]
meta=saved["metadata"]
st.write("**Research factor allocation**")
st.json(meta["factor_weights_used"])
st.metric("Composite score availability",f"{meta['coverage']['scored_fraction']:.1%}")
st.metric("Rank information coefficient (descriptive)",str(meta["coverage"]["rank_ic_mean_descriptive"]))
dates=scores.index[scores.notna().any(axis=1)]
if len(dates):
    decision=st.select_slider("Decision date",options=list(dates),value=dates[-1],
                              format_func=lambda d:pd.Timestamp(d).strftime("%Y-%m-%d"))
    ranking=scores.loc[decision].dropna().sort_values(ascending=False)
    st.subheader("Cross-sectional scores")
    st.plotly_chart(px.bar(x=ranking.head(30).index,y=ranking.head(30).values,
                            labels={"x":"Security","y":"Composite score"},
                            title=f"Top 30 ranked securities — {decision.date()}"),
                    use_container_width=True)
    st.dataframe(ranking.rename("score").to_frame(),use_container_width=True)
st.subheader("Factor-specific information coefficients")
ic=saved.get("factor_ic")
if ic is not None:
    st.plotly_chart(px.line(ic,title="Next-period cross-sectional factor rank IC"),
                    use_container_width=True)
    st.dataframe(ic.agg(["count","mean","std"]).T.rename(columns={
        "count":"periods","mean":"mean_rank_ic","std":"ic_std"
    }),use_container_width=True)
else:
    st.info("No factor IC panel is available for this experiment.")
st.subheader("Portfolio factor exposures")
factor_exposures=saved.get("factor_portfolio_exposures")
if factor_exposures is not None:
    st.plotly_chart(px.line(factor_exposures,
                    title="Holding-period factor exposures using prior decision signals"),
                    use_container_width=True)
else:
    st.info("No portfolio factor-exposure history available.")
st.subheader("Portfolio exposure and concentration")
st.plotly_chart(px.line(saved["concentration"][["effective_names","nonzero_holdings"]],
                       title="Effective number of names versus number held"),use_container_width=True)
if saved.get("sectors") is None:
    st.info("Historical sector exposure requires sectors.csv; no current sector label is backfilled.")
else:
    exposure=saved["sectors"]
    latest=exposure.iloc[-1].sort_values(ascending=False)
    st.plotly_chart(px.bar(x=latest.index,y=latest.values,
                           labels={"x":"Sector","y":"Allocation"},title="Latest recorded sector exposure"),
                    use_container_width=True)
    st.plotly_chart(px.area(exposure,title="Historical sector allocations"),use_container_width=True)
st.subheader("Interpretation and limitations")
st.markdown("""Rank IC and high-minus-low diagnostics describe cross-sectional relationships
and are not independently validated future forecasts. Factor scores require
verified publication dates, sector histories, corporate actions and a
chronologically frozen test design before public investment conclusions.""")

st.subheader("Input data coverage")
st.json(saved.get("data_quality",{}))
st.caption("A complete numeric data matrix is not proof that price adjustments, membership, sector assignments or filing dates were historically correct.")
