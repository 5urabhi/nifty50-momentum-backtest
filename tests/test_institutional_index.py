"""Independent numerical acceptance for institutional-style index optimization."""
import unittest
import numpy as np
import pandas as pd
from index_research.institutional_index import (
    IndexInfeasible, benchmark_asof, optimize_active_index, read_benchmark_history,
)


class InstitutionalIndexTests(unittest.TestCase):
    def setUp(self):
        self.names=pd.Index(["A","B","C","D"])
        self.scores=pd.Series([1.5, .5, -.2, .7],index=self.names)
        self.benchmark=pd.Series([.4,.2,.2,.2],index=self.names)
        self.cov=pd.DataFrame(np.eye(4)*.04,index=self.names,columns=self.names)

    def test_feasible_and_active_risk_accounting(self):
        out=optimize_active_index(self.scores,self.benchmark,self.cov,
                                  max_weight=.4,risk_aversion=2.,
                                  turnover_penalty=.01)
        w=out.weights
        self.assertAlmostEqual(w.sum(),1,places=6)
        self.assertTrue((w>=0).all())
        self.assertTrue((w<=.400001).all())
        expected=float((w-self.benchmark)@self.cov@(w-self.benchmark))
        self.assertAlmostEqual(out.active_variance_annual,expected,places=8)
        self.assertAlmostEqual(out.tracking_error_annual,np.sqrt(expected),places=8)

    def test_exclusion_and_hard_sector_constraints(self):
        selected=self.scores.copy()
        selected["D"]=float("nan")
        labels=pd.Series(["Tech","Tech","Banks","Banks"],index=self.names)
        out=optimize_active_index(selected,self.benchmark,self.cov,
                                  max_weight=.5,risk_aversion=3.,
                                  sector_labels=labels,sector_cap=.6)
        self.assertAlmostEqual(out.weights["D"],0.,places=8)
        self.assertLessEqual(out.weights[["A","B"]].sum(),.600001)
        self.assertLessEqual(out.weights[["C"]].sum(),.600001)

    def test_missing_benchmark_not_silently_inferred(self):
        date=pd.Timestamp("2024-06-30")
        frame=pd.DataFrame({"date":pd.to_datetime(["2024-05-31"]*3),
                            "ticker":["A","B","C"],"weight":[.4,.3,.3]})
        with self.assertRaises(IndexInfeasible):
            benchmark_asof(frame,date,self.names)

    def test_infeasible_security_limit_is_explained(self):
        with self.assertRaisesRegex(IndexInfeasible,"security cap"):
            optimize_active_index(self.scores,self.benchmark,self.cov,max_weight=.2)

    def test_infeasible_sector_concentration_has_diagnostics(self):
        labels=pd.Series(["Tech","Tech","Tech","Tech"],index=self.names)
        with self.assertRaises(IndexInfeasible):
            optimize_active_index(self.scores,self.benchmark,self.cov,
                                  sector_labels=labels,sector_cap=.5)

    def test_variance_uses_annualized_covariance_and_requires_psd(self):
        bad=self.cov.copy()
        bad.iloc[0,0]=-1.
        with self.assertRaisesRegex(ValueError,"non-PSD"):
            optimize_active_index(self.scores,self.benchmark,bad)

    def test_tight_tracking_error_fails_without_fabricating_solution(self):
        selected=self.scores.copy()
        selected["D"]=float("nan")
        # Reference has 20% in D, but D is forbidden, so active TE > zero.
        with self.assertRaises(IndexInfeasible):
            optimize_active_index(selected,self.benchmark,self.cov,
                                  max_weight=.5,tracking_error_limit=.00001)
