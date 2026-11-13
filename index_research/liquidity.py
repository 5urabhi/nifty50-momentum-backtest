"""Capacity and nonlinear market-impact research with actual dated liquidity input.

Costs are SCENARIO ESTIMATES. They are not observed order-book fills, audited
taxes, exchange fee invoices or liquidity forecasts. Missing/stale inputs fail.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
from .index import IndexBacktest


def read_liquidity(path: str | Path) -> pd.DataFrame:
    """date,ticker,adv_currency,half_spread_bps.

    ADV is average daily traded *notional in the same currency as portfolio
    capital*. The user must document its backward-looking construction.
    """
    source=Path(path)
    if not source.is_file() or source.is_symlink():
        raise ValueError("liquidity.csv required for market-impact and capacity analysis")
    data=pd.read_csv(source)
    columns={"date","ticker","adv_currency","half_spread_bps"}
    if not columns.issubset(data.columns) or data.empty:
        raise ValueError("liquidity.csv needs date,ticker,adv_currency,half_spread_bps")
    table=data[list(sorted(columns))].copy()
    table["date"]=pd.to_datetime(table["date"],errors="raise")
    for col in ("adv_currency","half_spread_bps"):
        table[col]=pd.to_numeric(table[col],errors="raise")
    if (table[["date","ticker"]].isna().any().any()
        or table["ticker"].astype(str).str.strip().eq("").any()
        or table[["date","ticker"]].duplicated().any()
        or not np.isfinite(table[["adv_currency","half_spread_bps"]].to_numpy()).all()
        or (table["adv_currency"]<=0).any() or (table["half_spread_bps"]<0).any()
        or (table["half_spread_bps"]>10_000).any()):
        raise ValueError("Invalid or duplicated dated liquidity observations")
    return table.sort_values(["date","ticker"]).reset_index(drop=True)


def capacity_overlay(result: IndexBacktest, price_dates: pd.DatetimeIndex,
                     liquidity: pd.DataFrame, *, capital: float,
                     max_participation: float = .05,
                     execution_days: int = 3,
                     impact_coefficient_bps: float = 50.,
                     max_age_days: int = 95) -> tuple[IndexBacktest,pd.DataFrame]:
    """Add modeled half-spread and square-root market impact on ACTUAL turnover.

    For each held-period return indexed by t+1, rebalance trades occur at the
    beginning of the interval (t). The overlay aligns source liquidity to t
    or earlier and refuses stale observations. Basic fixed bps transaction cost
    from the simulator is retained SEPARATELY; do not also include spread in
    the fixed-bps assumption or costs will double count.

    Extra market cost on portfolio = sum(abs(delta_w) *
      (half_spread_bps + impact_coefficient_bps * sqrt(participation)))/10000.

    This estimates instantaneous weight-based order notional with fixed
    capital, not path-dependent execution or changing account equity.
    """
    if (not np.isfinite(capital) or capital<=0 or
        not 0<max_participation<=1 or not 1<=execution_days<=30 or
        not np.isfinite(impact_coefficient_bps) or impact_coefficient_bps<0):
        raise ValueError("Capacity model needs positive capital, participation, days and impact parameters")
    if (len(price_dates)!=len(result.returns)+1 or
        not result.returns.index.equals(price_dates[1:]) or
        not result.weights.index.equals(result.returns.index) or
        not result.pre_trade_weights.index.equals(result.returns.index)):
        raise ValueError("Liquidity overlay needs matching monthly formation and return dates")
    if not result.weights.columns.equals(result.pre_trade_weights.columns):
        raise ValueError("Liquidity overlay target and prior holdings must match")
    records=[]
    new_costs=[]
    for j, period in enumerate(result.returns.index):
        decision=price_dates[j]
        old=result.pre_trade_weights.iloc[j].astype(float)
        new=result.weights.iloc[j].astype(float)
        differences=(new-old).abs()
        if not np.isfinite(differences.to_numpy()).all():
            raise ValueError("Nonfinite archived portfolio trade weights")
        moved=differences[differences>1e-10]
        extra=0.
        max_actual=0.
        trade_notional=0.
        if not moved.empty:
            previous=liquidity.loc[liquidity["date"]<=decision]
            if previous.empty:
                raise ValueError("No dated liquidity before rebalance "+str(decision.date()))
            # Exact last known observed security liquidity, no modern backfill.
            last=(previous.sort_values(["date","ticker"])
                  .drop_duplicates("ticker",keep="last").set_index("ticker"))
            for ticker,delta in moved.items():
                if ticker not in last.index:
                    raise ValueError("Missing as-of liquidity for traded security: "+str(ticker))
                row=last.loc[ticker]
                age=(decision-pd.Timestamp(row["date"])).days
                if age>max_age_days:
                    raise ValueError("Stale liquidity for traded security: "+str(ticker))
                adv=float(row["adv_currency"])
                notional=float(delta)*capital
                participation=notional/(adv*execution_days)
                max_actual=max(max_actual,participation)
                if participation>max_participation+1e-12:
                    raise ValueError("Market capacity exceeded for "+str(ticker)+
                                     ": estimated participation="+f"{participation:.4f}"+
                                     ", allowed="+f"{max_participation:.4f}")
                half_spread=float(row["half_spread_bps"])
                impact=impact_coefficient_bps*np.sqrt(max(0.,participation))
                extra+=float(delta)*(half_spread+impact)/10_000
                trade_notional+=notional
        base=float(result.costs.iloc[j])
        total=base+extra
        if total>=1 or not np.isfinite(total):
            raise ValueError("Total modeled execution cost invalid")
        new_costs.append(total)
        records.append({
            "date":period.date().isoformat(),
            "decision_date":decision.date().isoformat(),
            "capital_currency":capital,
            "trade_notional_currency":trade_notional,
            "gross_turnover":float(differences.sum()),
            "max_actual_participation":max_actual,
            "participation_cap":max_participation,
            "fixed_cost_fraction":base,
            "additional_spread_impact_fraction":extra,
            "total_cost_fraction":total,
            "warning":"Modeled execution only; dated ADV/spread require source review.",
        })
    corrected_costs=pd.Series(new_costs,index=result.returns.index,
                              name="transaction_cost_fraction")
    corrected_net=(1-corrected_costs)*(1+result.gross_returns)-1
    return replace(result,returns=corrected_net.rename("net_return"),
                   costs=corrected_costs),pd.DataFrame(records)
