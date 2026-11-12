"""Local mathematical/visual test-data contracts; no GitHub Actions."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from index_research.visual_validation import (
    option_price_surface,portfolio_risk_surface,option_convergence,
    identity_checks,gbm_moments,validation_table,
    risk_contribution_test,three_asset_covariance,
)


class VisualValidationTests(unittest.TestCase):
    def test_option_surface_finite_and_nonnegative(self):
        df=option_price_surface(strikes=np.linspace(80,120,5),
                                volatilities=np.linspace(.10,.50,5))
        self.assertEqual(len(df),25)
        self.assertTrue(np.isfinite(df[["price","delta","vega"]]).all().all())
        self.assertTrue((df.price>=0).all())
        at_strike=df[df.strike==100].sort_values("volatility")
        self.assertTrue(at_strike.price.is_monotonic_increasing)

    def test_portfolio_risk_surface_simplex(self):
        c=three_asset_covariance()
        result=portfolio_risk_surface(c,resolution=15)
        self.assertEqual(len(result),15*16//2)
        self.assertTrue(np.allclose(result[["weight_1","weight_2","weight_3"]].sum(axis=1),1))
        self.assertGreaterEqual(result.annual_volatility.min(),0)

    def test_analytical_option_parities(self):
        checks=identity_checks()
        self.assertEqual(len(checks),2)
        self.assertTrue(all(check.passed for check in checks))

    def test_numerical_convergence_checks(self):
        df,checks=option_convergence()
        self.assertEqual(len(df),11)
        self.assertTrue((df.absolute_error>=0).all())
        self.assertTrue(all(c.passed for c in checks))

    def test_gbm_mean_confidence_and_bounds(self):
        data,checks=gbm_moments(paths=6000,seed=2026)
        self.assertTrue(all(c.passed for c in checks))
        self.assertTrue((data.p05<=data.p50).all())
        self.assertTrue((data.p50<=data.p95).all())
        self.assertTrue(np.all(np.isfinite(data.to_numpy())))

    def test_risk_contribution_identity(self):
        values,checks=risk_contribution_test()
        self.assertTrue(all(c.passed for c in checks))
        self.assertAlmostEqual(values.share_of_volatility.sum(),1.0,places=9)

    def test_chart_evidence_table_columns(self):
        output=validation_table([*identity_checks(),*risk_contribution_test()[1]])
        self.assertTrue({"Test","Status","Tolerance","Absolute error"}.issubset(output.columns))
        self.assertTrue((output.Status=="PASS").all())


if __name__=="__main__":
    unittest.main()
