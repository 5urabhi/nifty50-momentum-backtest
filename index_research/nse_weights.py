"""Strict import of user-exported NSE Indices historical monthly weight reports.

The monthly snapshots are NOT original effective-dated index event notices.
Source reports must be lawfully downloaded separately and supplied locally.
Publication dates are explicit; an unknown same-day timestamp is not assumed
known at the preceding close. Historical ticker aliases are never guessed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json

import numpy as np
import pandas as pd

from .data import read_matrix


def _hash(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda:file.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _https(value: str) -> bool:
    parsed=urlsplit(str(value).strip())
    return bool(parsed.scheme=="https" and parsed.hostname and not parsed.username and
                not parsed.password and not parsed.query and not parsed.fragment)


def import_nifty_weight_snapshots(manifest_csv: str | Path,
                                  priced_universe_csv: str | Path,
                                  output_dir: str | Path,
                                  *, symbol_column: str = "Symbol",
                                  weight_column: str = "Weightage (%)",
                                  weight_unit: str = "percent",
                                  index_column: str | None = None,
                                  index_label: str = "NIFTY 50",
                                  pit_intervals_csv: str | Path | None = None) -> dict:
    """Create source-date lagged benchmark_weights.csv with explicit zeros.

    manifest_csv has file,snapshot_date,published_at,source_url per original
    exported CSV. The file name must be flat and relative to the manifest,
    and the URL must point to the original official HTTPS evidence page.
    No download/scrape is triggered; official file copyrights are respected.

    Publication date is *researcher-supplied* and must be independently
    verified. We conservatively delay eligibility by one calendar day
    because the exact publication timestamp is unknown.
    """
    origin=Path(manifest_csv).expanduser().resolve()
    result_root=Path(output_dir).expanduser().resolve()
    if result_root.exists():
        raise FileExistsError("Snapshot import output exists; research source views are immutable")
    if origin.is_symlink() or not origin.is_file():
        raise ValueError("Provide an original-source snapshot manifest.csv")
    if weight_unit not in {"percent","fraction"}:
        raise ValueError("Explicit weight_unit must be percent or fraction")
    if bool(index_column) and not str(index_label).strip():
        raise ValueError("Declare exact index label for a combined monthly report")
    universe=read_matrix(priced_universe_csv,positive=True).columns
    if len(universe)<50:
        raise ValueError("NIFTY 50 research requires a historical price universe of at least 50 securities")
    if universe.has_duplicates or any(not str(x).strip() for x in universe):
        raise ValueError("Historical modeled universe has duplicate/empty ticker identifiers")
    manifest=pd.read_csv(origin,dtype=str,keep_default_na=False)
    required={"file","snapshot_date","published_at","source_url"}
    if not required.issubset(manifest.columns) or manifest.empty:
        raise ValueError("Snapshot manifest requires file,snapshot_date,published_at,source_url")
    m=manifest[list(required)].copy()
    m["snapshot_date"]=pd.to_datetime(m["snapshot_date"],errors="raise")
    m["published_at"]=pd.to_datetime(m["published_at"],errors="raise")
    if (m["snapshot_date"].isna().any() or m["published_at"].isna().any() or
        m["snapshot_date"].duplicated().any() or
        (m["snapshot_date"]>m["published_at"]).any() or
        (m["published_at"]>pd.Timestamp.now()).any()):
        raise ValueError("Missing, duplicated, future, or chronologically invalid source report dates")
    if not m["snapshot_date"].is_monotonic_increasing:
        raise ValueError("Snapshot manifest must be sorted chronologically")
    if not all(_https(u) and len(u)<=500 for u in m["source_url"]):
        raise ValueError("Each source report needs plain public official HTTPS evidence")
    if (m["file"].str.strip()=="").any() or m["file"].duplicated().any():
        raise ValueError("Snapshot names must be present and unique")
    pit=None
    if pit_intervals_csv is not None:
        file=Path(pit_intervals_csv).expanduser().resolve()
        if file.is_symlink() or not file.is_file():
            raise ValueError("Cannot check missing PIT reconstruction evidence")
        pit=pd.read_csv(file,dtype=str,keep_default_na=False)
        needed={"index_name","symbol","valid_from","valid_to"}
        if not needed.issubset(pit):
            raise ValueError("PIT comparison needs exact interval source columns")
        pit=pit.loc[pit["index_name"].eq("Nifty 50")].copy()
        if pit.empty:
            raise ValueError("PIT reconstruction has no Nifty 50 intervals")
    records=[]
    provenance=[]
    mismatches=[]
    for row in m.itertuples(index=False):
        name=str(row.file)
        if Path(name).name!=name or name.startswith(".") or not name.lower().endswith(".csv"):
            raise ValueError("Use flat original CSV names; extract official ZIP locally if required")
        file=(origin.parent/name)
        if file.is_symlink() or not file.is_file():
            raise ValueError("Missing original NSE monthly snapshot: "+name)
        if file.stat().st_size>32*1024*1024:
            raise ValueError("Snapshot exceeds the local import size limit")
        observed=pd.read_csv(file,dtype=str,keep_default_na=False)
        if index_column:
            if index_column not in observed.columns:
                raise ValueError("Exact index column missing from "+name)
            observed=observed.loc[observed[index_column].str.strip()==index_label]
        if symbol_column not in observed or weight_column not in observed:
            raise ValueError(
                "Choose the actual symbol/weight columns for "+name+
                ": "+", ".join(observed.columns[:20]))
        selected=observed[[symbol_column,weight_column]].copy()
        selected.columns=["ticker","original_weight"]
        selected["ticker"]=selected["ticker"].astype(str).str.strip()
        if (selected["ticker"].eq("").any() or selected["ticker"].duplicated().any()):
            raise ValueError("Empty or duplicate original constituents in "+name)
        if len(selected)!=50:
            raise ValueError("NIFTY 50 monthly source must list exactly 50 names: "+
                             name+" has "+str(len(selected)))
        raw=selected["original_weight"].astype(str).str.replace(",","",regex=False).str.strip()
        if weight_unit=="fraction" and raw.str.contains("%",regex=False).any():
            raise ValueError("Explicit fractional weights cannot include percent signs")
        cleaned=raw.str.replace("%","",regex=False)
        values=pd.to_numeric(cleaned,errors="raise").to_numpy(dtype=float)
        if weight_unit=="percent":
            values/=100.
        if not np.isfinite(values).all() or (values<=0).any() or (values>1).any():
            raise ValueError("NSE source weights must be positive finite fractions")
        total=float(values.sum())
        if abs(total-1)>0.005:
            raise ValueError("Source weightage sum materially differs from 100%: "+
                             name+", found="+f"{total:.8f}")
        source_set=set(selected["ticker"])
        unknown=sorted(source_set-set(universe))
        if unknown:
            raise ValueError("Source references securities absent from complete historical "
                             "price universe. Never drop delisted/renamed names: "+
                             ", ".join(unknown[:20]))
        published=pd.Timestamp(row.published_at)
        # No reliance on an unknown within-day publication timestamp.
        usable=(published+pd.Timedelta(days=1)).normalize()
        asof=pd.Timestamp(row.snapshot_date).normalize()
        if records and usable<=pd.Timestamp(records[-1]["date"]):
            raise ValueError("Research release dates must increase strictly")
        normalized=values/total
        indexed=pd.Series(normalized,index=selected["ticker"])
        for ticker in universe:
            records.append({"date":usable.date().isoformat(),
                            "ticker":ticker,"weight":float(indexed.get(ticker,0.))})
        original_set=set(selected["ticker"])
        if pit is not None:
            observed_day=asof.date().isoformat()
            candidates=pit.loc[
                (pit["valid_from"]<=observed_day)&
                ((pit["valid_to"]=="")|(pit["valid_to"]>observed_day))]
            expected=set(candidates["symbol"])
            difference=sorted(original_set.symmetric_difference(expected))
            mismatches.append({"snapshot_date":observed_day,
                               "disagreement_count":len(difference),
                               "disputed_symbols":difference})
        provenance.append({
            "source_file":name,"snapshot_date":asof.date().isoformat(),
            "research_first_usable_day":usable.date().isoformat(),
            "researcher_declared_published_at":published.date().isoformat(),
            "original_source_https":row.source_url,
            "original_sha256":_hash(file),
            "original_constituents":len(selected),
            "original_weight_sum":total,
            "rounded_weights_rescaled_to_one":abs(total-1)>1e-10,
            "source_vs_PIT_disagreement":mismatches[-1]["disagreement_count"] if pit is not None else None,
        })
    if not provenance:
        raise ValueError("No source snapshots")
    result_root.mkdir(parents=True)
    pd.DataFrame(records).to_csv(result_root/"benchmark_weights.csv",index=False,
                                 float_format="%.12g")
    if mismatches:
        pd.DataFrame(mismatches).to_csv(result_root/"PIT_SNAPSHOT_COMPARISON.csv",index=False)
    summary={
        "kind":"official_nse_weightage_csv_user_supplied_unreviewed",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source_manifest_sha256":_hash(origin),
        "price_universe_sha256":_hash(Path(priced_universe_csv)),
        "pit_intervals_sha256":_hash(Path(pit_intervals_csv)) if pit is not None else None,
        "observed_source_snapshots":provenance,
        "modeled_universe_security_count":len(universe),
        "snapshot_count":len(provenance),
        "pit_disagreement_snapshots":sum(x["disagreement_count"]>0 for x in mismatches),
        "source_publication_times_independently_verified":False,
        "original_index_notice_effective_dates_proven":False,
        "source_licensing_independently_reviewed":False,
        "publication_certified":False,
        "notice":"Snapshot dates and researcher-supplied publication dates are NOT original "
                 "constituent entry/exit event dates. This importer delays use by one day "
                 "and never fabricates historical ticker aliases, index weights or prices.",
    }
    (result_root/"NSE_WEIGHTAGE_SOURCE_MANIFEST.json").write_text(
        json.dumps(summary,indent=2,allow_nan=False)+"\n")
    return {"output":str(result_root),
            "snapshots":len(provenance),
            "priced_universe":len(universe),
            "pit_snapshot_disagreements":len([x for x in mismatches if x["disagreement_count"]]),
            "publication_certified":False}
