"""Interactive research lab. Run: streamlit run dashboard/app.py

Market-data dependent panels require user-uploaded return data. We intentionally
do not display the original unvalidated notebook's optimized Sharpe as fact.
"""
import io
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from index_research.derivatives import heston_paths, merton_jump_diffusion
from index_research.math_models import (
    sample_covariance, shrinkage_covariance, ewma_covariance,
    minimum_variance, historical_var_es, simulate_gbm, black_scholes,
)

st.set_page_config(page_title="Equity Index Quant Research Lab",layout="wide")
st.title("Equity Index Quantitative Research Laboratory")
st.caption("Research demonstrations only · Not an investable strategy or MSCI methodology")
st.warning("The legacy 3.34 Sharpe and 132.86% annualized return are not audited. No historical index performance is claimed here.")

tabs=st.tabs(["Covariance & Optimization","Downside Risk","Stochastic Processes","Black–Scholes","Stochastic Volatility & Jumps"])

with tabs[0]:
    st.subheader("Empirical covariance and long-only minimum-variance weights")
    st.write("Upload monthly **simple total returns** in decimal units, with a date column and one column per stock. Example: 0.01 = 1%. No missing values.")
    uploaded=st.file_uploader("Historical monthly returns CSV",type="csv")
    if uploaded is not None:
        try:
            raw=pd.read_csv(uploaded)
            if raw.shape[1] < 3:
                raise ValueError("Expected date + at least two numeric security columns")
            dates=pd.to_datetime(raw.iloc[:,0],errors="raise")
            if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
                raise ValueError("Dates must be valid, unique and ascending")
            values=raw.iloc[:,1:].apply(pd.to_numeric, errors="raise")
            values.index=pd.DatetimeIndex(dates)
            if len(values)<12 or values.isna().any().any() or not np.isfinite(values.to_numpy()).all():
                raise ValueError("Need >=12 complete rows with finite returns")
            model=st.selectbox("Covariance estimator",["Sample","Diagonal shrinkage","EWMA"])
            if model=="Sample":
                cov=sample_covariance(values)
            elif model=="Diagonal shrinkage":
                shrink=st.slider("Shrinkage toward diagonal",0.0,1.0,0.25)
                cov=shrinkage_covariance(values,shrink)
            else:
                decay=st.slider("EWMA decay",0.01,0.99,0.94)
                cov=ewma_covariance(values,decay)
            maximum=st.slider("Maximum single-stock weight",min_value=1.0/len(values.columns),max_value=1.0,value=1.0,format="%.3f")
            solution=minimum_variance(cov,max_weight=maximum)
            left,right=st.columns(2)
            left.metric("Estimated annualized portfolio volatility",f"{solution.volatility:.2%}")
            right.metric("Number of securities",len(values.columns))
            st.plotly_chart(px.bar(x=solution.weights.index,y=solution.weights.values,labels={"x":"Security","y":"Optimized weight"},title="Constrained minimum-variance weights"),use_container_width=True)
            corr=values.corr()
            st.plotly_chart(px.imshow(corr,x=corr.columns,y=corr.index,color_continuous_scale="RdBu",zmin=-1,zmax=1,title="Historical sample return correlation"),use_container_width=True)
            st.info("These are **in-sample estimated weights**, not a backtest. Recompute only on prior-period data and evaluate out of sample before measuring performance.")
        except Exception as exc:
            st.error(f"Input/optimization validation failed: {exc}")
    else:
        st.info("Upload actual monthly return data to enable this panel. No synthetic performance is substituted.")

with tabs[1]:
    st.subheader("Empirical loss distribution")
    st.write("Upload a CSV with a column of realized simple portfolio returns (decimal units).")
    risk_upload=st.file_uploader("Portfolio return CSV",type="csv",key="risk")
    confidence=st.slider("Confidence level",0.80,0.99,0.95,step=0.01)
    if risk_upload is not None:
        try:
            frame=pd.read_csv(risk_upload)
            numeric=frame.select_dtypes(include="number")
            if numeric.empty:
                raise ValueError("No numeric return column")
            key=st.selectbox("Return column",list(numeric.columns))
            returns=numeric[key].dropna()
            metrics=historical_var_es(returns,confidence)
            a,b=st.columns(2)
            a.metric("Historical VaR (loss fraction)",f"{metrics['var']:.2%}")
            b.metric("Empirical Expected Shortfall",f"{metrics['expected_shortfall']:.2%}")
            st.plotly_chart(px.histogram(x=-returns,bins=40,labels={"x":"Realized loss","y":"Count"},title="Empirical loss distribution"),use_container_width=True)
            st.caption("Historical quantile/tail mean; not regulatory ES and not a probabilistic guarantee.")
        except Exception as exc:
            st.error(f"Input validation failed: {exc}")

with tabs[2]:
    st.subheader("Geometric Brownian Motion: hypothetical price paths")
    c1,c2,c3=st.columns(3)
    s0=c1.number_input("Initial price",min_value=1.0,value=100.0)
    drift=c2.number_input("Assumed annual drift",value=0.05,step=0.01)
    vol=c3.number_input("Assumed annual volatility",min_value=0.0,value=0.20,step=0.01)
    paths=simulate_gbm(s0,drift,vol,1.0,252,100,seed=2026)
    st.plotly_chart(px.line(pd.DataFrame(paths[:,:15]),labels={"index":"Trading-step proxy","value":"Simulated price","variable":"Path"},title="15 simulated paths from 100 Monte Carlo paths"),use_container_width=True)
    st.caption("Illustrative Gaussian GBM simulation: parameters are user-provided, NOT calibrated to Nifty data.")

with tabs[3]:
    st.subheader("European Black–Scholes–Merton option pricing")
    a,b,c=st.columns(3)
    spot=a.number_input("Underlying spot",min_value=0.01,value=100.0)
    strike=b.number_input("Strike",min_value=0.01,value=100.0)
    years=c.number_input("Time to expiry (years)",min_value=0.001,value=1.0)
    d,e,f=st.columns(3)
    rate=d.number_input("Annual continuously compounded risk-free rate",value=0.05)
    sigma=e.number_input("Annual volatility",min_value=0.001,value=0.20)
    q=f.number_input("Continuous dividend yield",value=0.0)
    opt=st.radio("Option type",["call","put"],horizontal=True)
    output=black_scholes(spot,strike,years,rate,sigma,opt,q)
    st.dataframe(pd.DataFrame([output]).T.rename(columns={0:"Value"}),use_container_width=True)
    st.caption("Theoretical European option formula under lognormal diffusion and constant volatility; unrelated to realized index performance.")

with tabs[4]:
    st.subheader("Heston stochastic volatility and Merton jump diffusion")
    st.info("Theoretical simulations are not market-calibrated forecasts.")
    sim=st.selectbox("Stochastic model",["Heston","Merton jump diffusion"])
    initial_price=st.number_input("Initial price",min_value=0.01,value=100.0,key="stoch_spot")
    annual_drift=st.number_input("Assumed annual drift",value=.05,key="stoch_mu")
    annual_vol=st.number_input("Assumed diffusion volatility",min_value=0.001,value=.2,key="stoch_sigma")
    if sim=="Heston":
        kappa=st.number_input("Variance mean reversion",min_value=.01,value=2.0)
        volvol=st.number_input("Volatility of variance",min_value=0.0,value=.4)
        rho=st.slider("Stock-variance innovation correlation",-1.0,1.0,-.6,.05)
        heston=heston_paths(initial_price,annual_vol**2,years=1,steps=252,paths=80,
                            rate=annual_drift,kappa=kappa,long_variance=annual_vol**2,
                            vol_of_vol=volvol,rho=rho,seed=2026)
        st.plotly_chart(px.line(pd.DataFrame(heston["prices"][:,:12]),
                      title="Hypothetical Heston price paths"),use_container_width=True)
        st.plotly_chart(px.line(pd.DataFrame(heston["variance"][:,:12]),
                      title="Simulated variance paths"),use_container_width=True)
        st.caption(heston["warning"])
    else:
        jump_intensity=st.number_input("Expected jumps per year",min_value=0.0,value=1.0)
        jump_mean=st.number_input("Mean log-jump size",value=-.1)
        jump_sd=st.number_input("Log-jump standard deviation",min_value=0.0,value=.15)
        sample=merton_jump_diffusion(initial_price,1,252,80,annual_drift,annual_vol,
                                     jump_intensity,jump_mean,jump_sd,seed=2026)
        st.plotly_chart(px.line(pd.DataFrame(sample[:,:12]),
                      title="Hypothetical compensated Merton jump paths"),use_container_width=True)
