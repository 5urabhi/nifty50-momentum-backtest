import unittest
import numpy as np
import pandas as pd
from index_research.math_models import (
    sample_covariance, shrinkage_covariance, ewma_covariance,
    minimum_variance, historical_var_es, simulate_gbm,
    black_scholes, factor_regression,
)


class MathematicalModelTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(18)
        self.r = pd.DataFrame(rng.normal(size=(120,3))*0.02, columns=["A","B","C"])

    def test_covariance_psd_and_shrinkage(self):
        sample = sample_covariance(self.r)
        shrunk = shrinkage_covariance(self.r, intensity=1)
        ewma = ewma_covariance(self.r)
        self.assertTrue(np.all(np.linalg.eigvalsh(sample) >= -1e-12))
        self.assertTrue(np.allclose(shrunk.to_numpy(), np.diag(np.diag(sample))))
        self.assertTrue(np.all(np.linalg.eigvalsh(ewma) >= -1e-12))

    def test_minimum_variance_closed_form_diagonal(self):
        cov = pd.DataFrame(np.diag([1.0,4.0]),index=["A","B"],columns=["A","B"])
        result = minimum_variance(cov)
        self.assertAlmostEqual(result.weights["A"],0.8,places=4)
        self.assertAlmostEqual(result.weights.sum(),1.0,places=7)
        capped = minimum_variance(cov,max_weight=0.6)
        self.assertAlmostEqual(capped.weights["A"],0.6,places=4)

    def test_infeasible_caps_rejected(self):
        cov = sample_covariance(self.r)
        with self.assertRaises(ValueError):
            minimum_variance(cov,max_weight=0.2)

    def test_var_es_order(self):
        r = pd.Series(np.linspace(-0.2, 0.2, 101))
        m = historical_var_es(r)
        self.assertGreaterEqual(m["expected_shortfall"],m["var"])

    def test_gbm_deterministic_zero_vol(self):
        paths = simulate_gbm(100,0.05,0,1,12,4,seed=3)
        self.assertTrue(np.allclose(paths[-1],100*np.exp(0.05)))
        self.assertEqual(paths.shape,(13,4))

    def test_black_scholes_parity_and_delta(self):
        c=black_scholes(100,100,1,0.05,0.2,"call")
        p=black_scholes(100,100,1,0.05,0.2,"put")
        self.assertAlmostEqual(c["price"]-p["price"],100-100*np.exp(-0.05),places=9)
        self.assertAlmostEqual(c["delta"]-p["delta"],1.0,places=9)
        self.assertGreater(c["vega"],0)

    def test_ols_factor_recovery(self):
        rng = np.random.default_rng(11)
        index=pd.date_range("2020-01-31",periods=100,freq="ME")
        factors=pd.DataFrame({"mkt":rng.normal(0,0.03,100),
                              "value":rng.normal(0,0.02,100)},index=index)
        asset=0.002+1.2*factors["mkt"]-0.4*factors["value"]
        reg=factor_regression(asset,factors)
        self.assertAlmostEqual(reg["alpha_per_period"],0.002,places=10)
        self.assertAlmostEqual(reg["betas"]["mkt"],1.2,places=10)
        self.assertAlmostEqual(reg["betas"]["value"],-0.4,places=10)
        self.assertAlmostEqual(reg["r_squared"],1.0,places=10)


if __name__=="__main__":
    unittest.main()
