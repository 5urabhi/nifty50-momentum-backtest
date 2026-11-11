"""Local Dhan data onboarding, schema and historical evidence checklist.

Does not request tokens in the browser, persist secrets or place orders.
All API calls are made through the read-only local terminal downloader.
"""
from pathlib import Path
import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dhan Data Connection", layout="wide")
st.title("DhanHQ Historical Data — Local Setup")
st.caption("Read-only market-data retrieval · DhanHQ v2 · Local credentials only")
st.warning("Do not paste an API token into this page. Set DHAN_ACCESS_TOKEN in your local terminal. "
           "Never deploy a token in client-side Vercel code.")

a,b,c=st.columns(3)
a.metric("Dhan token in local environment",
         "Detected" if bool(os.environ.get("DHAN_ACCESS_TOKEN")) else "Not set")
b.metric("Dhan trading/order endpoints","Not used")
c.metric("Price adjustment verification","Required")

st.subheader("1. Account and token")
st.markdown("""Generate an access token from **Dhan Web → Profile → Trading & Data APIs**.
Confirm historical Data API entitlement, then locally set:

```bash
read -rsp "Dhan access token: " DHAN_ACCESS_TOKEN; echo
export DHAN_ACCESS_TOKEN
```

For more instructions, see `docs/DHAN_API_SETUP.md`. The Dhan account login,
OTP/TOTP secrets and trading PIN are **never** needed by this read-only tool.""")

st.subheader("2. Instrument master and mapping")
st.code("python scripts/dhan_data.py instrument-master --output data/dhan/instrument_master.csv",language="bash")
st.code("cp config/dhan_instruments.example.csv data/dhan/instruments.csv",language="bash")
st.write("Replace illustrative Security IDs with reviewed values from the current Dhan instrument master.")
mapping=Path("data/dhan/instruments.csv")
if mapping.exists():
    try:
        from index_research.dhan_data import read_instruments
        ins=read_instruments(mapping)
        st.success(f"{len(ins)} instruments mapped in ignored local data folder.")
        st.dataframe(pd.DataFrame([{"label":i.label,"security_id":i.security_id,
                         "exchange_segment":i.exchange_segment,"instrument":i.instrument}
                        for i in ins]),hide_index=True,use_container_width=True)
    except Exception as exc:
        st.error(f"Instrument mapping invalid: {exc}")
else:
    st.info("No local instrument mapping has been provided yet.")

st.subheader("3. Historical download")
st.code("""python scripts/dhan_data.py download \\
  --instruments data/dhan/instruments.csv \\
  --from-date 2018-01-01 --to-date 2026-11-11 \\
  --output-dir data/dhan/raw""",language="bash")
st.caption("Daily OHLCV, chunked with retries. to-date is exclusive. "
           "For intraday, add --interval 5 (90-day request chunks).")
st.subheader("4. Convert to research input matrix")
st.code("""python scripts/dhan_data.py monthly \\
  --instruments data/dhan/instruments.csv \\
  --raw-dir data/dhan/raw \\
  --output-dir data/dhan/monthly_research""",language="bash")

monthly=Path("data/dhan/monthly_research")
required=["prices.csv","membership.csv","benchmark.csv"]
optional=["fundamentals.csv","sectors.csv","corporate_actions.csv"]
rows=[]
for name in required+optional:
    exists=(monthly/name).exists()
    rows.append({"File":name,"Required for index research":name in required,
                 "Local status":"Present" if exists else "Missing"})
st.subheader("5. Evidence readiness")
st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
if (monthly/"prices.csv").exists():
    st.warning("Dhan-generated prices.csv is raw month-end CLOSE. Adjusted prices, corporate actions, "
               "historic constituents and a genuine compatible benchmark need separate verification.")
if all((monthly/f).exists() for f in required):
    st.success("Required input filenames present. Their historical accuracy and licensing are NOT verified.")
    st.code("python -m index_research.cli run --input-dir data/dhan/monthly_research "
            "--output-dir results/dhan_research --config config/research_momentum.json",language="bash")
else:
    st.info("Running an index research experiment is deliberately blocked until membership.csv "
            "and benchmark.csv are supplied independently.")

st.markdown("""### Source and limitations

Official DhanHQ documentation: [Historical Candles](https://dhanhq.co/docs/v2/historical-data/),
[Authentication](https://dhanhq.co/docs/v2/authentication/),
[Instrument List](https://dhanhq.co/docs/v2/instruments/).

Dhan historical candles alone are **not** point-in-time Nifty constituent history,
corporate-action-adjusted total returns, or publication-dated fundamental data.
The Dhan API page is an onboarding guide; **no token is sent or stored from this UI**.""")
