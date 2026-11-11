"""Local rolling model evaluation using uploaded non-synthetic return histories."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from index_research.model_validation import (
    rolling_volatility_forecasts,variance_forecast_scores,
    rolling_covariance_portfolios
)

st.set_page_config(page_title="Out-of-Sample Model Diagnostics",layout="wide")
st.title("Out-of-Sample Model Diagnostics")
st.caption("Rolling covariance and volatility comparisons; input data never uploaded to a hosted service by this code")
st.warning("These are exploratory risk-estimator comparisons, NOT investable portfolio backtests. "
           "No transaction costs, delisting treatment, or benchmark methodology are modeled in this page.")

upload=st.file_uploader("Monthly decimal simple returns: date + >=2 security columns",type="csv")
if upload is None:
    st.info("Supply a CSV to calculate leakage-aware rolling model diagnostics. "
            "There are no prefilled performance numbers.")
    st.stop()
try:
    data=pd.read_csv(upload)
    if len(data.columns)<3:
        raise ValueError("date and at least two security columns required")
    dates=pd.to_datetime(data.iloc[:,0],errors="raise")
    if dates.duplicated().any() or dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("ordered, unique and valid dates required")
    x=data.iloc[:,1:].apply(pd.to_numeric,errors="raise")
    x.index=pd.DatetimeIndex(dates)
    if len(x)<48 or x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError("at least 48 fully observed rows required")
    if len(x.columns)>30:
        raise ValueError("this interactive model comparison is limited to 30 securities")
    window=st.slider("Train window (months)",min_value=24,max_value=len(x)-12,
                      value=min(36,len(x)-12))
    decay=st.slider("EWMA decay",min_value=.50,max_value=.99,value=.94,step=.01)
    shrinkage=st.slider("Covariance diagonal shrinkage",min_value=0.0,
                         max_value=1.0,value=.25,step=.05)
    tab1,tab2=st.tabs(["Volatility forecast diagnostics","Portfolio covariance comparison"])
    with tab1:
        security=st.selectbox("Security",list(x.columns))
        forecasts=rolling_volatility_forecasts(x[security],train_window=window,
                                               ewma_decay=decay)
        scores=variance_forecast_scores(forecasts)
        st.dataframe(scores,hide_index=True,use_container_width=True)
        display=forecasts[["sample_variance_forecast","ewma_variance_forecast",
                            "realized_variance"]].rename(columns={
            "sample_variance_forecast":"Historical sample",
            "ewma_variance_forecast":"EWMA",
            "realized_variance":"Squared realized return (noisy)"})
        st.plotly_chart(px.line(display,title="Strictly prior-history variance forecast vs observed squared return"),use_container_width=True)
        st.caption("Lower holdout QLIKE and squared error are better under their respective losses. "
                   "Squared realized returns are noisy variance proxies.")
    with tab2:
        cap=max(1/len(x.columns),.25)
        models=rolling_covariance_portfolios(
            x,train_window=window,rebalance_every=3,
            max_weight=cap,shrinkage_intensity=shrinkage,ewma_decay=decay)
        net_columns=[name for name in models.columns if not name.endswith(("_turnover","_gross"))]
        net_models=models[net_columns]
        wealth=(1+net_models).cumprod()
        st.plotly_chart(px.line(wealth,title="Frictionless rolling covariance portfolio wealth (illustrative)",
                      labels={"value":"Wealth multiple","index":"Date"}),use_container_width=True)
        summary=pd.DataFrame({
            "model":net_columns,
            "monthly_mean":[float(net_models[c].mean()) for c in net_columns],
            "monthly_volatility":[float(net_models[c].std(ddof=1)) for c in net_columns],
            "annualized_turnover":[float(models[f"{c}_turnover"].mean()*12) for c in net_columns],
            "holdout_observations":[len(models)]*len(net_columns),
        })
        st.dataframe(summary,hide_index=True,use_container_width=True)
        st.caption("Drift-aware turnover is included; sector caps, full market-impact costs and official benchmark are absent; "
                   "these curves are diagnostic, not evidence of an investable index.")
except Exception as exc:
    st.error(f"Model validation blocked: {exc}")
