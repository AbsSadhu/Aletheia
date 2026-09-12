"""Regression test for a real bug: `POST /backtest` accepted a `strategy`
field but never called it — BacktestRunner.execute_orders() only acts on
orders submitted via runner.submit_order(), and nothing submitted any. Every
backtest silently returned zero trades regardless of which strategy was
requested. This drives the same loop aletheia/core/api/routers/backtest.py
now runs, without needing a live DuckDB-backed HTTP call.
"""

from aletheia.extensions.backtest.runner import BacktestRunner
from aletheia.extensions.backtest.strategies import get_strategy


def test_backtest_loop_actually_submits_and_fills_orders() -> None:
    strategy = get_strategy("sma_crossover")
    runner = BacktestRunner(initial_capital=100_000.0)

    # A clean uptrend long enough to clear the strategy's slow window (20),
    # then a downtrend to force an exit — should produce at least one
    # completed round-trip trade.
    prices = [100 + i for i in range(30)] + [130 - i for i in range(30)]

    for i, price in enumerate(prices):
        day_data = {"AAA": {"close": price}}
        for signal in strategy.on_bar(f"day-{i}", day_data, runner.positions, runner.current_capital):
            if signal.quantity and signal.quantity > 0:
                runner.submit_order(signal.symbol, "market", signal.action, signal.quantity, price=price)
        runner.execute_orders(day_data)
        runner.update_equity(day_data)

    assert len(runner.orders) > 0, "strategy produced no orders at all"
    filled = [o for o in runner.orders if o.status == "filled"]
    assert filled, "no orders were filled"
    assert runner.trades_pnl, "no completed round-trip trades — the bug this test guards against"
