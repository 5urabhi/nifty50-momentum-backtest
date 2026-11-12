"""CI-only deterministic browser-smoke data. Never use as observed market evidence.

Runs exclusively in an ephemeral GitHub Actions checkout. Does not contact Dhan,
write canonical Dhan history, place broker orders, or include credentials.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from workstation_api import model_lab, research_library, service


def main() -> None:
    if os.environ.get("CI", "").lower() != "true":
        raise SystemExit("Refusing to seed CI demonstration fixtures outside CI=true")
    if os.getenv("DHAN_ACCESS_TOKEN"):
        raise SystemExit("Browser smoke must not run with a Dhan credential")
    folder = service.DATA / "workstation_imports" / "ci_browser_smoke"
    if folder.exists():
        raise SystemExit("Smoke fixture directory already exists. No existing data may be overwritten.")
    folder.mkdir(parents=True)
    rng = np.random.default_rng(55031)
    dates = pd.bdate_range("2024-01-02", periods=460)
    changes = np.column_stack([
        rng.normal(.0005, .012, len(dates)),
        rng.normal(.0002, .013, len(dates)),
        rng.normal(.0007, .011, len(dates)),
        rng.normal(-.0001, .015, len(dates)),
    ])
    prices = 100 * np.exp(changes.cumsum(axis=0))
    observed = pd.DataFrame(prices, index=dates, columns=["TEST_A", "TEST_B", "TEST_C", "TEST_D"])
    observed.to_csv(folder / "daily_prices.csv", index_label="date")
    monthly = observed.resample("ME").last()
    monthly.to_csv(folder / "prices.csv", index_label="date")
    pd.DataFrame({
        "date": [monthly.index[0].date()] * 4,
        "ticker": list(monthly.columns),
        "eligible": [True] * 4,
    }).to_csv(folder / "membership.csv", index=False)
    pd.DataFrame({"date": monthly.index.date,
                  "benchmark": np.zeros(len(monthly), dtype=float)}
                 ).to_csv(folder / "benchmark.csv", index=False)
    assert service.dataset_path("upload_ci_browser_smoke")[1]["ready"], "CI synthetic fixture must be parseable"

    # Model results provide browser UI comparisons without network calls.
    for seed in (17, 23):
        outcome = model_lab.run_model("gbm", raw_parameters={
            "steps": 30, "paths": 48, "seed": seed, "drift": .04, "volatility": .2
        })
        model_lab.save_result(outcome)
    project = research_library.create("project", "CI smoke project — synthetic fixture",
                                      {"goal": "Demonstrate reproducible interface flows"})
    research_library.create("notebook", "CI smoke notebook",
                            {"project_id": project["id"], "cells": []},
                            tags=["ci-fixture"])
    print("CI TEST FIXTURE: synthetic test data stored under upload_ci_browser_smoke; not real market evidence")
    print("CI TEST FIXTURE: two seeded numerical runs and one project/notebook prepared")


if __name__ == "__main__":
    main()
