# Research Dashboard

Run from the repository root:

```bash
python -m pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

Panels:
- Covariance and long-only constrained minimum-variance optimization on
  **uploaded** monthly simple return data.
- Historical VaR and simple empirical tail-loss mean on uploaded return data.
- Seeded hypothetical GBM paths, clearly labeled as model simulation.
- Black–Scholes–Merton European call/put prices and Greeks.

No verified backtest returns, tracked index level or benchmark-relative
performance is available until the research protocol's data audit is complete.
CSV inputs should contain a date column followed by numeric security return
columns in decimal units. This is a research demonstration, not investment advice.
