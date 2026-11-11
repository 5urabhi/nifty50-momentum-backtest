"""Interactive Visual Validation Lab — 2D and 3D mathematical verification.

All default data are mathematical fixtures, not market returns. PASS means
specified numerical identity/tolerance holds, not that finance research is
historically validated. The page never fabricates external model performance.
"""
import io
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from index_research.visual_validation import (
    option_price_surface, portfolio_risk_surface, option_convergence,
    identity_checks, gbm_moments, validation_table,
    three_asset_covariance, risk_contribution_test
)
from index_research.portfolio_theory import optimize_portfolio
from index_research.model_validation import rolling_volatility_forecasts, variance_forecast_scores

st.set_page_config(page_title="Visual Validation Laboratory", layout="wide")
st.title("Visual Validation Laboratory")
st.caption("Mathematical assertions → calculated 2D diagnostics → interactive 3D model surfaces")
st.warning("DETERMINISTIC MATHEMATICAL FIXTURES / THEORETICAL MODELS. "
           "A PASS is a numerical check, not proof of historical investment returns.")
st.markdown("**Navigation:** Choose a model to examine the equation, its numerical check, "
            "interactive plots and downloadable evidence. Rotate or zoom the 3D plots with your mouse.")

with st.sidebar:
    st.header("Visual validation controls")
    spot=st.number_input("Underlying price",min_value=1.,value=100.,step=5.)
    strike=st.number_input("Strike",min_value=1.,value=100.,step=5.)
    vol=st.slider("Annualized volatility",.05,.80,.20,.01)
    rate=st.slider("Continuously compounded rate",-.02,.15,.04,.005)
    maturity=st.slider("Years to expiry",.10,3.,1.,.10)
    opt=st.selectbox("European option type",["call","put"])
    show_grid=st.toggle("Show 3D axes and color scale",value=True)

def theme(fig, title, *, height=480, scene=False):
    fig.update_layout(title=title,template="plotly_dark",
        paper_bgcolor="#0b1424",plot_bgcolor="#121f33",
        font=dict(family="Arial",color="#dfebf8"),
        height=height,margin=dict(l=25,r=25,t=65,b=25))
    if scene:
        fig.update_layout(scene=dict(
            bgcolor="#121f33",
            xaxis=dict(showbackground=show_grid),
            yaxis=dict(showbackground=show_grid),
            zaxis=dict(showbackground=show_grid),
            aspectmode="cube"))
    return fig

def show_checks(checks):
    checks_df=validation_table(checks)
    successful=sum(c.passed for c in checks)
    total=len(checks)
    col1,col2,col3=st.columns(3)
    col1.metric("Mathematical checks",total)
    col2.metric("Within tolerance",successful)
    col3.metric("Outside tolerance",total-successful)
    st.dataframe(checks_df,hide_index=True,use_container_width=True)
    st.caption("Assertion tolerances refer to numerical precision or sampling error. "
               "They are not calibrated confidence in a financial strategy.")
    return checks_df

def download_chart(fig,filename):
    html=fig.to_html(full_html=True,include_plotlyjs=True)
    st.download_button("Export interactive chart (HTML)",
                       html,file_name=filename,mime="text/html")

all_checks=[]
tabs=st.tabs([
    "2D · Convergence",
    "3D · Option surfaces",
    "3D · Portfolio risk",
    "2D · Stochastic moments",
    "2D · Risk contributions",
    "2D · Real-data forecast tests",
    "Evidence & limitations",
])

with tabs[0]:
    st.subheader("Option-pricing convergence")
    st.markdown("**Hypothesis:** A European CRR tree and seeded antithetic Monte Carlo "
                "price converge toward analytical Black–Scholes–Merton.")
    frame,checks=option_convergence(
        spot=spot,strike=strike,years=maturity,rate=rate,vol=vol,option=opt)
    all_checks.extend(checks)
    checks_df=show_checks(checks)
    fig=go.Figure()
    for name,part in frame.groupby("method",sort=False):
        fig.add_trace(go.Scatter(x=part["budget"],y=part["absolute_error"],
                                 mode="lines+markers",name=name,
                                 hovertemplate="Budget %{x}<br>Absolute error %{y:.5f}<extra>%{fullData.name}</extra>"))
    fig.update_xaxes(title="Lattice steps / simulated paths (method-specific)")
    fig.update_yaxes(title="Absolute pricing error",rangemode="tozero")
    theme(fig,"Numerical convergence to BSM — different computational budgets")
    st.plotly_chart(fig,use_container_width=True)
    st.caption("The x-axis combines different computational units for compact inspection; "
               "do not interpret equal values as equal computational cost.")
    download_chart(fig,"pricing_convergence_2d.html")
    st.download_button("Export convergence table (CSV)",frame.to_csv(index=False),
                       file_name="pricing_convergence.csv",mime="text/csv")

with tabs[1]:
    st.subheader("3D European option-price and Greeks surfaces")
    st.markdown("**Axes:** strike × assumed annual volatility × theoretical option price. "
                "Values are computed from Black–Scholes, not observed option quotes.")
    df=option_price_surface(option=opt,spot=spot,rate=rate,
                            maturity=maturity)
    strikes=np.sort(df.strike.unique())
    vols=np.sort(df.volatility.unique())
    surface=df.pivot(index="volatility",columns="strike",values="price").reindex(
        index=vols,columns=strikes)
    surface_kind=st.radio("Surface z-axis",["price","delta","vega"],horizontal=True)
    z=df.pivot(index="volatility",columns="strike",values=surface_kind).reindex(
        index=vols,columns=strikes).to_numpy()
    fig=go.Figure(data=[go.Surface(x=strikes,y=vols,z=z,
                   colorscale="Viridis",colorbar=dict(title=surface_kind.title()),
                   hovertemplate="Strike %{x:.1f}<br>Vol %{y:.1%}<br>Value %{z:.4f}<extra></extra>")])
    fig.update_layout(scene=dict(
        xaxis_title="Strike",yaxis_title="Volatility",
        zaxis_title=surface_kind.capitalize()))
    theme(fig,f"{surface_kind.capitalize()} surface | European {opt}",height=640,scene=True)
    st.plotly_chart(fig,use_container_width=True)
    download_chart(fig,f"option_{surface_kind}_surface_3d.html")
    left,right=st.columns(2)
    with left:
        slice_strike=st.select_slider("Volatility slice: fixed strike",options=list(strikes),
                                      value=strikes[len(strikes)//2])
        curve=df[np.isclose(df.strike,slice_strike)]
        slice_fig=px.line(curve,x="volatility",y=surface_kind,
                          title=f"{surface_kind.capitalize()} versus volatility")
        st.plotly_chart(theme(slice_fig,"2D slice of the 3D surface",height=360),
                        use_container_width=True)
    with right:
        st.markdown("**Analytic checks:** put-call parity and call-put delta parity.")
        parity=identity_checks(spot,strike,maturity,rate,vol)
        all_checks.extend(parity)
        show_checks(parity)

with tabs[2]:
    st.subheader("3D risk landscape for a three-asset portfolio")
    st.markdown("Weights satisfy **w₁ + w₂ + w₃ = 1**, with no shorting. "
                "The z-axis is annualized portfolio volatility calculated from an "
                "explicitly illustrative covariance matrix.")
    cov=three_asset_covariance()
    resolution=st.slider("Surface mesh resolution",15,65,35,5)
    landscape=portfolio_risk_surface(cov,resolution=resolution)
    # The triangular simplex is represented as a 3D scatter mesh rather than
    # pretending the w1+w2>1 region is feasible.
    fig=go.Figure()
    fig.add_trace(go.Scatter3d(
        x=landscape["weight_1"],y=landscape["weight_2"],
        z=landscape["annual_volatility"],
        mode="markers",name="Feasible portfolios",
        marker=dict(size=3.2,color=landscape["annual_volatility"],
                    colorscale="Viridis",showscale=True,
                    colorbar=dict(title="Volatility")),
        customdata=landscape[["weight_3"]].to_numpy(),
        hovertemplate="Asset A %{x:.1%}<br>Asset B %{y:.1%}<br>Asset C %{customdata[0]:.1%}<br>Volatility %{z:.2%}<extra></extra>"
    ))
    optimum=optimize_portfolio(cov,objective="minimum_variance")
    w=optimum.weights
    fig.add_trace(go.Scatter3d(
        x=[w.iloc[0]],y=[w.iloc[1]],z=[optimum.volatility],
        mode="markers",name="Minimum variance",
        marker=dict(size=9,color="#ffce63",symbol="diamond")))
    fig.update_layout(scene=dict(xaxis_title="Asset A weight",
                                 yaxis_title="Asset B weight",
                                 zaxis_title="Annualized portfolio volatility"))
    theme(fig,"3D feasible portfolio risk simplex (illustrative)",height=640,scene=True)
    st.plotly_chart(fig,use_container_width=True)
    download_chart(fig,"portfolio_risk_landscape_3d.html")
    st.dataframe(w.rename("Minimum-variance weights").to_frame(),use_container_width=True)
    st.info("The 3D geometry is a mathematical feasible-region visualization. "
            "The covariance inputs are illustrative, and the optimum is not an investment recommendation.")

with tabs[3]:
    st.subheader("Geometric Brownian Motion: analytical versus simulated mean")
    path_count=st.slider("Simulated independent paths",1000,12000,6000,1000)
    data,checks=gbm_moments(spot=spot,mu=.05,sigma=vol,
                             years=maturity,steps=60,paths=path_count)
    all_checks.extend(checks)
    show_checks(checks)
    fig=go.Figure()
    fig.add_trace(go.Scatter(
        x=data["year"],y=data["p95"],mode="lines",
        line=dict(width=0),showlegend=False,hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=data["year"],y=data["p05"],mode="lines",fill="tonexty",
        fillcolor="rgba(98,201,216,.20)",line=dict(width=0),
        name="5th–95th percentile band"))
    fig.add_trace(go.Scatter(x=data["year"],y=data["analytical_mean"],
        mode="lines",name="Analytical mean",line=dict(width=3)))
    fig.add_trace(go.Scatter(x=data["year"],y=data["simulated_mean"],
        mode="lines",name="Simulated mean",line=dict(dash="dash",width=2)))
    fig.update_xaxes(title="Elapsed years")
    fig.update_yaxes(title="Illustrative asset price")
    theme(fig,"GBM distribution fan and moment convergence")
    st.plotly_chart(fig,use_container_width=True)
    download_chart(fig,"gbm_moment_validation_2d.html")

with tabs[4]:
    st.subheader("Euler portfolio volatility decomposition")
    components,checks=risk_contribution_test()
    all_checks.extend(checks)
    show_checks(checks)
    fig=px.bar(components.reset_index(names="Asset"),x="Asset",
               y="volatility_contribution",color="Asset",
               title="Component contributions sum to total volatility")
    st.plotly_chart(theme(fig,"Portfolio volatility contributions",height=420),
                    use_container_width=True)
    download_chart(fig,"risk_contributions_2d.html")
    st.caption("The covariance and weights are mathematical fixtures; the chart verifies a decomposition identity.")

with tabs[5]:
    st.subheader("Forecast diagnostics on uploaded historical returns")
    st.write("Optional CSV: date column and a single numeric decimal-return column. "
             "The forecast for each period uses strictly earlier observations.")
    upload=st.file_uploader("Upload monthly return CSV",type="csv",key="forecast_csv")
    if upload is None:
        st.info("No market forecasts are displayed without uploaded data.")
    else:
        try:
            frame=pd.read_csv(upload)
            if frame.shape[1]!=2:
                raise ValueError("CSV must have date + one return column")
            dates=pd.to_datetime(frame.iloc[:,0],errors="raise")
            returns=pd.Series(pd.to_numeric(frame.iloc[:,1],errors="raise").to_numpy(),
                              index=pd.DatetimeIndex(dates))
            if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
                raise ValueError("Dates must be unique, increasing and valid")
            if not np.isfinite(returns.to_numpy()).all() or len(returns)<36:
                raise ValueError("At least 36 finite monthly returns required")
            window=st.slider("Train months",24,len(returns)-12,min(36,len(returns)-12))
            forecasts=rolling_volatility_forecasts(returns,train_window=window)
            scores=variance_forecast_scores(forecasts)
            st.dataframe(scores,hide_index=True,use_container_width=True)
            fig=px.line(forecasts[["realized_variance","sample_variance_forecast",
                                  "ewma_variance_forecast"]],
                        title="One-step rolling variance forecast versus realized-return proxy")
            st.plotly_chart(theme(fig,"Out-of-sample variance diagnostics",height=470),
                            use_container_width=True)
            download_chart(fig,"forecast_validation_2d.html")
            st.caption("Realized squared residuals are noisy variance proxies. Lower QLIKE/MSE "
                       "does not establish asset-pricing or trading advantage.")
        except Exception as exc:
            st.error(f"Forecast input or calculation failed: {exc}")

with tabs[6]:
    st.subheader("Evidence, scope and reproducibility")
    st.markdown("""**Numerical assertions** verify specific properties: option-parity
identities, convergence checks, stochastic means, and Euler risk decomposition.
**Visual diagnostics** help find patterns and discrepancies, but do not replace
assertions. **Financial validation** requires real point-in-time security
histories, complete corporate actions, licensed benchmark data and an
untouched evaluation period.""")
    report=validation_table(all_checks)
    st.dataframe(report,hide_index=True,use_container_width=True)
    st.download_button("Download numerical-check results (CSV)",report.to_csv(index=False),
                       file_name="visual_math_checks.csv",mime="text/csv")
    st.info("The checks shown here are the checks calculated in tabs visited during "
            "this Streamlit rerun. To produce a full independent test report, run "
            "the local test suite and the optional visual-evidence exporter.")
