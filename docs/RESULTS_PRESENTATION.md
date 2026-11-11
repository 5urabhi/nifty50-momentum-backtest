# How to Communicate Results (Recruiter / Research Reviewer)

## Three audiences

1. **Recruiter / hiring manager (30 seconds).** Show one research question,
   the methodology, dataset status, the final-test period, and the important
   benchmark-relative outcomes. Do not lead with legacy optimized Sharpe.
2. **Quantitative index researcher (5 minutes).** Explain point-in-time
   constituent selection, publication-lag controls, index rules, treatment
   of turnover and transaction costs, and why the weighting scheme is used.
3. **Technical interviewer (15 minutes).** Show `index_research/`, data
   ingestion contracts, deterministic tests, experiment JSON config, return
   and benchmark alignment, and ways it can fail under adverse scenarios.

## Research report structure

- Question and null hypothesis.
- Data vendors, licenses, security identifiers and eligible history.
- Factor formulations and as-of availability rules.
- Index construction and annual/quarterly reconstitution.
- Portfolio risk / covariance assumptions and volatility models.
- Experiment split (development, validation, untouched final test).
- Benchmark-relative metrics, charts, uncertainty and scenario analysis.
- Negative controls, practical implementation frictions and limitations.
- Reproducibility metadata: dataset hashes, software commit, configuration.

## Resume policy

Only list implemented contributions you personally made. No fabricated
quantitative uplift. A responsible (conditional) example:

> Developed an independent multi-factor equity index research framework in
> Python, combining cross-sectional signal engineering, constrained index
> weighting, benchmark-relative backtesting, and provenance-aware reporting.

Once a verified out-of-sample experiment is independently reproduced, add
**only true** data-specific figures such as realized tracking error,
annualized turnover and evaluation period. Avoid claiming to reproduce MSCI
proprietary factors or to have production-grade trading capabilities.

## Dashboard labeling

The dashboard's synthetic data are explicitly marked SYNTHETIC. The
legacy-static demo is marked STATIC UNIVERSE WITH SURVIVORSHIP BIAS.
Real-world user inputs are marked UNVERIFIED until documentation and
external checks justify changing the status.

## Vercel

Vercel's static preview only displays exported aggregate returns and summary
metrics; it does NOT run Python optimization or market data processing.
Publish a snapshot only with explicit consent and a verified right to share
all figures. No brokerage/private holdings or raw vendor data.
