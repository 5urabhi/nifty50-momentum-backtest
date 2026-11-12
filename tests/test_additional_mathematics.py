"""Local mathematical verification tests; intentionally NOT GitHub Actions.

Synthetic quantities and exact limit cases only. Empirical market validation,
dashboard QA and benchmarking remain separate user-led local tasks.
"""
import unittest
import numpy as np
import pandas as pd

from index_research.portfolio_theory import (
    optimize_portfolio,risk_contributions,risk_parity,maximum_diversification,efficient_frontier
)
from index_research.statistical_inference import (
    newey_west_ols,regression_with_known_factors,moving_block_bootstrap_mean,
    benjamini_hochberg,cross_sectional_rank_ic,quantile_spread,rolling_time_splits
)
from index_research.tail_risk import (
    gaussian_var_es,student_t_var_es,correlated_gaussian_scenarios,
    portfolio_monte_carlo_risk,historical_scenario_impact,
    parametric_expected_shortfall_backtest,evt_peak_over_threshold
)
from index_research.derivatives import (
    implied_volatility,monte_carlo_european,binomial_option,heston_paths,
    merton_jump_diffusion
)
from index_research.math_models import black_scholes
from index_research.portfolio_extensions import (
    black_litterman_posterior,minimize_historical_cvar,factor_neutralize_scores
)


class AdditionalMathematicsTests(unittest.TestCase):
    def setUp(self):
        self.labels=pd.Index(["A","B","C"])
        self.cov=pd.DataFrame(np.diag([0.01,0.04,0.09]),
                              index=self.labels,columns=self.labels)
        self.b=pd.Series([1/3]*3,index=self.labels)
        self.mu=pd.Series([0.06,0.08,0.12],index=self.labels)

    def test_tracking_error_solution_returns_benchmark(self):
        solution=optimize_portfolio(self.cov,self.mu,self.b,
                                    objective="minimum_tracking_error")
        np.testing.assert_allclose(solution.weights,self.b,atol=1e-5)
        self.assertLess(solution.tracking_error,1e-6)

    def test_active_constraints_and_frontier(self):
        solution=optimize_portfolio(self.cov,self.mu,self.b,
                                    objective="mean_variance",max_weight=0.6,
                                    tracking_error_limit=0.1)
        self.assertLessEqual(solution.tracking_error,0.100001)
        self.assertAlmostEqual(solution.weights.sum(),1,places=6)
        curve=efficient_frontier(self.cov,self.mu,points=5)
        self.assertEqual(len(curve),5)
        self.assertTrue(curve["feasible"].any())

    def test_risk_budget_and_euler_decomposition(self):
        solution=risk_parity(self.cov)
        contributions=risk_contributions(solution.weights,self.cov)
        self.assertAlmostEqual(contributions["volatility_contribution"].sum(),
                               solution.volatility,places=7)
        shares=contributions["share_of_volatility"].to_numpy()
        self.assertLess(np.max(shares)-np.min(shares),1e-3)
        other=maximum_diversification(self.cov)
        self.assertAlmostEqual(other.weights.sum(),1,places=7)

    def test_newey_west_recovers_known_betas(self):
        rng=np.random.default_rng(12)
        index=pd.date_range("2010-01-31",periods=120,freq="ME")
        f=pd.DataFrame({"mkt_rf":rng.normal(size=120),
                        "smb":rng.normal(size=120),
                        "hml":rng.normal(size=120)},index=index)
        y=0.01+1.2*f["mkt_rf"]-0.5*f["smb"]+0.2*f["hml"]+rng.normal(0,0.01,120)
        r=regression_with_known_factors(y,f,model="fama_french_3",lags=3)
        self.assertAlmostEqual(r.coefficients["mkt_rf"],1.2,places=2)
        self.assertEqual(r.observations,120)
        self.assertGreater(r.t_statistics["mkt_rf"],20)

    def test_bootstrap_reproducible_and_bh(self):
        data=pd.Series(np.linspace(-0.02,0.05,120))
        a=moving_block_bootstrap_mean(data,block_length=5,resamples=150,seed=3)
        b=moving_block_bootstrap_mean(data,block_length=5,resamples=150,seed=3)
        self.assertEqual(a,b)
        p=pd.Series([0.001,0.03,0.20])
        q=benjamini_hochberg(p)
        self.assertTrue(np.all(q>=p))
        self.assertAlmostEqual(q.iloc[0],0.003)

    def test_ic_spread_and_time_splits(self):
        idx=pd.date_range("2018-01-31",periods=48,freq="ME")
        columns=list("ABCDE")
        s=pd.DataFrame([np.arange(5)]*48,index=idx,columns=columns)
        r=s/100
        ic=cross_sectional_rank_ic(s,r,minimum_names=5)
        self.assertAlmostEqual(ic.iloc[0],1.0)
        spread=quantile_spread(s,r,minimum_names=5,fraction=0.2)
        self.assertGreater(spread.iloc[0],0)
        folds=rolling_time_splits(idx,train=24,test=6,embargo=1)
        self.assertGreater(len(folds),0)
        self.assertLess(folds[0][0][-1],folds[0][1][0]-1)

    def test_gaussian_t_and_monte_carlo_tail_consistency(self):
        g=gaussian_var_es(0,0.02,0.95)
        t=student_t_var_es(0,0.02,5,0.95)
        self.assertGreaterEqual(g["expected_shortfall"],g["var"])
        self.assertGreaterEqual(t["expected_shortfall"],t["var"])
        sample=correlated_gaussian_scenarios(self.mu,self.cov,draws=500,seed=4)
        self.assertEqual(sample.shape,(500,3))
        mc=portfolio_monte_carlo_risk(self.b,self.mu,self.cov,draws=500,seed=4)
        self.assertGreaterEqual(mc["expected_shortfall"],mc["var"])

    def test_scenarios_and_exceedance_rate(self):
        shock=pd.DataFrame([[-.1,-.2,-.3],[.1,.2,.3]],columns=self.labels)
        effect=historical_scenario_impact(self.b,shock)
        self.assertAlmostEqual(effect["portfolio_return"].iloc[0],-.2)
        idx=pd.date_range("2020-01-31",periods=100,freq="ME")
        r=pd.Series(np.linspace(-.1,.1,100),index=idx)
        var=pd.Series(.05,index=idx)
        test=parametric_expected_shortfall_backtest(r,var)
        self.assertGreaterEqual(test["kupiec_p_value_asymptotic"],0)
        self.assertLessEqual(test["kupiec_p_value_asymptotic"],1)

    def test_evt_can_fit_defined_tail(self):
        rng=np.random.default_rng(44)
        losses=pd.Series(rng.exponential(.02,1000))
        tail=evt_peak_over_threshold(losses,0.90,0.99)
        self.assertGreater(tail["loss_quantile"],tail["threshold"])

    def test_bsm_iv_binomial_mc_consistency(self):
        analytic=black_scholes(100,100,1,.04,.2)["price"]
        sigma=implied_volatility(analytic,100,100,1,.04)
        self.assertAlmostEqual(sigma,.2,places=8)
        euro=binomial_option(100,100,1,.04,.2,steps=400,exercise="european")
        self.assertAlmostEqual(euro,analytic,delta=.04)
        american_put=binomial_option(100,105,1,.04,.2,steps=400,option="put",exercise="american")
        european_put=binomial_option(100,105,1,.04,.2,steps=400,option="put",exercise="european")
        self.assertGreaterEqual(american_put+1e-10,european_put)
        mc=monte_carlo_european(100,100,1,.04,.2,paths=20000,seed=4)
        self.assertLess(abs(mc["price"]-analytic),5*mc["standard_error"]+.1)

    def test_heston_and_jump_limits(self):
        h=heston_paths(100,.04,years=1,steps=5,paths=10,vol_of_vol=0.,seed=2)
        self.assertEqual(h["prices"].shape,(6,10))
        self.assertTrue(np.isfinite(h["prices"]).all())
        j=merton_jump_diffusion(100,1,6,10,0.05,.2,0.,0.,0.,seed=2)
        self.assertEqual(j.shape,(7,10))
        self.assertTrue((j>0).all())

    def test_black_litterman_prior(self):
        p=pd.DataFrame([[1.,-1.,0.]],columns=self.labels,index=["relative_view"])
        q=pd.Series([.02],index=p.index)
        out=black_litterman_posterior(self.cov,self.b,2.,p,q)
        self.assertEqual(out["posterior_expected_returns"].shape,(3,))
        self.assertTrue(np.isfinite(out["posterior_expected_returns"]).all())

    def test_cvar_linear_program(self):
        rng=np.random.default_rng(91)
        returns=pd.DataFrame(rng.normal(0,.02,(120,3)),columns=self.labels)
        result=minimize_historical_cvar(returns,confidence=.95,max_weight=.6)
        self.assertAlmostEqual(result["weights"].sum(),1,places=7)
        self.assertTrue((result["weights"]<=.60001).all())

    def test_neutralization_residual_orthogonal(self):
        exposures=pd.DataFrame({"beta":np.arange(10.)},index=list("ABCDEFGHIJ"))
        scores=pd.Series(np.arange(10.)*2+np.sin(np.arange(10.)),
                         index=exposures.index)
        clean=factor_neutralize_scores(scores,exposures)
        self.assertLess(abs(clean.mean()),1e-9)
        self.assertLess(abs(np.dot(clean,exposures["beta"])),1e-8)


if __name__=="__main__":
    unittest.main()
