"""Research utilities for transparent, reproducible equity-index experiments."""
from .core import (
    BacktestResult,
    equal_weight_top_n,
    momentum_scores,
    run_monthly_backtest,
    summary_metrics,
)
__all__ = ["BacktestResult", "equal_weight_top_n", "momentum_scores", "run_monthly_backtest", "summary_metrics"]
