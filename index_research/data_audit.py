"""Point-in-time data readiness audit for local research inputs.

This checks internal consistency, not external truth, data licensing, or the
historical correctness of an index constituent list.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .data import load_research_inputs, read_fundamentals
from .sector_data import read_sector_history, asof_sectors


def audit_dataset(directory: str | Path) -> dict:
    folder=Path(directory)
    prices,membership,benchmark,fundamentals=load_research_inputs(folder)
    p=prices.astype(float)
    finite_prices=np.isfinite(p.to_numpy())
    positive=p.gt(0)
    available=p.notna() & positive
    intervals=p.shift(-1).div(p).sub(1)
    membership_incomplete=membership & (~available)
    missing_forward=membership & (intervals.isna())
    # Last price row has no forward return by construction.
    missing_forward=missing_forward.iloc[:-1]
    warnings=[]
    if membership_incomplete.any().any():
        warnings.append("Some eligible securities have no positive price on some decision dates.")
    if missing_forward.any().any():
        warnings.append("Some eligible securities have unavailable next-period returns; a selected holding would fail.")
    if fundamentals is None:
        warnings.append("Publication-dated fundamental factors absent: Value/Quality/Size cannot run.")
    elif (fundamentals[["value","quality","size"]].isna().any().any()):
        warnings.append("Some fundamental fields are missing; full-composite coverage may be reduced.")
    sector_path=folder/"sectors.csv"
    historical_sectors=None
    if sector_path.exists():
        historical_sectors=asof_sectors(read_sector_history(str(sector_path)),
                                       prices.index,prices.columns)
        if (membership & historical_sectors.isna()).to_numpy().any():
            warnings.append("Some eligible securities have unknown sector vintages.")
    else:
        warnings.append("Historical sector classifications are absent; sector caps unavailable.")
    action_path=folder/"corporate_actions.csv"
    if action_path.exists():
        actions=pd.read_csv(action_path)
        required={"date","ticker","event_type","event_source"}
        if not required.issubset(actions.columns):
            raise ValueError("corporate_actions.csv requires date,ticker,event_type,event_source")
        dates=pd.to_datetime(actions["date"],errors="raise")
        if dates.isna().any() or actions[list(required-{"date"})].isna().any().any():
            raise ValueError("incomplete corporate-action evidence")
        unknown=set(actions["ticker"])-set(prices.columns)
        if unknown:
            raise ValueError(f"corporate actions reference unknown tickers: {sorted(unknown)}")
        actions_count=len(actions)
    else:
        actions_count=0
        warnings.append("No corporate-action evidence supplied; adjusted price/vendor policy must be documented.")
    return {
        "data_directory":str(folder),
        "first_date":str(prices.index.min().date()),
        "last_date":str(prices.index.max().date()),
        "number_of_monthly_marks":len(prices),
        "number_of_securities":len(prices.columns),
        "eligible_security_date_pairs":int(membership.to_numpy().sum()),
        "nonmissing_positive_price_fraction":float(available.to_numpy().mean()),
        "missing_prices_when_eligible":int(membership_incomplete.to_numpy().sum()),
        "missing_next_returns_when_eligible":int(missing_forward.to_numpy().sum()),
        "historical_sector_classifications_supplied":historical_sectors is not None,
        "fundamental_rows":len(fundamentals) if fundamentals is not None else 0,
        "corporate_action_evidence_rows":actions_count,
        "warnings":warnings,
        "caveat":"INTERNAL CONSISTENCY AUDIT ONLY. Does not verify historical source provenance, adjusted-return conventions, constituent history, permissions or delisting payouts."
    }


def save_dataset_audit(directory: str | Path, output: str | Path) -> Path:
    result=audit_dataset(directory)
    path=Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,allow_nan=False))
    return path
