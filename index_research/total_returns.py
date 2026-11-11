"""Source-aware corporate-action and total-return normalization.

Important:
* Dhan reports DAILY historic prices adjusted for splits and bonus shares.
* Dividends are NOT assumed included in vendor daily closes.
* No double-counting of splits or already-adjusted total-return prices.
* Delisting/suspension recoveries require actual sourced values and are never
  imputed. This module does not model rights, tender offers or spin-offs.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

EVENTS = {"dividend", "split", "bonus", "delisting_cash"}
PRICE_BASES = {"raw_unadjusted", "split_bonus_adjusted", "total_return_adjusted"}

def read_actions(path: str | Path) -> pd.DataFrame:
    """Event CSV: ex_date,ticker,event_type,cash_per_share,share_multiplier,
    declared_at,source_url,verified. Exact ex-date is required for daily data.

    dividend cash_per_share is amount per post-action share held on ex-date.
    split/bonus share_multiplier is NEW shares per OLD share, e.g. 2 for 2:1.
    delisting_cash uses proceeds per share upon actual closure, NOT a guess.
    """
    f = pd.read_csv(path)
    required = {"ex_date","ticker","event_type","cash_per_share",
                "share_multiplier","declared_at","source_url","verified"}
    if not required.issubset(f):
        raise ValueError(f"missing action fields: {sorted(required-set(f))}")
    f = f[list(required)].copy()
    for k in ["ex_date","declared_at"]:
        f[k] = pd.to_datetime(f[k],errors="raise").dt.normalize()
    for k in ["cash_per_share","share_multiplier"]:
        f[k] = pd.to_numeric(f[k],errors="raise")
    f["verified"] = f["verified"].astype(str).str.lower().map(
        {"true":True,"false":False,"1":True,"0":False})
    if (f[["ex_date","ticker","event_type","declared_at","source_url","verified"]].isna().any().any()
        or not f["event_type"].isin(EVENTS).all()
        or not np.isfinite(f[["cash_per_share","share_multiplier"]]).all().all()
        or (f["cash_per_share"] < 0).any() or (f["share_multiplier"]<=0).any()
        or f[["ticker","ex_date","event_type"]].duplicated().any()):
        raise ValueError("invalid, duplicate or unverifiable corporate action")
    if (f["declared_at"]>f["ex_date"]).any():
        raise ValueError("corporate action announced after ex-date: check vintage")
    if f["source_url"].astype(str).str.strip().eq("").any():
        raise ValueError("each event needs source evidence")
    if not f["verified"].all():
        raise ValueError("unverified corporate actions are blocked from total-return construction")
    if ((f.event_type.isin(["split","bonus"])) & (f.share_multiplier<=0)).any():
        raise ValueError("invalid split/bonus ratio")
    return f.sort_values(["ex_date","ticker","event_type"]).reset_index(drop=True)


def total_return_index(daily_close: pd.Series, actions: pd.DataFrame,
                       *, price_basis: str, ticker: str,
                       dividends_already_included: bool=False) -> pd.DataFrame:
    """Build normalized total-return wealth from DAILY OHLC observed closes.

    For pre-split-adjusted prices: period return=(P_t+D_t)/P_prev-1,
    where D_t is per share on the contemporaneous adjusted share basis.
    For raw unadjusted prices: apply split/bonus multiplicity at the ex-date:
      period wealth factor=(M*(P_t+D_t))/P_prev.
    For delisting_cash: use actual sourced cash proceeds and stop the series.
    Dividend is received on ex-date and reinvested at that day's close.

    Returns date-indexed close, simple_return, wealth_index (starts 1).
    A reference adjusted price and vendor dividend policy must be documented
    externally before interpreting this as economic total return.
    """
    if price_basis not in PRICE_BASES:
        raise ValueError("explicit price_basis is mandatory")
    if dividends_already_included and price_basis != "total_return_adjusted":
        raise ValueError("dividends_already_included only valid for total_return_adjusted")
    if price_basis == "total_return_adjusted" and not dividends_already_included:
        raise ValueError("must confirm dividends already included for total_return_adjusted")
    p = pd.Series(daily_close,dtype=float).copy()
    if not isinstance(p.index,pd.DatetimeIndex) or p.index.has_duplicates or not p.index.is_monotonic_increasing:
        raise ValueError("daily series needs ascending unique dates")
    if len(p)<2 or p.isna().any() or (p<=0).any() or not np.isfinite(p).all():
        raise ValueError("daily closes must be complete, positive, finite")
    p.index = p.index.normalize()
    if p.index.has_duplicates:
        raise ValueError("multiple bars on same date; expected daily data")
    if actions is None:
        actions=pd.DataFrame(columns=["ex_date","ticker","event_type","cash_per_share","share_multiplier"])
    events=actions[actions["ticker"]==ticker].copy()
    if len(events):
        events["ex_date"]=pd.to_datetime(events["ex_date"]).dt.normalize()
        if ((events.ex_date<p.index.min())|(events.ex_date>p.index.max())).any():
            raise ValueError("events outside price coverage must be reviewed separately")
        if not events.ex_date.isin(p.index).all():
            raise ValueError("an ex-date has no corresponding trading close")
    if len(events):
        terminal_days=set(events.loc[events["event_type"]=="delisting_cash","ex_date"])
        conflicting=events.loc[events["ex_date"].isin(terminal_days)]
        if any((conflicting.groupby("ex_date").size()>1)):
            raise ValueError("cash delisting combined with other same-day events requires separate economic modeling")
    if price_basis == "total_return_adjusted" and len(events):
        raise ValueError("already total-return-adjusted series must not apply events again")
    cash=pd.Series(0.,index=p.index)
    multiplier=pd.Series(1.,index=p.index)
    delisted=False
    terminal_recovery=pd.Series(np.nan,index=p.index)
    # For a vendor split-adjusted price series, historical closes are in
    # current-share units. Historical pre-split dividends are converted to
    # the same units using verified later split/bonus multipliers.
    later_splits=events[events["event_type"].isin(["split","bonus"])]
    for _,event in events.iterrows():
        day=event["ex_date"]
        kind=event["event_type"]
        if kind=="dividend":
            dividend=float(event["cash_per_share"])
            if price_basis=="split_bonus_adjusted":
                later=later_splits[later_splits["ex_date"]>day]
                if len(later):
                    dividend/=float(later["share_multiplier"].prod())
            cash.at[day]+=dividend
        elif kind in ("split","bonus"):
            if price_basis=="raw_unadjusted":
                multiplier.at[day]*=float(event["share_multiplier"])
            # Dhan split/bonus-adjusted daily: do not multiply again.
        else:
            if delisted:
                raise ValueError("multiple terminal delisting payouts")
            if day != p.index.max():
                raise ValueError("delisting cash must be terminal; truncate after payout")
            if event["cash_per_share"]<=0:
                raise ValueError("delisting recovery must have actual sourced cash")
            terminal_recovery.at[day]=float(event["cash_per_share"])
            delisted=True
    end_value=p+cash
    # A terminal cash recovery replaces the last stock price; it is NOT an
    # extra dividend paid while the final traded share remains valuable.
    end_value.loc[terminal_recovery.notna()]=terminal_recovery.dropna()
    gross=end_value*multiplier / p.shift(1)
    gross.iloc[0]=1.
    if (gross<=0).any() or not np.isfinite(gross).all():
        raise ValueError("invalid total-return wealth factor")
    wealth=gross.cumprod()
    return pd.DataFrame({"close":p,"cash_per_share":cash,
                         "share_multiplier_applied":multiplier,
                         "simple_return":gross-1.,
                         "wealth_index":wealth},index=p.index)


def daily_to_monthly_total_return(series: pd.DataFrame) -> pd.Series:
    """Month-end observed wealth level; do not forward-fill missing months."""
    if "wealth_index" not in series:
        raise ValueError("expected computed wealth index")
    monthly=series["wealth_index"].groupby(series.index.to_period("M")).last()
    monthly.index=monthly.index.to_timestamp("M")
    return monthly.rename("total_return_index")


def build_research_total_returns(raw_folder: str | Path, instruments,
                                 actions_file: str | Path,
                                 output_folder: str | Path, *,
                                 price_basis: str="split_bonus_adjusted") -> Path:
    """Produce prices.csv of normalized *wealth* indices for supported events.

    Requires verified actions file (possibly header-only for no events);
    resulting data remain provisional until completeness of dividend/split
    evidence and source adjustment policy are independently established.
    """
    actions=read_actions(actions_file)
    panels=[]
    for inst in instruments:
        src=Path(raw_folder)/(inst.label+"_daily.csv")
        frame=pd.read_csv(src)
        if not {"datetime","close","security_id","label"}.issubset(frame):
            raise ValueError(f"{src} missing required columns")
        if not frame["security_id"].astype(str).eq(inst.security_id).all() or not frame["label"].eq(inst.label).all():
            raise ValueError("security mapping mismatch")
        days=pd.to_datetime(frame.datetime,utc=True).dt.tz_convert("Asia/Kolkata").dt.normalize().dt.tz_localize(None)
        close=pd.Series(pd.to_numeric(frame.close,errors="raise").to_numpy(),index=pd.DatetimeIndex(days)).sort_index()
        calc=total_return_index(close,actions,price_basis=price_basis,ticker=inst.label)
        panels.append(daily_to_monthly_total_return(calc).rename(inst.label))
    matrix=pd.concat(panels,axis=1).sort_index()
    out=Path(output_folder)
    out.mkdir(parents=True,exist_ok=True)
    target=out/"prices.csv"
    if target.exists():
        raise FileExistsError(f"{target} exists (do not overwrite previous vintage)")
    matrix.to_csv(target,index_label="date")
    (out/"RETURN_METHODOLOGY.json").write_text(json.dumps({
        "vendor":"DhanHQ daily OHLCV","price_basis":price_basis,
        "dividend_adjustment":"verified ex-date cash-per-share, reinvested on ex-date",
        "split_bonus_adjustment":"only applied to raw_unadjusted basis",
        "supported_events":sorted(EVENTS),
        "not_supported":["rights_issue","spin_off","merger_exchange","tender_offer","unknown_delisting_recovery"],
        "validation":"UNVERIFIED completeness of market events and price adjustments",
        "use":"research only until event coverage and vendor policy independently verified"
    },indent=2))
    return target
