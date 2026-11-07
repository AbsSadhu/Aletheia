"""Backtest numbers checked against answers worked out by hand, not against the code itself."""

from __future__ import annotations

import math

import pytest

from aletheia.extensions.backtest.metrics import (
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)
from aletheia.extensions.backtest.runner import BacktestRunner


def test_one_winning_trade_without_costs() -> None:
    # Buy 10 at 100 (cash 100000 -> 99000), sell 10 at 110 (+1100): final 100100, pnl 100.
    runner = BacktestRunner(initial_capital=100_000.0)
    runner.submit_order("AAA", "market", "buy", 10, price=100.0)
    runner.execute_orders({"AAA": {"close": 100.0}})
    runner.update_equity({"AAA": {"close": 100.0}})
    runner.submit_order("AAA", "market", "sell", 10, price=110.0)
    runner.execute_orders({"AAA": {"close": 110.0}})
    runner.update_equity({"AAA": {"close": 110.0}})
    report = runner.generate_report("hand", "2024-01-01", "2024-01-02")
    assert report.final_capital == pytest.approx(100_100.0)
    assert report.total_return == pytest.approx(0.001)
    assert runner.trades_pnl == [pytest.approx(100.0)]
    assert report.metrics["win_rate"] == 1.0
    assert report.metrics["profit_factor"] is None  # no losing trade: undefined, not infinite


def test_unrealised_position_is_marked_to_the_latest_close() -> None:
    runner = BacktestRunner(initial_capital=10_000.0)
    runner.submit_order("AAA", "market", "buy", 50, price=100.0)  # cost 5000, cash 5000
    runner.execute_orders({"AAA": {"close": 100.0}})
    runner.update_equity({"AAA": {"close": 120.0}})  # 5000 cash + 50 * 120
    assert runner.equity_curve[-1] == pytest.approx(11_000.0)


def test_max_drawdown_is_the_worst_peak_to_trough_fall() -> None:
    # Peak 110, trough 99: (110 - 99) / 110 = 0.1. The later recovery to 121 does not erase it.
    assert calculate_max_drawdown([100, 110, 99, 121]) == pytest.approx(0.1)
    assert calculate_max_drawdown([100, 101, 102]) == 0.0


def test_sharpe_of_known_returns() -> None:
    # Returns 1% and 3%: mean 0.02, population std 0.01, so daily Sharpe 2, annualised 2 * sqrt(252).
    assert calculate_sharpe_ratio([0.01, 0.03]) == pytest.approx(2 * math.sqrt(252))
    assert calculate_sharpe_ratio([0.02, 0.02, 0.02]) == 0.0  # no variance: not a number to trust


def test_win_rate_and_profit_factor() -> None:
    pnl = [100.0, -50.0, 50.0, -25.0]
    assert calculate_win_rate(pnl) == 0.5
    assert calculate_profit_factor(pnl) == pytest.approx(150.0 / 75.0)
