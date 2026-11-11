"""Local DhanHQ data workspace: instrument mapping, downloads and research handoff.

Never renders credentials or sends them to a browser. All downloads run from
the locally launched Python process through the existing read-only adapter.
"""
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.workstation_nav import show_workflow_nav

from index_research.dhan_data import (
    MASTER_URL, Instrument, read_instruments, download_candles,
    save_download, build_monthly_close,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "dhan"
MASTER = DATA / "instrument_master.csv"
MAPPING = DATA / "instruments.csv"
RAW = DATA / "raw"
MONTHLY = DATA / "monthly_research"
DATA.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Dhan Historical Data | Research Workstation", page_icon="📊", layout="wide")
show_workflow_nav()
st.title("Dhan Historical Data")
st.caption("Local read-only data manager · instrument discovery → mapping → candles → charts → research inputs")
st.warning("The download tool is READ-ONLY and does not submit orders. Keep your Dhan token in the ignored local .env file, never in this browser.")
token = os.environ.get("DHAN_ACCESS_TOKEN", "").strip()
connected = bool(token and token != "PASTE_YOUR_DHAN_ACCESS_TOKEN_HERE")
mapped = []
mapping_error = ""
if MAPPING.exists():
    try:
        mapped = read_instruments(MAPPING)
    except (ValueError, OSError) as exc:
        mapping_error = str(exc)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Token", "Configured" if connected else "Missing")
c2.metric("Master", "Available" if MASTER.exists() else "Missing")
c3.metric("Mapped instruments", len(mapped))
c4.metric("Raw daily files", len(list(RAW.glob("*_daily.csv"))) if RAW.exists() else 0)

st.info("Your Dhan candles become a PRICE-DATA SOURCE—not a complete backtest dataset. They do not supply audited historical Nifty memberships, dividend-reinvested returns, publication-dated fundamentals, or a compatible TRI benchmark.")
tabs = st.tabs([
    "1 · Connection & master",
    "2 · Find instruments",
    "3 · Watchlist mapping",
    "4 · Download history",
    "5 · Explore candles",
    "6 · Prepare for models",
])

with tabs[0]:
    st.subheader("Local API connection")
    st.write("API token is read on the local machine from the repository's ignored `.env`. The UI displays its presence only.")
    if not connected:
        st.error("Dhan access token missing. In another terminal: `nano .env` and set `DHAN_ACCESS_TOKEN=...`, then restart this dashboard.")
    else:
        st.success("Token detected locally. No token content is displayed or saved in a report.")
    st.markdown("**Step 1:** Download the official Dhan instrument master (no API token required).")
    if MASTER.exists():
        st.caption(f"Cached instrument master: {MASTER.name} · {MASTER.stat().st_size / 1024**2:.1f} MiB · local cache")
    if st.button("Download / refresh instrument master", type="primary", key="master_download"):
        try:
            maximum_bytes = 120 * 1024 * 1024
            with st.spinner("Downloading Dhan instrument list..."):
                request = Request(MASTER_URL, headers={"User-Agent":"LocalQuantResearch/1.0"})
                with urlopen(request, timeout=60) as response:
                    content = response.read(maximum_bytes + 1)
                if not content or len(content) > maximum_bytes:
                    raise ValueError("Master file empty or larger than 120 MiB")
                if b"," not in content[:4096] or b"\n" not in content[:4096]:
                    raise ValueError("Downloaded file does not resemble a CSV")
                import tempfile
                with tempfile.NamedTemporaryFile(dir=DATA, suffix=".csv", delete=False) as tmp:
                    tmp.write(content)
                    temp_path = Path(tmp.name)
                try:
                    pd.read_csv(temp_path, nrows=3, dtype=str)
                    temp_path.replace(MASTER)
                finally:
                    temp_path.unlink(missing_ok=True)
            st.success("Instrument master saved locally. Open the next tab to search.")
            st.rerun()
        except Exception as exc:
            st.error(f"Master download failed: {exc}")
    st.markdown("**Step 2:** Search instruments and add reviewed Security IDs to your mapping.")
    st.markdown("**Step 3:** Download the selected symbols and inspect the candles before research.")

def master_matches(query: str, limit: int = 70):
    # A full instrument file can be large; use a small cached projection in memory.
    if not MASTER.exists():
        return None
    @st.cache_data(show_spinner=False, ttl=600)
    def read_master(path, size, mod_time):
        return pd.read_csv(path, dtype=str, low_memory=False).fillna("")
    frame = read_master(str(MASTER), MASTER.stat().st_size, MASTER.stat().st_mtime_ns)
    cols = [c for c in frame.columns if any(term in c.upper() for term in (
        "SYMBOL", "SECURITY", "DISPLAY", "SERIES", "NAME", "EXCH", "SEGMENT", "INSTRUMENT", "SEM_"))]
    if not cols:
        cols = list(frame.columns)
    mask = frame[cols].astype(str).apply(lambda col: col.str.contains(query, case=False, regex=False, na=False)).any(axis=1)
    return frame.loc[mask, cols].head(limit)

with tabs[1]:
    st.subheader("Instrument finder")
    query = st.text_input("Search a company, trading symbol, or Security ID", value="RELIANCE", key="dhan_query")
    if not MASTER.exists():
        st.warning("Go to Connection & master and download the instrument master first.")
    elif query.strip():
        try:
            results = master_matches(query.strip())
            st.caption(f"Showing up to 70 matching rows from your local Dhan master. Verify exchange and instrument type.")
            st.dataframe(results, hide_index=True, use_container_width=True)
            st.info("Dhan's detailed instrument columns can vary. Copy the verified Security ID, segment and type to the next tab. Do not assume one search result represents historical Nifty membership.")
        except Exception as exc:
            st.error(f"Master search failed: {exc}")
    else:
        st.info("Enter a symbol or company name to search. Full master browsing is intentionally disabled for performance.")

def persist_instruments(instruments: list[Instrument]) -> None:
    if not instruments:
        raise ValueError("Watchlist must not be empty")
    if MAPPING.exists():
        raise FileExistsError("Mapping exists: use the explicit Replace mapping action")
    mapping_frame = pd.DataFrame([{
        "label": i.label, "security_id": i.security_id,
        "exchange_segment": i.exchange_segment, "instrument": i.instrument,
        "expiry_code": i.expiry_code,
    } for i in instruments])
    mapping_frame.to_csv(MAPPING, index=False)

with tabs[2]:
    st.subheader("Local research watchlist")
    if mapping_error:
        st.error(f"Mapping file requires repair: {mapping_error}")
    if mapped:
        st.dataframe(pd.DataFrame([{
            "Label": i.label, "Security ID": i.security_id,
            "Segment": i.exchange_segment, "Type": i.instrument,
        } for i in mapped]), hide_index=True, use_container_width=True)
    else:
        st.info("No reviewed mapping yet. Add the first instrument below.")
    st.caption("Mappings are stored only in ignored data/dhan/instruments.csv. Adding an instrument never changes existing downloaded candles.")
    with st.form("dhan_add_mapping"):
        label = st.text_input("Unique short label", placeholder="RELIANCE")
        security_id = st.text_input("Verified Dhan Security ID", placeholder="Enter numeric ID from instrument master")
        segment = st.selectbox("Exchange segment", ["NSE_EQ", "BSE_EQ", "NSE_FNO", "NSE_CURRENCY", "BSE_FNO"])
        instrument_type = st.selectbox("Instrument", ["EQUITY", "INDEX", "FUTIDX", "FUTSTK", "OPTIDX", "OPTSTK"])
        add = st.form_submit_button("Add instrument to watchlist", type="primary")
    if add:
        try:
            safe_label = label.strip().upper()
            if not safe_label or not all(c.isalnum() or c in "_-" for c in safe_label):
                raise ValueError("Label must contain only letters, numbers, underscores or hyphens")
            candidate = Instrument(label=safe_label, security_id=security_id.strip(),
                                   exchange_segment=segment, instrument=instrument_type)
            if any(x.label == candidate.label for x in mapped):
                raise ValueError("Duplicate label; choose another or remove the old row")
            new_list = mapped + [candidate]
            if MAPPING.exists():
                MAPPING.unlink()
            persist_instruments(new_list)
            st.success(f"Added {safe_label}")
            st.rerun()
        except Exception as exc:
            st.error(f"Mapping not saved: {exc}")
    if mapped:
        with st.expander("Remove a mapped instrument"):
            remove_label = st.selectbox("Select label to remove", [x.label for x in mapped])
            st.caption("Only removes its mapping, never its saved candle history.")
            if st.button("Remove selected mapping"):
                remaining = [x for x in mapped if x.label != remove_label]
                if remaining:
                    MAPPING.unlink()
                    persist_instruments(remaining)
                else:
                    MAPPING.unlink()
                st.rerun()

with tabs[3]:
    st.subheader("Download historical OHLCV")
    if not connected:
        st.warning("Add your API token in .env and restart the dashboard before downloading.")
    if not mapped:
        st.warning("Add at least one reviewed Dhan instrument in the Watchlist mapping tab.")
    selected_names = st.multiselect("Instruments to download", [i.label for i in mapped], default=[i.label for i in mapped[:1]])
    today = date.today()
    left, right, third = st.columns(3)
    start = left.date_input("Start date (inclusive)", value=today - timedelta(days=365), max_value=today)
    end = right.date_input("End date (exclusive)", value=today, min_value=start + timedelta(days=1))
    resolution = third.selectbox("Candle resolution", ["Daily", "1 minute", "5 minutes", "15 minutes", "25 minutes", "60 minutes"])
    intraday = None if resolution == "Daily" else int(resolution.split()[0])
    st.caption("Dhan API access, rate limits and historical availability depend on your account. Intraday requests may be large or unavailable for older dates.")
    folder_name = st.text_input("Local run folder (optional)", value=date.today().strftime("run_%Y%m%d"), help="A new folder under data/dhan/raw; protects previous evidence from overwrites")
    valid_folder = bool(folder_name) and all(c.isalnum() or c in "_-" for c in folder_name)
    if not valid_folder:
        st.error("Run folder may use only letters, numbers, underscore and hyphen.")
    if st.button("Fetch selected historical candles", type="primary", disabled=not(connected and mapped and selected_names and valid_folder)):
        if end <= start:
            st.error("End date must be later than start date")
        else:
            run_dir = RAW / folder_name
            instruments = [x for x in mapped if x.label in selected_names]
            completed = []
            for inst in instruments:
                try:
                    with st.spinner(f"Downloading {inst.label}..."):
                        frame = download_candles(inst, start.isoformat(), end.isoformat(),
                                                interval=intraday, pause_seconds=.5)
                        filepath, manifest = save_download(frame, inst, run_dir, start.isoformat(), end.isoformat(), intraday)
                    completed.append((inst.label, len(frame), str(filepath.relative_to(ROOT))))
                except Exception as exc:
                    st.error(f"{inst.label}: {exc}")
            if completed:
                st.success(f"Completed {len(completed)} of {len(instruments)} instrument downloads.")
                st.dataframe(pd.DataFrame(completed, columns=["Instrument","Candles","Local file"]), hide_index=True, use_container_width=True)
                st.session_state["dhan_last_download_folder"] = str(run_dir)
                st.session_state["dhan_selected_symbols"] = selected_names
    st.caption("Downloads are local read-only HTTPS requests. Existing filenames are never silently overwritten. No historical benchmark, dividends, or constituents are fabricated.")

with tabs[4]:
    st.subheader("Inspect downloaded data")
    files = sorted(RAW.glob("**/*_daily.csv")) + sorted(RAW.glob("**/*_intraday_*m.csv"))
    if not files:
        st.info("No candle files yet. Use Download history.")
    else:
        picked = st.selectbox("Saved candle file", files, format_func=lambda p: str(p.relative_to(DATA)))
        try:
            raw_frame = pd.read_csv(picked)
            needed = {"datetime", "open", "high", "low", "close", "volume"}
            if not needed.issubset(raw_frame.columns):
                raise ValueError(f"Missing candle fields: {sorted(needed - set(raw_frame.columns))}")
            timestamps = pd.to_datetime(raw_frame.datetime, utc=True, errors="raise")
            values = raw_frame[["open","high","low","close","volume"]].apply(pd.to_numeric, errors="raise")
            if values[["open","high","low","close"]].le(0).any().any() or values.volume.lt(0).any():
                raise ValueError("Invalid OHLCV values")
            rows = len(raw_frame)
            st.session_state["dhan_last_inspected"] = str(picked)
            x, y, z = st.columns(3)
            x.metric("Observed candles", rows)
            y.metric("First observation", str(timestamps.min().date()) if rows else "—")
            z.metric("Last observation", str(timestamps.max().date()) if rows else "—")
            plot = pd.DataFrame({"Time": timestamps, "Close": values.close, "Volume": values.volume})
            st.plotly_chart(px.line(plot, x="Time", y="Close", title="Observed Dhan closes (not dividend total returns)"), use_container_width=True)
            st.plotly_chart(px.bar(plot.tail(250), x="Time", y="Volume", title="Last 250 trading observations: volume"), use_container_width=True)
            st.dataframe(raw_frame.tail(100), hide_index=True, use_container_width=True)
            with open(picked, "rb") as source:
                st.download_button("Export selected OHLCV CSV", source.read(), file_name=picked.name, mime="text/csv")
        except Exception as exc:
            st.error(f"Cannot inspect selected candles: {exc}")
    st.warning("Corporate actions, licensing, missing trading sessions, and delistings require separate review before historical performance claims.")

with tabs[5]:
    st.subheader("Convert Dhan candles into model inputs")
    st.markdown("This produces **month-end close observations** for the selected mapped symbols. It does not manufacture constituent membership, dividends, fundamentals or benchmark returns.")
    daily_roots = sorted({p.parent for p in RAW.glob("**/*_daily.csv")})
    if mapped and daily_roots:
        chosen_root = st.selectbox("Input folder containing daily candles", daily_roots, format_func=lambda p: str(p.relative_to(DATA)))
        destination_name = st.text_input("Research output folder name", value=date.today().strftime("dhan_monthly_%Y%m%d"))
        clean_name = bool(destination_name) and all(c.isalnum() or c in "_-" for c in destination_name)
        available = [inst for inst in mapped if (chosen_root / (inst.label + "_daily.csv")).exists()]
        selected = st.multiselect("Daily series to convert", [x.label for x in available], default=[x.label for x in available])
        if st.button("Build monthly close matrix", disabled=not(bool(available and selected and clean_name)), type="primary"):
            try:
                output_dir = MONTHLY / destination_name
                picked_instruments = [inst for inst in available if inst.label in selected]
                result = build_monthly_close(chosen_root, picked_instruments, output_dir)
                st.session_state["dhan_monthly_dir"] = str(output_dir)
                st.success(f"Month-end matrix saved: {result.relative_to(ROOT)}")
            except Exception as exc:
                st.error(f"Monthly conversion failed: {exc}")
    else:
        st.info("Download at least one daily series to enable month-end conversion.")
    st.divider()
    st.subheader("Research readiness and handoff")
    st.markdown("**Next:** Use Empirical Readiness to verify prices, effective-dated membership, corporate actions, publication-dated fundamentals and benchmark series.")
    data_directories = sorted(MONTHLY.glob("*/prices.csv"))
    if data_directories:
        newest = data_directories[-1].parent
        chosen = st.selectbox("Prepared close-price folder", [p.parent for p in data_directories],
                              format_func=lambda p: str(p.relative_to(ROOT)))
        st.session_state["research_input_dir"] = str(chosen)
        st.success("Research input folder selected for Index Research: " + str(chosen.relative_to(ROOT)))
        st.warning("A prices.csv file alone is NOT a valid experiment dataset. Index Research must still verify membership.csv and benchmark.csv. These are never fabricated.")
    st.page_link("dashboard/pages/13_Empirical_Readiness.py", label="Continue to empirical evidence review →", icon="🧾")
    st.page_link("dashboard/pages/1_Index_Research.py", label="Open Index Research →", icon="📈")
