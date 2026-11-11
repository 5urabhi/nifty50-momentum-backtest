"""Advanced quantitative models with transparent, user-provided data."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.workstation_nav import show_workflow_nav

from index_research.advanced_models import (
    principal_components, fit_garch11, simulate_ou, covariance_stress_loss,
)
from index_research.math_models import (
    factor_regression, sample_covariance, shrinkage_covariance,
    ewma_covariance, minimum_variance,
)

st.set_page_config(page_title="Quantitative Model Comparison",layout="wide")
show_workflow_nav()
st.title("Quantitative Model Comparison Laboratory")
st.caption("PCA · factor regression · GARCH · EWMA · stochastic mean reversion")
st.warning("Inputs must be real, date-aligned observations. Synthetic demonstrations are not validated financial forecasts.")

tab1,tab2,tab3,tab4=st.tabs(["PCA Exposures","Volatility Models","Factor Regression","Mean-Reverting Processes"])

def return_data(upload, minimum):
    if upload is None:
        return None
    frame=pd.read_csv(upload)
    if len(frame.columns)<2:
        raise ValueError("CSV must include date column and at least one numeric series")
    dates=pd.to_datetime(frame.iloc[:,0],errors="raise")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("dates must be valid, unique and increasing")
    v=frame.iloc[:,1:].apply(pd.to_numeric,errors="raise")
    v.index=pd.DatetimeIndex(dates)
    if len(v)<minimum or v.isna().any().any() or not np.isfinite(v.to_numpy()).all():
        raise ValueError(f">={minimum} fully observed rows required")
    return v

with tab1:
    st.subheader("Principal component analysis of standardized return exposures")
    up=st.file_uploader("Upload historical returns CSV",type="csv",key="pca")
    try:
        values=return_data(up,12)
        if values is not None:
            if values.shape[1]<2: raise ValueError("PCA requires >=2 securities")
            count=st.slider("Number of components",1,min(values.shape),min(3,values.shape[1]))
            result=principal_components(values,count)
            explained=pd.DataFrame({"Component":result["loadings"].columns,
                                    "Explained fraction":result["explained_variance_ratio"]})
            st.plotly_chart(px.bar(explained,x="Component",y="Explained fraction",title="Explained sample variance"),use_container_width=True)
            st.dataframe(result["loadings"].round(4),use_container_width=True)
            st.plotly_chart(px.line(result["scores"],title="Training-sample principal component scores"),use_container_width=True)
            st.caption("Descriptive in-sample PCA. Refit on trailing training history for forecasting.")
    except Exception as exc: st.error(str(exc))

with tab2:
    st.subheader("Sample, EWMA, shrinkage, and GARCH volatility")
    up=st.file_uploader("Upload monthly returns CSV (>=60 observations for GARCH)",type="csv",key="vol")
    try:
        values=return_data(up,60)
        if values is not None:
            asset=st.selectbox("Select security",values.columns,key="vol_asset")
            x=values[asset]
            result={
                "Annualized sample":float(x.std(ddof=1)*np.sqrt(12)),
                "Annualized EWMA":float(np.sqrt(ewma_covariance(values[[asset]],0.94,12).iloc[0,0])),
                "Annualized diagonal shrinkage":float(np.sqrt(shrinkage_covariance(values[[asset]],0.25,12).iloc[0,0])),
            }
            garch=fit_garch11(x)
            result["GARCH next-month annualized equivalent"]=float(np.sqrt(garch.next_variance*12))
            st.dataframe(pd.DataFrame([{"Model":k,"Estimated annual volatility":v} for k,v in result.items()]),hide_index=True,use_container_width=True)
            st.plotly_chart(px.bar(x=list(result),y=list(result.values()),
                labels={"x":"Estimator","y":"Annualized estimated volatility"},title="Volatility estimator comparison"),use_container_width=True)
            st.caption("GARCH is fitted in-sample on these returns; no forecast accuracy comparison has been performed.")
    except Exception as exc: st.error(str(exc))

with tab3:
    st.subheader("OLS factor attribution / sensitivity (descriptive)")
    st.write("Upload a date-first CSV with one column called asset and >=1 factor columns. Returns must use decimal units.")
    up=st.file_uploader("Upload asset plus factor return CSV",type="csv",key="reg")
    try:
        values=return_data(up,12)
        if values is not None:
            if "asset" not in values.columns or len(values.columns)<2:
                raise ValueError("CSV requires 'asset' and at least one factor column")
            result=factor_regression(values["asset"],values.drop(columns="asset"))
            st.metric("Model R-squared",f"{result['r_squared']:.3f}")
            st.metric("Alpha per sample period",f"{result['alpha_per_period']:.4%}")
            st.dataframe(pd.DataFrame(list(result["betas"].items()),columns=["Factor","OLS beta"]),hide_index=True,use_container_width=True)
            st.caption("OLS has no robust standard errors in this panel. Do not use as statistical significance evidence.")
    except Exception as exc: st.error(str(exc))

with tab4:
    st.subheader("Ornstein–Uhlenbeck process: hypothetical mean reversion")
    left,right=st.columns(2)
    initial=left.number_input("Initial state",value=3.0)
    target=right.number_input("Long-run mean",value=0.0)
    a,b=st.columns(2)
    theta=a.number_input("Mean-reversion rate",min_value=0.01,value=1.0)
    sigma=b.number_input("Diffusion",min_value=0.0,value=0.2)
    paths=simulate_ou(initial,target,theta,sigma,1/12,120,30,seed=2026)
    plot=pd.DataFrame(paths[:,:10],columns=[f"Path {i+1}" for i in range(10)])
    st.plotly_chart(px.line(plot,labels={"index":"Month","value":"Modeled state"},title="Hypothetical OU paths"),use_container_width=True)
    st.caption("Illustrative model process, not fitted to actual market data or predictive performance.")
