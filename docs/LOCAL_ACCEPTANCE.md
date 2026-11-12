# Local Acceptance Checklist (run later)

**Do not call the entire empirical project verified until these checks pass.**

1. Create `.venv`, install `dashboard/requirements.txt`.
2. Run `python -m unittest discover -s tests -v` and investigate all failures.
3. Generate synthetic fixture; run momentum and multi-factor configurations.
4. Check that output CSVs/JSON/HTML are present and finite.
5. Run both Streamlit pages and verify responsive charts, file uploads and exports.
6. Run static legacy adapter. Confirm disclosure of missing historical
   constituents and **never** treat its internal benchmark as official Nifty.
7. Verify no date from the *future* influences a prior-date factor or index weight.
8. Inject bad membership, missing held security prices, nonpositive prices,
   mismatched benchmark dates; validate hard failures.
9. Verify turnover equals absolute target minus drifted pre-trade holdings.
10. Compare execution lag 0 vs 1 and transaction cost stress.
11. Validate a legal point-in-time historical dataset and consistent
    adjusted/total-return benchmark series; record source, revision policy
    and source licenses.
12. Freeze parameters before final test; run independent holdout and document
    negative results, confidence intervals and sector/risk sensitivities.
13. Generate a publishable report only from verified results, review
    method limitations and configure the resume claims accordingly.
14. If deploying a static Vercel snapshot later, inspect exactly the files
    in `web/data` to prevent vendor, user or proprietary information leaks.

No GitHub Actions, hosted automation, scheduled execution, live trading,
broker connection or production Vercel deployment is required by this project.
