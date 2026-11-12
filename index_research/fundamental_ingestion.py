"""Point-in-time financial-statement ingestion and transparent factor inputs.

Input is a documented *normalized* filing export, not an untrusted automatic
scrape. Filing timestamp (public availability) is essential to prevent
financial-statement look-ahead. This does not reproduce proprietary MSCI
Value/Quality factor methodologies.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

REQUIRED = {
    "ticker","period_end","published_at","source_url","filing_id",
    "book_equity","net_income_ttm","revenue_ttm","operating_income_ttm",
    "total_assets","total_debt","shares_outstanding","market_cap"
}


def normalize_filing_export(path: str | Path) -> pd.DataFrame:
    """Validate standardized filings.csv supplied from NSE filings/XBRL export.

    All financial amounts are required to use ONE consistent currency/unit
    convention within each row. Do not use revised numbers before revision's
    actual published_at. market_cap must be a period-specific sourced point,
    not inferred from today's shares or present-day equity values.
    """
    data=pd.read_csv(path,dtype={"ticker":str,"filing_id":str,"source_url":str})
    missing=REQUIRED-set(data)
    if missing:
        raise ValueError(f"missing financial fields: {sorted(missing)}")
    data=data[list(sorted(REQUIRED))].copy()
    for name in ("period_end","published_at"):
        data[name]=pd.to_datetime(data[name],errors="raise",utc=True).dt.tz_convert(None)
    numeric=sorted(REQUIRED-{"ticker","filing_id","source_url","period_end","published_at"})
    for name in numeric:
        data[name]=pd.to_numeric(data[name],errors="coerce")
    if (data[["ticker","filing_id","period_end","published_at","source_url"]].isna().any().any()
        or data[["ticker","filing_id"]].duplicated().any()
        or (data["published_at"]<data["period_end"]).any()
        or not np.isfinite(data[numeric].to_numpy()).all()
        or (data["total_assets"]<=0).any()
        or (data["market_cap"]<=0).any()
        or (data["shares_outstanding"]<=0).any()):
        raise ValueError("filing identities, dates or numeric fields invalid")
    if data["source_url"].str.strip().eq("").any():
        raise ValueError("filing needs source record")
    # Negative income/equity are allowed as evidence but *not* treated as
    # high-value/high-quality positives. Analysts should review those cases.
    return data.sort_values(["ticker","published_at","period_end","filing_id"]).reset_index(drop=True)


def compute_pit_factor_records(filings: pd.DataFrame) -> pd.DataFrame:
    """Higher-is-better value and quality factor proxies with transparent math.

    Value = book equity / contemporary market cap (book-to-market).
    Quality = 0.5 * ROA + 0.5 * operating margin.
    Size = contemporary market cap, which scoring engine later ranks as -log.
    Invalid denominator or negative book equity => NA value. These are simple
    research proxies and should not be called established MSCI factor scores.
    """
    f=filings.copy()
    value=(f["book_equity"]/f["market_cap"]).where(f["book_equity"]>0)
    roa=f["net_income_ttm"]/f["total_assets"]
    margin=(f["operating_income_ttm"]/f["revenue_ttm"]).where(f["revenue_ttm"]>0)
    quality=(0.5*roa+0.5*margin).where(roa.notna() & margin.notna())
    out=pd.DataFrame({
        "ticker":f["ticker"],"period_end":f["period_end"],
        "available_at":f["published_at"],
        "value":value,"quality":quality,"size":f["market_cap"],
        "filing_id":f["filing_id"],"source_url":f["source_url"],
    })
    if out[["ticker","available_at"]].duplicated().any():
        raise ValueError("multiple filings with same availability timestamp per ticker")
    return out.sort_values(["available_at","ticker"]).reset_index(drop=True)


def export_factor_inputs(filing_csv: str | Path, output_dir: str | Path) -> tuple[Path,Path]:
    """Write research factors and provenance; never modify supplied raw filing."""
    filings=normalize_filing_export(filing_csv)
    scores=compute_pit_factor_records(filings)
    root=Path(output_dir)
    root.mkdir(parents=True,exist_ok=True)
    csvpath=root/"fundamentals.csv"
    if csvpath.exists():
        raise FileExistsError("fundamentals.csv exists; create versioned output folder")
    scores[["ticker","period_end","available_at","value","quality","size"]].to_csv(csvpath,index=False)
    manifest=root/"fundamental_sources.csv"
    scores[["ticker","period_end","available_at","filing_id","source_url"]].to_csv(manifest,index=False)
    (root/"FUNDAMENTAL_METHODS.json").write_text(json.dumps({
        "value":"book_equity / market_cap; only positive book equity",
        "quality":"0.5 * net_income_ttm / total_assets + 0.5 * operating_income_ttm / revenue_ttm",
        "size":"historical contemporary market_cap, later used as -log(market_cap)",
        "availability":"only visible on strictly later decision dates than published_at",
        "warning":"Inputs require independently verified first-public filing timestamps and historical market caps. No NSE filings were automatically retrieved."
    },indent=2))
    return csvpath,manifest
