"""Local math lab: additional quantitative models without fabricated market evidence."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from index_research.portfolio_theory import (
    optimize_portfolio,risk_parity,maximum_diversification,
    risk_contributions,efficient_frontier
)
from index_research.portfolio_extensions import (
    black_litterman_posterior,minimize_historical_cvar
)
from index_research.statistical_inference import (
    newey_west_ols,moving_block_bootstrap_mean,benjamini_hochberg
)
from index_research.tail_risk import (
    gaussian_var_es,student_t_var_es,portfolio_monte_carlo_risk
)
from index_research.derivatives import (
    implied_volatility,binomial_option,monte_carlo_european
)
from index_research.math_models import black_scholes

st.set_page_config(page_title="Advanced Quantitative Mathematics",layout="wide")
st.title("Advanced Quantitative Mathematics")
st.caption("Index optimization · tail risk · academic factor inference · derivatives")
st.warning("All outputs are exploratory. No empirical excess-return or investability claims are made.")

def matrix_csv(upload, minimum=30):
    if upload is None:return None
    frame=pd.read_csv(upload)
    if frame.shape[1]<3:raise ValueError("CSV requires date and >=2 asset columns")
    date=pd.to_datetime(frame.iloc[:,0],errors="raise")
    if date.isna().any() or date.duplicated().any() or not date.is_monotonic_increasing:
        raise ValueError("valid ascending unique dates required")
    x=frame.iloc[:,1:].apply(pd.to_numeric,errors="raise")
    x.index=pd.DatetimeIndex(date)
    if len(x)<minimum or x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError(f">={minimum} fully observed finite rows required")
    return x

def research_session_returns(minimum=30):
    source=st.session_state.get("index_research_result")
    if not source or "research_inputs" not in source:
        raise ValueError("Run Index Research first to activate a dataset.")
    prices=source["research_inputs"]["prices"]
    rets=prices.pct_change(fill_method=None).iloc[1:].dropna(axis=0,how="any")
    if len(rets)<minimum:
        raise ValueError(f"Active research data have only {len(rets)} complete return dates; need {minimum}. Upload a separate valid CSV.")
    return rets

t1,t2,t3,t4=st.tabs(["Portfolio Theory","Tail Risk","Statistical Inference","Option Pricing"])

with t1:
    st.subheader("Markowitz, risk parity, diversification and tracking-error optimization")
    active_option=st.toggle("Use active Index Research dataset",value=False,
                                help="Applies to the current research session and does not assert that data are audited.")
    up=st.file_uploader("Or upload historical monthly asset returns",type="csv",key="port",
                        disabled=active_option)
    try:
        frame=research_session_returns() if active_option else matrix_csv(up)
        if frame is not None:
            if len(frame.columns)>70:raise ValueError("Interactive optimizer limited to 70 assets")
            n=len(frame.columns)
            est_mu=frame.mean()*12
            cov=frame.cov()*12
            method=st.selectbox("Portfolio method",[
                "Minimum variance","Risk parity","Maximum diversification",
                "Mean-variance utility","Minimum tracking error","Active utility"
            ])
            cap=st.slider("Maximum asset allocation",min_value=1/n,max_value=1.0,value=1.0)
            market=pd.Series(np.full(n,1/n),index=frame.columns,name="equal_weight_benchmark")
            if method=="Risk parity":
                sol=risk_parity(cov,max_weight=cap)
            elif method=="Maximum diversification":
                sol=maximum_diversification(cov,max_weight=cap)
            else:
                names={
                    "Minimum variance":"minimum_variance",
                    "Mean-variance utility":"mean_variance",
                    "Minimum tracking error":"minimum_tracking_error",
                    "Active utility":"active_utility",
                }
                sol=optimize_portfolio(
                    cov,est_mu,benchmark=market,objective=names[method],
                    max_weight=cap,risk_aversion=3.0)
            weights=sol.weights
            st.write("**Ex-ante estimated quantities (IN SAMPLE)**")
            a,b,c=st.columns(3)
            a.metric("Annualized volatility",f"{sol.volatility:.2%}")
            b.metric("Annualized sample expected return",f"{sol.expected_return:.2%}")
            c.metric("HHI",f"{sol.concentration_hhi:.4f}")
            st.plotly_chart(px.bar(x=weights.index,y=weights.to_numpy(),
                         labels={"x":"Security","y":"Weight"},title="Optimized weights"),
                         use_container_width=True)
            st.plotly_chart(px.bar(risk_contributions(weights,cov),
                         y="volatility_contribution",title="Volatility contribution by asset"),
                         use_container_width=True)
            if n<=25:
                frontier=efficient_frontier(cov,est_mu,points=15,max_weight=cap)
                st.plotly_chart(px.line(frontier.dropna(),
                             x="estimated_volatility",y="estimated_return",
                             markers=True,title="Ex-ante constrained efficient frontier"),
                             use_container_width=True)
            st.caption("Expected returns and covariance are estimated on the uploaded sample. A separate forward holdout is necessary.")

            with st.expander("Black–Litterman example (user-defined subjective view)"):
                lhs=st.selectbox("Asset expected to outperform",list(frame.columns),key="view_up")
                rhs=st.selectbox("Asset expected to underperform",list(frame.columns),index=min(1,n-1),key="view_down")
                view=st.number_input("Subjective annual return difference",value=0.02,step=0.005)
                if lhs!=rhs:
                    P=pd.DataFrame(0.,index=["relative_view"],columns=frame.columns)
                    P.loc["relative_view",lhs]=1
                    P.loc["relative_view",rhs]=-1
                    posterior=black_litterman_posterior(cov,market,2.5,P,
                        pd.Series([view],index=P.index))
                    st.dataframe(pd.DataFrame({
                        "Implied equilibrium return":posterior["equilibrium_returns"],
                        "Posterior expected return":posterior["posterior_expected_returns"]
                    }),use_container_width=True)
                else:st.info("Choose distinct securities for the relative view.")

            with st.expander("Historical CVaR constrained optimizer"):
                try:
                    tail=minimize_historical_cvar(frame,confidence=.95,max_weight=cap)
                    st.metric("Scenario-optimized CVaR loss",f"{tail['optimization_objective_cvar']:.2%}")
                    st.dataframe(tail["weights"].rename("weight").to_frame())
                    st.caption("This optimization is in-sample and extremely sensitive to scenario representativeness.")
                except Exception as exc:st.error(str(exc))
    except Exception as exc:st.error(f"Input/model error: {exc}")

with t2:
    st.subheader("Gaussian, Student-t, and portfolio Monte Carlo tail-risk estimates")
    mean=st.number_input("Assumed monthly mean return",value=.005,step=.005)
    vol=st.number_input("Assumed monthly volatility",min_value=.0001,value=.04,step=.005)
    conf=st.slider("Loss confidence",.80,.99,.95,.01)
    df=st.slider("Student-t degrees of freedom",min_value=2.01,max_value=30.0,value=6.0)
    gauss=gaussian_var_es(mean,vol,conf)
    # Convert Student-t *standard deviation* to its scale so comparisons use
    # the same intended portfolio monthly volatility when df>2.
    tscale=vol*np.sqrt((df-2)/df)
    student=student_t_var_es(mean,tscale,df,conf)
    compare=pd.DataFrame([
        {"Assumption":"Gaussian","VaR":gauss["var"],"ES":gauss["expected_shortfall"]},
        {"Assumption":"Student-t","VaR":student["var"],"ES":student["expected_shortfall"]},
    ])
    st.dataframe(compare,use_container_width=True,hide_index=True)
    st.plotly_chart(px.bar(compare,x="Assumption",y=["VaR","ES"],barmode="group",
                        title="Model-based one-month loss estimates"),use_container_width=True)
    st.caption("These are hypothetical parametrically assumed return distributions. The tail-risk functions accept signed losses, which can produce negative VaR if expected returns dominate risk.")

with t3:
    st.subheader("Newey–West HAC factor regression and block bootstrap")
    st.write("Upload a date-first CSV with dependent asset excess return in the column `asset` and remaining columns as factor returns.")
    up=st.file_uploader("Upload academic factor-return data",type="csv",key="stats")
    try:
        frame=matrix_csv(up,minimum=30)
        if frame is not None:
            if "asset" not in frame.columns:raise ValueError("CSV needs an 'asset' dependent variable column")
            x=frame.drop(columns="asset")
            lags=st.slider("HAC lag length",0,min(24,len(frame)-1),3)
            est=newey_west_ols(frame["asset"],x,lags)
            coeff=pd.DataFrame({
                "Coefficient":est.coefficients,
                "HAC standard error":est.standard_errors,
                "Normal-approx p-value":est.p_values_normal_approx,
            })
            st.dataframe(coeff,use_container_width=True)
            if len(est.p_values_normal_approx)>1:
                q=benjamini_hochberg(est.p_values_normal_approx.fillna(1))
                st.dataframe(q.rename("Exploratory BH q value"))
            boot=moving_block_bootstrap_mean(frame["asset"],block_length=min(6,len(frame)),
                                              resamples=500,seed=2026)
            st.json(boot)
            st.caption("Factor returns and asset excess returns must have identical definitions and vintages. Asymptotic p-values and BH q-values do not correct for all model selection.")
    except Exception as exc:st.error(str(exc))

with t4:
    st.subheader("Black–Scholes, implied volatility, binomial pricing and Monte Carlo")
    a,b,c=st.columns(3)
    spot=a.number_input("Spot price",min_value=.01,value=100.0)
    strike=b.number_input("Strike price",min_value=.01,value=100.0)
    maturity=c.number_input("Time to expiry (years)",min_value=.01,value=1.0)
    d,e,f=st.columns(3)
    rate=d.number_input("Continuously compounded rate",value=.05)
    sigma=e.number_input("Annual volatility",min_value=.0001,value=.2)
    q=f.number_input("Continuous dividend yield",value=0.)
    option=st.radio("Call or put",["call","put"],horizontal=True)
    analytical=black_scholes(spot,strike,maturity,rate,sigma,option,q)
    tree=binomial_option(spot,strike,maturity,rate,sigma,steps=300,option=option,
                         exercise="american",dividend_yield=q)
    numerical=monte_carlo_european(spot,strike,maturity,rate,sigma,paths=20000,
                                    option=option,dividend_yield=q)
    recovered=implied_volatility(analytical["price"],spot,strike,maturity,rate,
                                 option,dividend_yield=q)
    st.dataframe(pd.DataFrame([
        {"Method":"Black–Scholes European","Price":analytical["price"]},
        {"Method":"CRR American tree","Price":tree},
        {"Method":"Antithetic Monte Carlo European","Price":numerical["price"]},
    ]),hide_index=True,use_container_width=True)
    st.metric("Recovered implied volatility",f"{recovered:.4%}")
    st.write("Antithetic MC 95% normal-approx confidence interval:",
              round(numerical["ci95_lower"],4),round(numerical["ci95_upper"],4))
    st.caption("CRR American and Black–Scholes European prices may differ due to early exercise. This is a numerical math demonstration, not trading advice.")
