"""Independent mathematical acceptance tests for core quant models.

Run: python -m unittest tests.test_math_acceptance -v
No broker access, market files, or network are used. These checks test
analytic identities and invariants, not the statistical validity of a
real-world trading strategy.
"""
import unittest
import numpy as np
import pandas as pd

from index_research.math_models import (
    black_scholes,minimum_variance,simulate_gbm,sample_covariance
)
from index_research.derivatives import (
    binomial_option,monte_carlo_european,implied_volatility,heston_paths,
    merton_jump_diffusion
)
from index_research.portfolio_theory import (
    risk_parity,optimize_portfolio,risk_contributions
)
from index_research.portfolio_extensions import (
    black_litterman_posterior,minimize_historical_cvar
)
from index_research.advanced_models import simulate_ou
from index_research.model_validation import rolling_covariance_portfolios
from index_research.tail_risk import gaussian_var_es,student_t_var_es


class MathAcceptance(unittest.TestCase):
    def test_european_put_call_parity(self):
        s,k,t,r,q,sigma=102.,98.,1.3,.035,.012,.24
        c=black_scholes(s,k,t,r,sigma,"call",q)
        p=black_scholes(s,k,t,r,sigma,"put",q)
        self.assertAlmostEqual(c["price"]-p["price"],
             s*np.exp(-q*t)-k*np.exp(-r*t),places=10)
        self.assertAlmostEqual(c["delta"]-p["delta"],np.exp(-q*t),places=10)

    def test_greeks_against_central_finite_difference(self):
        s,k,t,r,q,sigma=100.,105.,.9,.03,.01,.22
        h=1e-2
        for option in ("call","put"):
            def value(spot,vol,rate,years):
                return black_scholes(spot,k,years,rate,vol,option,q)["price"]
            g=black_scholes(s,k,t,r,sigma,option,q)
            delta=(value(s+h,sigma,r,t)-value(s-h,sigma,r,t))/(2*h)
            gamma=(value(s+h,sigma,r,t)-2*value(s,sigma,r,t)+value(s-h,sigma,r,t))/h**2
            vega=(value(s,sigma+1e-4,r,t)-value(s,sigma-1e-4,r,t))/2e-4
            rho=(value(s,sigma,r+1e-4,t)-value(s,sigma,r-1e-4,t))/2e-4
            theta=(value(s,sigma,r,t-1e-4)-value(s,sigma,r,t+1e-4))/2e-4
            self.assertAlmostEqual(g["delta"],delta,delta=1e-5)
            self.assertAlmostEqual(g["gamma"],gamma,delta=2e-5)
            self.assertAlmostEqual(g["vega"],vega,delta=5e-4)
            self.assertAlmostEqual(g["rho"],rho,delta=5e-4)
            self.assertAlmostEqual(g["theta"],theta,delta=5e-4)

    def test_lattice_and_implied_volatility(self):
        analytic=black_scholes(100,100,1,.05,.2,"call")["price"]
        tree=binomial_option(100,100,1,.05,.2,steps=600,exercise="european")
        self.assertAlmostEqual(tree,analytic,delta=.025)
        inferred=implied_volatility(analytic,100,100,1,.05)
        self.assertAlmostEqual(inferred,.2,places=8)
        put_american=binomial_option(100,110,1,.05,.2,steps=400,option="put",exercise="american")
        put_european=binomial_option(100,110,1,.05,.2,steps=400,option="put",exercise="european")
        self.assertGreaterEqual(put_american,put_european-1e-10)

    def test_antithetic_monte_carlo_reproducibility(self):
        reference=black_scholes(100,100,1,.04,.2)["price"]
        a=monte_carlo_european(100,100,1,.04,.2,paths=40000,seed=7)
        b=monte_carlo_european(100,100,1,.04,.2,paths=40000,seed=7)
        self.assertEqual(a,b)
        self.assertLess(abs(a["price"]-reference),5*a["standard_error"]+.05)

    def test_minimum_variance_closed_form(self):
        labels=pd.Index(["A","B","C"])
        variances=np.array([.01,.04,.09])
        cov=pd.DataFrame(np.diag(variances),index=labels,columns=labels)
        expected=(1/variances)/(1/variances).sum()
        solver=minimum_variance(cov)
        np.testing.assert_allclose(solver.weights.to_numpy(),expected,atol=2e-5)
        other=optimize_portfolio(cov)
        np.testing.assert_allclose(other.weights.to_numpy(),expected,atol=2e-5)

    def test_risk_parity_and_euler_identity(self):
        labels=pd.Index(["A","B","C"])
        sigma=pd.DataFrame(np.diag([.01,.04,.09]),index=labels,columns=labels)
        solution=risk_parity(sigma)
        contribution=risk_contributions(solution.weights,sigma)
        np.testing.assert_allclose(contribution["share_of_volatility"],[1/3]*3,atol=1e-3)
        self.assertAlmostEqual(contribution["volatility_contribution"].sum(),
                               solution.volatility,places=9)

    def test_infeasible_parity_must_fail(self):
        labels=pd.Index(["A","B","C"])
        sigma=pd.DataFrame(np.diag([.01,.04,.16]),index=labels,columns=labels)
        # Equal risk budgets require a smaller variance asset to have more
        # weight than 1/3, impossible with a 0.34 single-name cap.
        with self.assertRaises(RuntimeError):
            risk_parity(sigma,max_weight=.34)

    def test_black_litterman_zero_view_residual(self):
        labels=pd.Index(["A","B"])
        sigma=pd.DataFrame(np.diag([.02,.06]),index=labels,columns=labels)
        w=pd.Series([.6,.4],index=labels)
        prior=3*sigma.to_numpy()@w.to_numpy()
        p=pd.DataFrame([[1.,-1.]],columns=labels,index=["view"])
        q=pd.Series([prior[0]-prior[1]],index=p.index)
        output=black_litterman_posterior(sigma,w,3.,p,q)
        np.testing.assert_allclose(output["posterior_expected_returns"],prior,atol=1e-12)

    def test_cvar_symmetric_invariant(self):
        rng=np.random.default_rng(20)
        scenarios=pd.DataFrame({"A":rng.normal(0,.04,300),
                                "B":rng.normal(0,.08,300)})
        out=minimize_historical_cvar(scenarios,confidence=.95,max_weight=.8)
        self.assertAlmostEqual(float(out["weights"].sum()),1.,places=8)
        self.assertTrue((out["weights"]<=.800001).all())
        self.assertGreaterEqual(out["empirical_tail_mean"],out["empirical_var"])

    def test_gbm_exact_expected_mean(self):
        paths=simulate_gbm(100,.06,.20,1,24,20000,seed=11)
        theoretical=100*np.exp(.06)
        terminal=paths[-1]
        stderr=terminal.std(ddof=1)/np.sqrt(len(terminal))
        self.assertLess(abs(terminal.mean()-theoretical),5*stderr)

    def test_ou_exact_transition_expectation(self):
        paths=simulate_ou(3.,1.,1.5,.3,1/12,12,20000,seed=12)
        analytic=1+(3-1)*np.exp(-1.5)
        stderr=paths[-1].std(ddof=1)/np.sqrt(paths.shape[1])
        self.assertLess(abs(paths[-1].mean()-analytic),5*stderr)

    def test_heston_and_jump_zero_diffusion_limits(self):
        h=heston_paths(100,.04,1,steps=12,paths=20,vol_of_vol=0.,seed=14)
        self.assertTrue(np.isfinite(h["prices"]).all())
        self.assertTrue(np.isfinite(h["variance"]).all())
        jump=merton_jump_diffusion(100,1,12,100,0.05,0.,0.,0.,0.,seed=14)
        np.testing.assert_allclose(jump[-1],100*np.exp(.05),atol=1e-10)

    def test_normal_student_t_es_not_below_var(self):
        a=gaussian_var_es(0,.04,.975)
        b=student_t_var_es(0,.04,6,.975)
        for x in [a,b]:
            self.assertGreaterEqual(x["expected_shortfall"],x["var"])

    def test_rolling_covariance_weights_drift_and_costs(self):
        rng=np.random.default_rng(77)
        dates=pd.date_range("2010-01-31",periods=55,freq="ME")
        raw=rng.normal(.01,.02,(55,3))
        returns=pd.DataFrame(raw,index=dates,columns=["A","B","C"])
        zero=rolling_covariance_portfolios(returns,train_window=36,
                                           rebalance_every=3,cost_bps=0.)
        paid=rolling_covariance_portfolios(returns,train_window=36,
                                           rebalance_every=3,cost_bps=15.)
        self.assertEqual(len(zero),19)
        for name in ["equal_weight","sample_min_variance",
                     "shrinkage_min_variance","ewma_min_variance"]:
            self.assertAlmostEqual(zero[f"{name}_turnover"].iloc[0],1.,places=7)
            self.assertAlmostEqual(zero[f"{name}_turnover"].iloc[1],0.,places=10)
            self.assertLess(paid[name].iloc[0],zero[name].iloc[0])
            np.testing.assert_allclose(
                zero[name].to_numpy(),zero[f"{name}_gross"].to_numpy(),atol=1e-12)


if __name__=="__main__":
    unittest.main()
