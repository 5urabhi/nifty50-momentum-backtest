"""Validate scalability measurement is synthetic and not hardcoded performance."""
import unittest
from scripts.benchmark_research import benchmark


class ScalabilityBenchTests(unittest.TestCase):
    def test_small_universe_reports_measured_software_timings(self):
        result=benchmark(10,50,seed=71)
        self.assertEqual(result["test_kind"],"synthetic_software_performance_only")
        self.assertEqual(result["assets"],10)
        self.assertEqual(result["security_months"],500)
        self.assertGreater(result["total_seconds"],0)
        self.assertGreater(result["python_peak_tracemalloc_bytes"],0)
        self.assertEqual(result["return_periods"],49)
        self.assertNotIn("strategy_cagr",result)
