"""Ex-post factor and portfolio diagnostics with explicit point-in-time timing.

Diagnostics require already validated monthly price/membership matrices.
Cross-sectional rank IC uses scores known at date t against return t->t+1.
Do not use this ex-post realized information to select model parameters on an
untouched final holdout.
"""
import numpy as np
import pandas as pd
from .factors import composite_scores, information_coefficient
from .sector_data import sector_exposure
from .research_analytics import factor_exposures


def evaluate_factor_panel(prices: pd.DataFrame, membership: pd.DataFrame,
                          fundamentals: pd.DataFrame | None,
                          components: tuple[str, ...] = (
                              "momentum", "low_volatility", "value", "quality", "size", "yield"),
                          momentum_formation: int = 12,
                          momentum_skip: int = 1,
                          volatility_lookback: int = 12) -> tuple[pd.DataFrame,dict[str,pd.DataFrame]]:
    """Factor-specific rank IC for the exact stated data and formation windows.

    Fundamental components are skipped (and reported) if no publication-dated
    fundamental records were provided; no synthetic scores are substituted.
    """
    allowed = {"momentum","low_volatility","value","quality","size","yield"}
    if not set(components).issubset(allowed) or not components:
        raise ValueError("unsupported or empty factor components")
    available = [k for k in components if
                 k in {"momentum","low_volatility"} or (
                     fundamentals is not None and
                     (k != "yield" or (
                         "yield" in fundamentals.columns and
                         fundamentals["yield"].notna().any())))]
    scores={}
    ics={}
    for name in available:
        matrix=composite_scores(
            prices,membership,{name:1.0},fundamentals,
            momentum_formation=momentum_formation,
            momentum_skip=momentum_skip,
            volatility_lookback=volatility_lookback)
        scores[name]=matrix
        ics[name]=information_coefficient(matrix,prices,membership)
    if not ics:
        raise ValueError("no usable factor components")
    panel=pd.DataFrame(ics)
    panel.index.name="holding_period_end"
    return panel,scores


def exposure_panel(weights: pd.DataFrame, date_specific_scores: dict[str,pd.DataFrame],
                   sectors: pd.DataFrame | None = None) -> tuple[pd.DataFrame,pd.DataFrame | None]:
    """Portfolio-weighted z-score exposure with strict security/time alignment."""
    # IndexBacktest weights are tagged by holding-period END and correspond to
    # decisions at the preceding month-end. Explicitly shift signal timestamps
    # into matching holding-period ends BEFORE multiplying by holdings.
    exposures={}
    for name,matrix in date_specific_scores.items():
        shifted=matrix.shift(1).reindex(index=weights.index,columns=weights.columns)
        # Missing initial signal is not a zero exposure; omit that date from
        # factor-specific exposure output by returning NA.
        invalid=weights.gt(1e-12)&shifted.isna()
        weighted=weights.mul(shifted.fillna(0)).sum(axis=1)
        weighted[invalid.any(axis=1)]=np.nan
        exposures[name]=weighted
    exposure_table=pd.DataFrame(exposures,index=weights.index)
    sector_table=None
    if sectors is not None:
        # Sector identities at holding-period end may differ from the decision
        # date. For historical valuation this explicitly uses end-date labels;
        # a methodology requiring trade-date sectors must retain its own as-of
        # decision-date panel.
        sector_table=sector_exposure(
            weights,sectors.reindex(index=weights.index,columns=weights.columns))
    return exposure_table,sector_table


def data_quality_report(prices: pd.DataFrame, membership: pd.DataFrame,
                        fundamentals: pd.DataFrame | None,
                        sectors: pd.DataFrame | None) -> dict:
    """Auditable availability diagnostic; does not assert vendor correctness."""
    if not prices.index.equals(membership.index) or not prices.columns.equals(membership.columns):
        raise ValueError("prices and membership must align")
    active=membership.astype(bool)
    usable=prices.notna()&(prices>0)
    eligible_total=int(active.to_numpy().sum())
    missing_eligible=int((active&~usable).to_numpy().sum())
    return {
        "number_of_monthly_dates":int(len(prices)),
        "number_of_tickers":int(len(prices.columns)),
        "eligible_stock_months":eligible_total,
        "missing_eligible_stock_months":missing_eligible,
        "eligible_price_coverage":float((eligible_total-missing_eligible)/eligible_total) if eligible_total else None,
        "has_fundamentals":fundamentals is not None,
        "fundamental_publication_records":int(len(fundamentals)) if fundamentals is not None else 0,
        "has_historical_sectors":sectors is not None,
        "sector_stock_month_coverage":float(sectors.notna().to_numpy().mean()) if sectors is not None else None,
        "independent_provenance_verified":False,
    }
