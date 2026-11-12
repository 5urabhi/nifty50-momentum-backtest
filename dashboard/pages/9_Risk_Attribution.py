"""Risk attribution and explicitly hypothetical scenario analysis."""
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
from index_research.math_models import historical_var_es
from index_research.portfolio_theory import risk_contributions
from index_research.sector_data import concentration_metrics

st.set_page_config(page_title="Risk Attribution and Stress Lab",layout="wide")
show_workflow_nav()
st.title("Portfolio Risk Attribution")
st.caption("Issuer concentration · covariance decomposition · historical losses · hypothetical stress")
saved=st.session_state.get("index_research_result")
if saved is None or "research_inputs" not in saved:
    st.info("Run an experiment in Index Research to activate historical portfolio inputs.")
    st.stop()
if saved.get("demo"):
    st.error("SYNTHETIC experiment: any risk estimate is a numerical demonstration, not real market history.")
else:
    st.warning("Historical prices and benchmark have not been independently verified.")

prices=saved["research_inputs"]["prices"]
weights=saved["weights"]
ret=saved["data"]["strategy"]
latest=weights.iloc[-1]
c=st.columns(4)
concentration=concentration_metrics(weights)
c[0].metric("Latest holdings",int((latest>1e-12).sum()))
c[1].metric("Largest position",f"{latest.max():.2%}")
c[2].metric("HHI",f"{concentration['hhi'].iloc[-1]:.3f}")
c[3].metric("Effective names",f"{concentration['effective_names'].iloc[-1]:.1f}" if np.isfinite(concentration['effective_names'].iloc[-1]) else "N/A")
st.plotly_chart(px.line(concentration[["hhi","largest_weight","top_five_weight"]],
                title="Issuer concentration over time"),use_container_width=True)
st.subheader("Trailing covariance and volatility contributions")
window=st.slider("Historical covariance lookback (months)",min_value=12,max_value=min(60,max(12,len(prices)-1)),value=min(36,max(12,len(prices)-1)))
try:
    trailing=prices.pct_change(fill_method=None).iloc[-window:].dropna(axis=1,how="any").dropna(axis=0,how="any")
    assets=latest.loc[latest>1e-12].index
    if len(assets)<2 or not set(assets).issubset(trailing.columns) or len(trailing)<12:
        st.info("Need >=2 held securities with 12 complete trailing returns to decompose covariance risk.")
    else:
        held=trailing.loc[:,assets]
        portfolio=latest.loc[assets]
        portfolio=portfolio/portfolio.sum()
        covariance=held.cov()*12
        contrib=risk_contributions(portfolio,covariance)
        st.plotly_chart(px.bar(contrib,x=contrib.index,y="volatility_contribution",
                      title="Euler contributions to annualized volatility"),
                      use_container_width=True)
        st.dataframe(contrib.round(5),use_container_width=True)
        st.plotly_chart(px.imshow(held.corr(),zmin=-1,zmax=1,color_continuous_scale="RdBu",
                         title="Trailing held-security return correlation"),use_container_width=True)
        st.caption("Sample covariance uses complete trailing monthly returns, not a commercial factor-risk model.")
except Exception as exc:
    st.error(f"Covariance decomposition unavailable: {exc}")

st.subheader("Historical downside risk")
if len(ret.dropna())>=20:
    conf=st.slider("Loss confidence",min_value=.80,max_value=.99,value=.95,step=.01)
    try:
        risk=historical_var_es(ret,confidence=conf)
        a,b=st.columns(2)
        a.metric("Historical VaR",f"{risk['var']:.2%}")
        b.metric("Empirical tail average",f"{risk['expected_shortfall']:.2%}")
        st.plotly_chart(px.histogram(x=-ret,bins=40,labels={"x":"One-period loss"},
                        title="Observed research index losses"),use_container_width=True)
    except ValueError as exc:
        st.error(str(exc))
else:
    st.info("At least twenty realized research-period returns are required for empirical loss estimates.")

st.subheader("Sector shock worksheet")
sector=saved.get("sectors")
if sector is None:
    st.info("No historical sector file supplied. A sector shock chart cannot be generated from current-day classifications.")
else:
    allocations=sector.iloc[-1].sort_values(ascending=False)
    chosen=st.selectbox("Sector to stress",list(allocations.index))
    shock=st.slider("Hypothetical one-period sector return shock",min_value=-0.80,max_value=0.80,value=-0.20,step=.05)
    sector_weight=float(allocations.loc[chosen])
    estimated=sector_weight*shock
    st.metric("Linear portfolio return contribution",f"{estimated:.2%}")
    st.write("Sector allocation:",f"{sector_weight:.2%}")
    st.caption("This is weight × assumed return only. All other sectors are held at zero return; no correlations, nonlinear products, liquidity shocks or second-round effects.")
