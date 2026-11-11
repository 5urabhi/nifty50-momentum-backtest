"""Shared in-session return matrix for local model labs.

No automatic historical certification. This converts the active index
experiment's observed level matrix to decimal simple returns for analysis.
"""
import numpy as np
import pandas as pd
import streamlit as st

def active_asset_returns(minimum: int = 12, max_assets: int | None = None) -> pd.DataFrame:
    saved=st.session_state.get("index_research_result")
    if not saved or "research_inputs" not in saved:
        raise ValueError("No active experiment. First run Index Research, or upload a CSV.")
    prices=saved["research_inputs"].get("prices")
    if not isinstance(prices,pd.DataFrame) or prices.empty:
        raise ValueError("Active experiment has no usable price matrix")
    if max_assets is not None and len(prices.columns)>max_assets:
        raise ValueError(f"Model limited to {max_assets} securities; this experiment has {len(prices.columns)}")
    values=prices.pct_change(fill_method=None).iloc[1:].dropna(how="any")
    if len(values)<minimum:
        raise ValueError(f"Model requires at least {minimum} fully observed return periods; found {len(values)}")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("Active security return matrix contains nonfinite values")
    if values.index.has_duplicates or not values.index.is_monotonic_increasing:
        raise ValueError("Active return timestamps must be unique and increasing")
    return values

def active_source_label() -> str:
    saved=st.session_state.get("index_research_result")
    if not saved:
        return "No experiment"
    return "SYNTHETIC EXAMPLE" if saved.get("demo") else "USER DATA — NOT AUDITED"
