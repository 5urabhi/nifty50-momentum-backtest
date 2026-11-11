"""Deterministic SYNTHETIC research fixtures; never label as real Nifty results."""
from pathlib import Path
import numpy as np
import pandas as pd


def make_fixture(directory: str | Path, seed: int = 2026) -> Path:
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(seed)
    dates=pd.date_range("2015-01-31",periods=96,freq="ME")
    tickers=[f"SYNTH_{n:02d}" for n in range(20)]
    market=rng.normal(0.006,0.04,len(dates))
    iid=rng.normal(0,0.055,(len(dates),len(tickers)))
    returns=np.clip(market[:,None]+iid,-0.5,1.5)
    prices=pd.DataFrame(100*np.exp(np.cumsum(np.log1p(returns),axis=0)),index=dates,columns=tickers)
    prices.to_csv(root/"prices.csv",index_label="date")
    membership=pd.DataFrame({"date":[str(dates[0].date())]*len(tickers),
                             "ticker":tickers,"eligible":[True]*len(tickers)})
    membership.to_csv(root/"membership.csv",index=False)
    benchmark=pd.DataFrame({"date":dates,"return":market})
    benchmark.to_csv(root/"benchmark.csv",index=False)
    fundamentals=[]
    for date in dates[::3]:
        for ticker in tickers:
            fundamentals.append({"ticker":ticker,"period_end":date,
                                 "available_at":date+pd.Timedelta(days=12),
                                 "value":float(rng.normal()),"quality":float(rng.normal()),
                                 "size":float(rng.uniform(1000,100000))})
    pd.DataFrame(fundamentals).to_csv(root/"fundamentals.csv",index=False)
    (root/"DO_NOT_CITE.txt").write_text(
        "Entire dataset is mathematically SYNTHETIC, not NSE, MSCI, or Nifty history.\n"
        "Use exclusively for local debugging and UI checks.\n")
    return root
