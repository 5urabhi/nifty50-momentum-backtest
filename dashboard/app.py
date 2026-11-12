"""Research workstation home: summary of the same experiment outputs used by all pages."""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Equity Index Quant Research",page_icon="📈",layout="wide",
                   initial_sidebar_state="expanded")
# Ensure project packages resolve when Streamlit runs a page by file path.
import sys
from pathlib import Path as _ProjectPath
_PROJECT_ROOT = str(_ProjectPath(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dashboard.workstation_nav import show_workflow_nav
show_workflow_nav()
st.title("Equity Index Quantitative Research")
st.caption("YOUR LOCAL WORKSTATION · Data → Experiments → Mathematical models → Evidence")
st.markdown("## Research workflow")
st.write("All modules are connected through the left navigation and the active experiment in this session. Start anywhere, or follow the numbered stages below.")
stages=st.tabs(["① Data", "② Run Experiments", "③ Explore Models", "④ Validate", "⑤ Reports"])
with stages[0]:
    st.subheader("Collect and inspect Dhan market history")
    st.page_link("dashboard/pages/12_Dhan_Data_Setup.py",label="Open Dhan Historical Data Manager",icon="📥")
    st.page_link("dashboard/pages/13_Empirical_Readiness.py",label="Check historical evidence readiness",icon="🧾")
    st.caption("Master → symbol search → verified security ID mapping → download → charts → monthly inputs. No terminal downloader required.")
with stages[1]:
    st.subheader("Construct and run your index strategy")
    st.page_link("dashboard/pages/1_Index_Research.py",label="Open Index Research",icon="📈")
    st.page_link("dashboard/pages/6_Factor_Laboratory.py",label="Factor Laboratory",icon="🧮")
    st.page_link("dashboard/pages/7_Index_Comparisons.py",label="Index Comparisons",icon="⚖️")
    st.caption("Choose a local dataset or labeled synthetic fixture, configure models, and run. Outputs are shared across analysis pages.")
with stages[2]:
    st.subheader("Run mathematical and statistical models")
    for link,label,icon in [
        ("dashboard/pages/3_Advanced_Mathematics.py","Portfolio optimization · statistical inference","📐"),
        ("dashboard/pages/5_Quantitative_Models.py","Stochastic processes · options","🔬"),
        ("dashboard/pages/2_Model_Comparison.py","PCA, GARCH and model comparison","📊")]:
        st.page_link(link,label=label,icon=icon)
with stages[3]:
    st.subheader("Check robustness and model assumptions")
    for link,label,icon in [
        ("dashboard/pages/4_Rolling_Validation.py","Out-of-sample model diagnostics","⏱️"),
        ("dashboard/pages/10_Visual_Validation.py","2D / 3D mathematical validation","🌀"),
        ("dashboard/pages/9_Risk_Attribution.py","Portfolio risk attribution","🎯"),
        ("dashboard/pages/9_Robustness.py","Robustness and audit","🛡️")]:
        st.page_link(link,label=label,icon=icon)
with stages[4]:
    st.subheader("Review evidence and export your research")
    st.page_link("dashboard/pages/8_Research_Report.py",label="Research Report and downloads",icon="📑")
    st.page_link("dashboard/pages/11_Run_History.py",label="View previous saved experiments",icon="🗂️")
    st.markdown("For full local test reports, run `bash run.sh evaluate` in another terminal. The generated reports are saved under `results/`.")
    st.warning("Synthetic and unverified market results are NOT résumé-ready performance claims.")

st.divider()
st.subheader("Workspace status")
selected=st.session_state.get("research_input_dir")
current=st.session_state.get("index_research_result")
h1,h2,h3=st.columns(3)
h1.metric("Selected data folder", Path(selected).name if selected else "None")
h2.metric("Active experiment", "Synthetic" if current and current.get("demo") else ("Unverified" if current else "None"))
h3.metric("Local Dhan daily files", len(list((Path(__file__).resolve().parents[1]/"data"/"dhan"/"raw").glob("**/*_daily.csv"))))
if selected:
    st.info("Selected folder: "+str(selected)+" · Evidence must be reviewed before market claims.")
if current:
    st.success("An experiment is active. Factor Laboratory, Index Comparisons, Risk Attribution, Robustness and Research Report can use the current session results.")




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
