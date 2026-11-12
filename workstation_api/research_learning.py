"""Leakage-controlled CPU ML and tabular-RL research on saved observed prices.

Supervised models: ridge, random forest, histogram gradient boosting.
RL baseline: train-only discrete tabular Q-learning (long/cash, no leverage).
This is research/paper evaluation, not a live trading agent or execution API.

Execution convention: features are known after close t, action is entered
only after an additional session (close t+1), and earns return t+1 -> t+2.
Train labels are embargoed before the first test decision; all standardizing,
tuning and learning take place exclusively in the training segment.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import math

import numpy as np
import pandas as pd

from . import model_lab, research_advanced, research_insights, research_library

METHODS = {
    "ridge": "L2-regularized linear forecast (train-only standardization)",
    "random_forest": "Seeded random forest regression, fixed hyperparameters",
    "hist_gradient_boosting": "Seeded histogram gradient boosting regression",
    "tabular_q": "Bounded long/cash tabular Q-learning with frozen holdout policy",
}
MIN_SAMPLES=240
TARGET_SAMPLES=math.ceil(MIN_SAMPLES*1.20)
FEATURES=("return_1","mean_return_5","mean_return_20","volatility_20",
          "momentum_20","momentum_5","downside_20")
MAX_OBSERVATIONS=15000


def _dataset(dataset_id: str, asset: str):
    frame,source=research_advanced._price_data(dataset_id)
    if not isinstance(asset,str) or asset not in frame.columns:
        raise ValueError("Choose an observed price column in the selected dataset")
    series=frame[asset]
    finite=series.notna()
    if not finite.any():
        raise ValueError("Asset has no observed price observations")
    valid=series.loc[finite.idxmax():series.loc[finite].index[-1]]
    if valid.isna().any() or not np.isfinite(valid).all() or (valid<=0).any():
        raise ValueError("Internal missing, invalid or nonpositive prices: repair source data; no forward-fill")
    if len(valid)>MAX_OBSERVATIONS:
        raise ValueError("Limit learning studies to 15,000 observed daily prices")
    if source["frequency"]!="daily":
        raise ValueError("Learning studies require actual observed DAILY prices")
    return valid.astype(float),source


def _samples(prices: pd.Series):
    values=prices.to_numpy(dtype=float)
    r=np.empty(len(values),dtype=float)
    r[0]=np.nan
    r[1:]=values[1:]/values[:-1]-1
    features=[];targets=[];decision=[];entry=[];realized=[]
    for t in range(25,len(values)-2):
        past=r[t-19:t+1]
        recent=r[t-4:t+1]
        if not np.isfinite(past).all():
            raise ValueError("Invalid returns inside the feature lookback")
        x=[r[t],float(recent.mean()),float(past.mean()),
           float(past.std(ddof=1)),values[t]/values[t-20]-1,
           values[t]/values[t-5]-1,float(np.minimum(past,0).std(ddof=1))]
        features.append(x)
        targets.append(float(r[t+2]))
        decision.append(prices.index[t])
        entry.append(prices.index[t+1])
        realized.append(prices.index[t+2])
    return np.asarray(features,dtype=float),np.asarray(targets,dtype=float),decision,entry,realized


def readiness(dataset_id: str, asset: str) -> dict:
    prices,source=_dataset(dataset_id,asset)
    samples=max(0,len(prices)-27)
    return {"dataset_id":dataset_id,"asset":asset,"source":source,
            "observed_prices":len(prices),"usable_lagged_samples":samples,
            "minimum_samples":MIN_SAMPLES,"preferred_samples":TARGET_SAMPLES,
            "missing_minimum":max(0,MIN_SAMPLES-samples),
            "missing_preferred":max(0,TARGET_SAMPLES-samples),
            "ready":samples>=MIN_SAMPLES,
            "warning":"20% is a preferred coverage margin, not an independent test. "
                      "Use Dhan shared-cache extension to acquire real sessions if needed."}


def _state(x: np.ndarray) -> int:
    # Four observable momentum/volatility regimes. Thresholds fixed ex ante,
    # not selected on test returns.
    momentum=1 if x[2]>0 else 0
    volatility=1 if x[3]>.015 else 0
    return momentum*2+volatility


def _learn_q(x: np.ndarray,y: np.ndarray,cost: float,seed: int) -> np.ndarray:
    rng=np.random.default_rng(seed)
    q=np.zeros((4,2),dtype=float)
    # Model-free offline tabular baseline. Replayed historical episodes may
    # overfit; the policy is frozen before the unseen chronological holdout.
    for epoch in range(70):
        action_previous=0
        for i in range(len(y)-1):
            state=_state(x[i])
            action=int(rng.integers(0,2)) if rng.random()<max(.04,.22*(.975**epoch)) else int(np.argmax(q[state]))
            reward=action*y[i]-(cost if action!=action_previous else 0.)
            next_state=_state(x[i+1])
            q[state,action]+=.08*(reward+.92*np.max(q[next_state])-q[state,action])
            action_previous=action
    return q


def run(dataset_id: str,asset: str,method: str = "ridge",
        train_fraction: float = .70,cost_bps: float = 8.,
        seed: int = 2026,progress=None) -> dict:
    if method not in METHODS: raise ValueError("Unsupported registered learning method")
    if not .60<=train_fraction<=.85: raise ValueError("Training fraction must be 0.60–0.85")
    if not 0<=cost_bps<=250: raise ValueError("Trading cost must be 0–250 bps")
    if not isinstance(seed,int) or not 0<=seed<=2147483647:
        raise ValueError("Invalid seeded experiment")
    if progress:progress(2,"Inspecting daily price source and sample sufficiency")
    prices,source=_dataset(dataset_id,asset)
    x,y,decision,entry,realized=_samples(prices)
    if len(x)<MIN_SAMPLES:
        raise ValueError(f"{len(x)} lagged samples; at least {MIN_SAMPLES} required. "
                         f"Preferred with 20% margin: {TARGET_SAMPLES}.")
    cut=int(len(x)*train_fraction)
    embargo=2
    # Every training label was realized before the FIRST holdout decision.
    train_stop=cut-embargo
    if train_stop<120 or len(x)-cut<40:
        raise ValueError("Not enough chronological training/holdout observations")
    if not realized[train_stop-1] < decision[cut]:
        raise AssertionError("Purged training labels must precede first test decision")
    xtrain,ytrain=x[:train_stop],y[:train_stop]
    xtest,ytest=x[cut:],y[cut:]
    if progress:progress(15,"Fitting only the purged training segment")
    cost=cost_bps/10000.
    coeff=None
    if method=="tabular_q":
        q=_learn_q(xtrain,ytrain,cost,seed)
        action=np.array([int(np.argmax(q[_state(row)])) for row in xtest],dtype=int)
        forecast=np.array([float(q[_state(row),1]-q[_state(row),0]) for row in xtest])
        model_detail={"q_table":q.tolist(),"states":"fixed momentum sign × volatility > 1.5%",
                      "actions":["cash","long"],"training_episodes":70}
    else:
        try:
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler
            from sklearn.linear_model import Ridge
            from sklearn.ensemble import RandomForestRegressor,HistGradientBoostingRegressor
            import sklearn
        except ImportError as exc:
            raise RuntimeError("Install requirements.txt to enable CPU learning models") from exc
        models={
            "ridge":make_pipeline(StandardScaler(),Ridge(alpha=10.)),
            "random_forest":RandomForestRegressor(n_estimators=90,max_depth=5,
                                min_samples_leaf=12,n_jobs=1,random_state=seed),
            "hist_gradient_boosting":HistGradientBoostingRegressor(
                                max_iter=75,max_leaf_nodes=9,l2_regularization=5.,
                                learning_rate=.06,random_state=seed),
        }
        fitted=models[method]
        fitted.fit(xtrain,ytrain)
        forecast=np.asarray(fitted.predict(xtest),dtype=float)
        if not np.isfinite(forecast).all():
            raise ValueError("Trained model produced invalid forecasts")
        action=(forecast>cost).astype(int)
        model_detail={"model_family":method,"sklearn_version":sklearn.__version__,
                      "hyperparameters":"Fixed in source; not selected using the holdout."}
        if method=="ridge":
            coeff=fitted.named_steps["ridge"].coef_.tolist()
    if progress:progress(78,"Applying one-session execution lag and cost assumptions")
    changes=np.abs(np.diff(np.concatenate(([0],action))))
    strategy=action*ytest-cost*changes
    passive=ytest
    if not np.isfinite(strategy).all() or np.any(strategy<=-1):
        raise ValueError("Computed returns invalid for wealth-index evaluation")
    w=100*np.cumprod(1+strategy)
    bh=100*np.cumprod(1+passive)
    def ratio(z):
        std=float(np.std(z,ddof=1))
        return math.sqrt(252)*float(np.mean(z))/std if std>1e-14 else None
    dates=[d.date().isoformat() for d in realized[cut:]]
    # Full observations go to CSV. The library graph is a bounded preview.
    preview=np.unique(np.linspace(0,len(dates)-1,min(600,len(dates)),dtype=int))
    plot=model_lab.xy("Strictly later observed returns — "+METHODS[method],
        [dates[i] for i in preview],
        [{"name":"Frozen learning policy, net cost","y":w[preview].tolist()},
         {"name":"Single-asset passive reference (price-only)","y":bh[preview].tolist()}],
        "Realized holdout session","Illustrative wealth base 100")
    report={
        "kind":"learning_holdout","method":method,"asset":asset,"dataset_id":dataset_id,
        "source":source,"source_sha256":source["source_sha256"],
        "model_settings":{"train_fraction":train_fraction,"cost_bps":cost_bps,
                          "seed":seed,"execution_delay_sessions":1,
                          "training_embargo_samples":embargo},
        "features":list(FEATURES),"model_detail":model_detail,
        "train_observations":len(xtrain),"embargo_samples":embargo,
        "test_observations":len(xtest),"figure_observations":len(preview),
        "preferred_sample":TARGET_SAMPLES,
        "last_training_label_date":realized[train_stop-1].date().isoformat(),
        "first_test_decision_date":decision[cut].date().isoformat(),
        "first_test_entry_date":entry[cut].date().isoformat(),
        "first_realized_holdout_date":dates[0],
        "cost_bps":cost_bps,"turnover_units":int(changes.sum()),
        "holdout_sharpe_net":ratio(strategy),
        "passive_sharpe_price_only":ratio(passive),
        "holdout_total_return_net":float(w[-1]/100-1),
        "passive_total_return_price_only":float(bh[-1]/100-1),
        "holdout_max_drawdown_net":float(np.min(w/np.maximum.accumulate(np.r_[100.,w])[1:]-1)),
        "fraction_in_market":float(action.mean()),
        "plot":plot,
        "warning":"Retrospective exploratory historical study; not a trained live execution "
                  "agent or validated investment alpha. Results use unadjusted price returns, "
                  "one-session delayed signals, simplified configurable costs, no portfolio "
                  "capacity/slippage/fees/borrow adjustments and no independently frozen "
                  "multi-researcher selection protocol. A 20% buffer is not out-of-sample proof.",
    }
    if coeff is not None: report["ridge_coefficients"]=coeff
    if progress:progress(91,"Saving complete test-period return evidence")
    saved=research_library.create("study","Learning: "+method+" · "+asset,report,
                                  tags=["learning","historical_holdout"])
    target=research_insights.study_returns_root()/(saved["id"]+".csv")
    target.parent.mkdir(parents=True,exist_ok=True)
    artifact=pd.DataFrame({
        "date":dates,"strategy":strategy,"equal_weight":passive,
        "position_long":action,"forecast":forecast,
        "decision_date":[d.date().isoformat() for d in decision[cut:]],
        "entry_date":[d.date().isoformat() for d in entry[cut:]],
    })
    try:
        artifact.to_csv(target,index=False,float_format="%.12g")
    except Exception:
        research_library.action(saved["id"],"trash")
        target.unlink(missing_ok=True)
        raise
    if progress:progress(100,"Frozen learning holdout evidence saved")
    return {**report,"study_id":saved["id"],
            "returns_csv_url":"/api/workspace/studies/"+saved["id"]+"/returns.csv"}
