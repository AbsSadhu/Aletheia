"""Regression test for a real contract-violation bug: StrategySignal.quantity
documents `None` as meaning "caller (the backtest router) sizes the
position" (aletheia/extensions/backtest/strategy.py), but the router
treated a falsy/None quantity as "drop this signal" instead -- any plugin
strategy following the documented contract got every signal silently
dropped, zero trades, no error.
"""

from unittest.mock import MagicMock

from aletheia.core.api.routers.backtest import resolve_signal_quantity
from aletheia.extensions.backtest.models import Position
from aletheia.extensions.backtest.strategy import StrategySignal


def _fake_runner(capital: float, positions: dict) -> MagicMock:
    runner = MagicMock()
    runner.current_capital = capital
    runner.positions = positions
    return runner


def test_buy_signal_with_none_quantity_gets_sized_not_dropped() -> None:
    signal = StrategySignal(symbol="AAA", action="buy", quantity=None)
    runner = _fake_runner(capital=100_000.0, positions={})

    quantity = resolve_signal_quantity(signal, price=100.0, runner=runner)

    assert quantity > 0
    # Must not silently default to spending all capital either.
    assert quantity < 100_000.0 / 100.0


def test_sell_signal_with_none_quantity_sells_full_held_position() -> None:
    held = Position(symbol="AAA", quantity=37, average_entry_price=90.0, current_price=100.0)
    signal = StrategySignal(symbol="AAA", action="sell", quantity=None)
    runner = _fake_runner(capital=100_000.0, positions={"AAA": held})

    quantity = resolve_signal_quantity(signal, price=100.0, runner=runner)

    assert quantity == 37


def test_sell_signal_with_none_quantity_and_no_held_position_is_zero() -> None:
    signal = StrategySignal(symbol="AAA", action="sell", quantity=None)
    runner = _fake_runner(capital=100_000.0, positions={})

    quantity = resolve_signal_quantity(signal, price=100.0, runner=runner)

    assert quantity == 0


def test_explicit_quantity_is_used_as_is() -> None:
    signal = StrategySignal(symbol="AAA", action="buy", quantity=12)
    runner = _fake_runner(capital=100_000.0, positions={})

    quantity = resolve_signal_quantity(signal, price=100.0, runner=runner)

    assert quantity == 12
