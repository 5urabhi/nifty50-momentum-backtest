"""Versioned action-adjusted research data from original daily prices.

Original Dhan/user source remains immutable. A reviewed action ledger is
SELF-DECLARED input, not independent event-completeness certification.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import os
import shutil
import uuid

import numpy as np
import pandas as pd

from index_research.data import read_matrix, read_membership, read_returns
from index_research.total_returns import read_actions, total_return_index
from . import service

MAX_ACTION_BYTES = 2_000_000
MAX_DAILY_BYTES = 250_000_000
COPY = (
    "membership.csv", "benchmark.csv", "daily_prices.csv",
    "PIT_MEMBERSHIP_PROVENANCE.json", "BENCHMARK_PROVENANCE.json",
    "BENCHMARK_SOURCE.json", "DAILY_AGGREGATION_PROVENANCE.json",
    "DHAN_BATCH_PROVENANCE.json", "CALENDAR_ALIGNMENT_PROVENANCE.json",
    "OBSERVED_MARKET_SESSIONS.csv", "PER_SECURITY_LAST_OBSERVED_SESSIONS.csv",
    "fundamentals.csv", "FUNDAMENTAL_METHODS.json", "sectors.csv",
    "benchmark_weights.csv", "liquidity.csv", "EVIDENCE_REVIEW.json",
)


def import_adjusted(dataset_id: str, content: bytes, *,
                    price_basis: str = "split_bonus_adjusted") -> dict:
    """Create a new data version; never mutate source or overwrite another view."""
    if not isinstance(content, bytes) or len(content) == 0 or len(content) > MAX_ACTION_BYTES:
        raise ValueError("Supply a genuine corporate action ledger CSV under 2 MB")
    if price_basis not in {"split_bonus_adjusted", "raw_unadjusted"}:
        raise ValueError("Select the actual vendor daily-price adjustment basis")
    folder, dataset = service.dataset_path(dataset_id)
    if dataset.get("kind") == "synthetic" or (folder / "DO_NOT_CITE.txt").exists():
        raise ValueError("Synthetic fixtures cannot become observed research by importing events")
    original_file = folder / "prices.csv"
    daily_file = folder / "daily_prices.csv"
    if any(p.is_symlink() or not p.is_file() for p in (original_file, daily_file)):
        raise ValueError("Original dataset must include unchanged prices.csv and daily_prices.csv")
    if daily_file.stat().st_size > MAX_DAILY_BYTES:
        raise ValueError("Daily source exceeds safe local conversion size; split the universe first")
    if folder.is_symlink() or any(p.is_symlink() for p in folder.iterdir()):
        raise ValueError("Refusing to copy a dataset containing symbolic links")
    original = read_matrix(original_file, positive=True)
    daily = read_matrix(daily_file, positive=True)
    if not pd.Index(daily.columns).equals(pd.Index(original.columns)):
        raise ValueError("Daily and monthly price panels use different ticker order or identities")
    if not original.index.is_monotonic_increasing or not daily.index.is_monotonic_increasing:
        raise ValueError("Original source dates are not chronological")
    if not original.index.isin(daily.index).all():
        raise ValueError("Original monthly trading sessions are absent in the daily close series")
    if (folder/"membership.csv").is_file():
        read_membership(folder/"membership.csv",original.index,original.columns)
    if (folder/"benchmark.csv").is_file():
        benchmark=read_returns(folder/"benchmark.csv")
        if not benchmark.index.equals(original.index):
            raise ValueError("Benchmark and price calendar are incompatible")

    parsed=pd.read_csv(BytesIO(content))
    needed={"ex_date","ticker","event_type","cash_per_share",
            "share_multiplier","declared_at","source_url","verified"}
    if not needed.issubset(parsed.columns):
        raise ValueError("Corporate action file lacks required columns: " +
                         ", ".join(sorted(needed-set(parsed.columns))))
    if not set(parsed["ticker"].dropna().astype(str)).issubset(set(original.columns)):
        raise ValueError("Corporate action contains security identities absent from the original panel")
    for url in parsed["source_url"].dropna().astype(str):
        uri=urlsplit(url)
        if (uri.scheme != "https" or not uri.hostname or uri.username
                or uri.password or uri.query or uri.fragment or len(url)>500):
            raise ValueError("Action event citations must use credential-free public HTTPS URLs")
    # read_actions checks event values, declared-at availability, duplicate
    # ex-dates and self-asserted verified flags, without conferring authority.
    suffix="actions_"+uuid.uuid4().hex[:12]
    base=service.DATA/"workstation_imports"
    base.mkdir(parents=True,exist_ok=True)
    staging=base/(".pending_"+suffix)
    target=base/suffix
    staging.mkdir(mode=0o700)
    try:
        event_file=staging/"corporate_actions.csv"
        event_file.write_bytes(content)
        events=read_actions(event_file)
        adjusted=pd.DataFrame(index=original.index,columns=original.columns,dtype=float)
        gaps=[]
        for ticker in original.columns:
            observed = daily[ticker].dropna()
            if len(observed)<2:
                raise ValueError("Insufficient original daily close observations: "+ticker)
            mask = daily.index.isin(observed.index)
            first,last=np.flatnonzero(mask)[[0,-1]]
            if not mask[first:last+1].all():
                gaps.append(ticker)
                continue
            calc=total_return_index(observed,events,
                price_basis=price_basis,ticker=str(ticker))
            adjusted[ticker]=calc["wealth_index"].reindex(original.index).to_numpy()
            old=original[ticker]
            if (old.notna() & adjusted[ticker].isna()).any():
                raise ValueError("Adjusted wealth does not reach an originally observed market session: "+ticker)
        if gaps:
            raise ValueError("Interior missing daily trading sessions; cannot infer returns for: "+
                             ", ".join(gaps[:12]))
        if not np.isfinite(adjusted.to_numpy(dtype=float)[~np.isnan(adjusted.to_numpy(dtype=float))]).all():
            raise ValueError("Normalized total return panel contains nonfinite values")
        if (adjusted.le(0) & adjusted.notna()).any().any():
            raise ValueError("Normalized total returns must remain positive")
        adjusted.to_csv(staging/"prices.csv",index_label="date",float_format="%.12g")
        for name in COPY:
            candidate=folder/name
            if candidate.is_file() and not candidate.is_symlink():
                shutil.copy2(candidate,staging/name)
        source_digest=hashlib.sha256(daily_file.read_bytes()).hexdigest() if daily_file.stat().st_size <= 25_000_000 else _sha_file(daily_file)
        (staging/"RETURN_METHODOLOGY.json").write_text(json.dumps({
            "kind":"reconstructed_total_return_wealth_research_v1",
            "source_dataset_id":dataset_id,
            "original_daily_prices_sha256":source_digest,
            "input_actions_sha256":hashlib.sha256(content).hexdigest(),
            "normalized_monthly_prices_sha256":_sha_file(staging/"prices.csv"),
            "price_basis":price_basis,
            "dividend_adjustment":"Self-declared source-cited ex-date cash dividends, reinvested at closing price",
            "split_bonus_adjustment":"Apply multiplicity only when raw_unadjusted",
            "self_reported_event_count":len(events),
            "supported_events":["dividend","split","bonus","delisting_cash"],
            "not_supported":["rights_issue","merger_exchange","spin_off","tender_offer","unknown_delisting_recovery"],
            "event_completeness_reviewed_independently":False,
            "source_price_adjustment_verified_independently":False,
            "status":"PROVISIONAL_RESEARCH_TOTAL_RETURN_NOT_CERTIFIED",
            "warning":"An empty action ledger does not establish zero dividends. "
                      "No corporate event, delisting payout or missing daily close is invented.",
        },indent=2,allow_nan=False))
        (staging/"workstation_source.json").write_text(json.dumps({
            "parent_dataset_id":dataset_id,
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "kind":"locally_normalized_research_view",
            "original_daily_prices_sha256":source_digest,
            "actions_sha256":hashlib.sha256(content).hexdigest(),
            "independent_source_certified":False,
            "warning":"Original vendor/downloaded data remains unchanged; event evidence requires independent review.",
        },indent=2))
        if target.exists():
            raise FileExistsError("Research view already exists; retry with a new version")
        os.rename(staging,target)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise
    return {"dataset_id":"upload_"+suffix,
            "parent_dataset_id":dataset_id,
            "monthly_observations":len(original),"securities":len(original.columns),
            "corporate_action_rows":len(events),
            "normalized_monthly_sha256":_sha_file(target/"prices.csv"),
            "independent_source_certified":False,
            "warning":"A new provisional total-return research dataset was created. "
                      "An independent corporate-event, benchmark and index-source review is still mandatory."}


def _sha_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()
