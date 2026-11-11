"""Research workstation home: summary of the same experiment outputs used by all pages."""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Equity Index Quant Research",page_icon="📈",layout="wide",
                   initial_sidebar_state="expanded")
st.title("Equity Index Quantitative Research")
st.caption("Your personal Python research workstation · Run models, inspect graphs, and generate reproducible evidence")
st.info("Personal quantitative research laboratory—not a company website. Use it to run models, validate methodology, and produce evidence for a research portfolio.")

saved=st.session_state.get("index_research_result")
if not saved:
    st.header("Research framework")
    st.markdown("""Use **Index Research** in the sidebar to run a transparent experiment
with a historical CSV ZIP or a labeled synthetic fixture. Once generated,
its results automatically appear here and in the **Factor Laboratory**,
**Index Comparisons**, and **Research Report** pages.

The mathematical pages explore optimization, volatility forecasting,
statistical inference, stochastic processes and derivatives. They do not
imply validated market performance.""")
    a,b,c=st.columns(3)
    a.metric("Core factor models",5)
    b.metric("Research mode","LOCAL")
    c.metric("Empirical claims","NOT AUDITED")
    st.warning("Legacy optimized returns are unverified; point-in-time constituents and fundamental evidence are required.")
    st.subheader("How to use your research workstation")
    st.markdown("""**1. Run an experiment:** Sidebar → **Index Research** → select
**Synthetic demonstration** (software testing) or upload approved historical
inputs → **Run**.

**2. Inspect your models:** Sidebar → **Advanced Mathematics**,
**Quantitative Models**, **Rolling Validation** and **Visual Validation**.

**3. Compare outputs:** Open **Factor Laboratory**, **Index Comparisons**,
**Risk Attribution**, and **Robustness**.

**4. Save your results:** Open **Research Report** to review and export available
reports, methodology, charts and summary data.

**5. Run the full local suite:** Open another Ubuntu terminal and enter
`bash run.sh evaluate`. The test output, mathematical reports and
clearly labeled synthetic demonstrations are saved under `results/`.

**Important:** Synthetic tests establish software behavior, not real
Nifty performance. Historical results require independently verified data.
""")
    st.caption("Optional animated presentation: bash run.sh web. You do not need Vite or npm to run the Python research lab.")
    st.stop()

meta=saved["metadata"]
if saved.get("demo"):
    st.error("SYNTHETIC demonstration: not actual Nifty or MSCI performance.")
else:
    st.warning("Uploaded datasets have not been independently audited. Findings are exploratory.")
frame=saved["data"].copy()
nav=(1+frame[["strategy","benchmark"]]).cumprod()
nav.columns=["Research index","Supplied benchmark"]
views=meta.get("metrics_by_split",{})
name=next(reversed(views))
metrics=views[name]
st.caption("Metrics shown for latest configured evaluation segment: "+name.replace("_"," ").title())
a,b,c,d=st.columns(4)
def percent(value):
    return f"{value:.2%}" if isinstance(value,(float,int)) else "N/A"
a.metric("Strategy CAGR",percent(metrics.get("strategy_cagr")))
b.metric("Benchmark CAGR",percent(metrics.get("benchmark_cagr")))
c.metric("Tracking Error",percent(metrics.get("tracking_error")))
d.metric("Information Ratio",f"{metrics['information_ratio']:.2f}" if isinstance(metrics.get("information_ratio"),(float,int)) else "N/A")
st.plotly_chart(px.line(nav,title="Cumulative wealth: research index vs comparison benchmark",
                        labels={"index":"Holding period end","value":"Growth of 1","variable":"Series"}),
                use_container_width=True)
left,right=st.columns(2)
with left:
    st.subheader("Portfolio risk")
    roll=saved.get("rolling")
    if roll is not None:
        st.plotly_chart(px.line(roll[["rolling_tracking_error","rolling_volatility"]],
                                title="Rolling active and absolute risk"),use_container_width=True)
with right:
    st.subheader("Concentration")
    conc=saved.get("concentration")
    if conc is not None:
        st.plotly_chart(px.line(conc[["hhi","largest_weight"]],
                                title="HHI and largest stock allocation"),use_container_width=True)
st.subheader("Research governance")
st.json({"experiment":meta["config"]["name"],
         "dataset_status":meta["config"]["dataset_status"],
         "first_observation":meta["first_price_date"],
         "last_observation":meta["last_price_date"],
         "coverage":meta["coverage"],
         "limitations":meta["limitations"]})
st.caption("All charts derive from the active experiment in this Streamlit session. The page contains no hardcoded historical performance.")
