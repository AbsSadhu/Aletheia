"""
Statistical Validation for backtests:
  - Monte Carlo simulation (bootstrap)
  - Walk-Forward validation
  - Permutation test
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class MonteCarloResult:
    n_simulations: int
    median_sharpe: float
    sharpe_ci_low: float
    sharpe_ci_high: float
    median_max_drawdown: float
    drawdown_ci_low: float
    drawdown_ci_high: float
    unstable: bool
    comment: str = ""


@dataclass
class WalkForwardResult:
    n_folds: int
    is_sharpe: float  # in-sample Sharpe
    oos_sharpe: float  # out-of-sample Sharpe
    degradation_pct: float  # how much OOS degrades vs IS
    overfit_warning: bool
    fold_results: list[dict[str, float]] = field(default_factory=list)
    comment: str = ""


@dataclass
class PermutationResult:
    observed_sharpe: float
    permuted_sharpes: list[float]
    p_value: float
    is_real_edge: bool


def run_monte_carlo(
    returns: pd.Series,
    n_simulations: int = 1000,
    block_size: int = 20,
) -> MonteCarloResult:
    """
    Bootstrap Monte Carlo: resample returns with replacement (block bootstrap),
    compute metrics 1000x, report median and 95% CI.

    Block bootstrap (block_size=20 trading days ~1 month) preserves
    autocorrelation structure in returns.
    """
    from aletheia.core.risk.metrics import compute_sharpe, compute_max_drawdown

    clean = returns.dropna()
    n = len(clean)
    if n < 30:
        return MonteCarloResult(
            n_simulations=0,
            median_sharpe=0.0,
            sharpe_ci_low=0.0,
            sharpe_ci_high=0.0,
            median_max_drawdown=0.0,
            drawdown_ci_low=0.0,
            drawdown_ci_high=0.0,
            unstable=True,
            comment="Insufficient data for Monte Carlo (need ≥30 periods)",
        )

    rng = np.random.default_rng(seed=42)
    sharpes: list[float] = []
    drawdowns: list[float] = []

    for _ in range(n_simulations):
        # Block bootstrap
        n_blocks = n // block_size + 1
        start_indices = rng.integers(0, max(1, n - block_size), size=n_blocks)
        sim_returns = pd.concat(
            [clean.iloc[start : start + block_size] for start in start_indices]
        ).iloc[:n]
        sim_returns.index = range(len(sim_returns))

        sharpes.append(compute_sharpe(sim_returns))
        drawdowns.append(compute_max_drawdown(sim_returns))

    sharpe_arr = np.array(sharpes)
    dd_arr = np.array(drawdowns)

    sharpe_std = float(np.std(sharpe_arr))
    unstable = sharpe_std > 0.5  # CI is wide → unstable edge

    return MonteCarloResult(
        n_simulations=n_simulations,
        median_sharpe=round(float(np.median(sharpe_arr)), 4),
        sharpe_ci_low=round(float(np.percentile(sharpe_arr, 2.5)), 4),
        sharpe_ci_high=round(float(np.percentile(sharpe_arr, 97.5)), 4),
        median_max_drawdown=round(float(np.median(dd_arr)), 4),
        drawdown_ci_low=round(float(np.percentile(dd_arr, 2.5)), 4),
        drawdown_ci_high=round(float(np.percentile(dd_arr, 97.5)), 4),
        unstable=unstable,
        comment=(
            f"Sharpe CI width={sharpe_std * 2:.2f} — edge is {'UNSTABLE' if unstable else 'stable'}"
        ),
    )


def run_walk_forward(
    returns: pd.Series,
    n_folds: int = 5,
    train_pct: float = 0.6,
) -> WalkForwardResult:
    """
    Rolling walk-forward: repeatedly train on 60% window, test on next 20%.

    Since we're evaluating pre-computed returns (not fitting a model),
    we just compare IS vs OOS Sharpe ratios across folds.
    """
    from aletheia.core.risk.metrics import compute_sharpe

    clean = returns.dropna()
    n = len(clean)
    fold_size = n // n_folds if n_folds > 0 else n

    if fold_size < 10:
        return WalkForwardResult(
            n_folds=0,
            is_sharpe=0.0,
            oos_sharpe=0.0,
            degradation_pct=0.0,
            overfit_warning=True,
            comment="Insufficient data for walk-forward",
        )

    is_sharpes: list[float] = []
    oos_sharpes: list[float] = []
    fold_results: list[dict[str, float]] = []

    for i in range(n_folds):
        start = i * fold_size
        end = start + fold_size
        if end >= n:
            break

        is_end = start + int(fold_size * train_pct)
        is_returns = clean.iloc[start:is_end]
        oos_returns = clean.iloc[is_end:end]

        is_s = compute_sharpe(is_returns)
        oos_s = compute_sharpe(oos_returns)
        is_sharpes.append(is_s)
        oos_sharpes.append(oos_s)
        fold_results.append({"fold": i, "is_sharpe": round(is_s, 4), "oos_sharpe": round(oos_s, 4)})

    avg_is = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    avg_oos = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
    degradation = ((avg_is - avg_oos) / abs(avg_is) * 100) if avg_is != 0 else 0.0

    return WalkForwardResult(
        n_folds=len(is_sharpes),
        is_sharpe=round(avg_is, 4),
        oos_sharpe=round(avg_oos, 4),
        degradation_pct=round(degradation, 2),
        overfit_warning=degradation > 30.0,
        fold_results=fold_results,
    )


def run_permutation_test(
    returns: pd.Series,
    n_permutations: int = 1000,
) -> PermutationResult:
    """
    Permutation test: shuffle returns and recompute Sharpe 1000x.
    If observed Sharpe > 95th percentile of permuted Sharpe → edge is real.
    """
    from aletheia.core.risk.metrics import compute_sharpe

    clean = returns.dropna()
    observed_sharpe = compute_sharpe(clean)
    rng = np.random.default_rng(seed=99)

    permuted_sharpes: list[float] = []
    for _ in range(n_permutations):
        shuffled = pd.Series(rng.permutation(clean.values))
        permuted_sharpes.append(compute_sharpe(shuffled))

    p95 = float(np.percentile(permuted_sharpes, 95))
    perm_arr = np.array(permuted_sharpes)
    p_value = float((perm_arr >= observed_sharpe).mean())

    return PermutationResult(
        observed_sharpe=round(observed_sharpe, 4),
        permuted_sharpes=[round(s, 4) for s in permuted_sharpes[:20]],  # store sample
        p_value=round(p_value, 4),
        is_real_edge=observed_sharpe > p95,
    )
