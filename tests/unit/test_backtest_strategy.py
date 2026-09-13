import pytest

from aletheia.extensions.backtest.strategies import (
    SMACrossoverStrategy,
    available_strategies,
    get_strategy,
    register_strategy,
)
from aletheia.extensions.backtest.strategy import Strategy, StrategySignal


def test_get_strategy_returns_registered_builtin() -> None:
    strategy = get_strategy("sma_crossover")
    assert isinstance(strategy, SMACrossoverStrategy)


def test_get_strategy_unknown_name_raises_with_available_list() -> None:
    with pytest.raises(ValueError, match="sma_crossover"):
        get_strategy("does_not_exist")


def test_sma_crossover_buys_on_uptrend_then_sells_on_downtrend() -> None:
    strategy = SMACrossoverStrategy(fast=2, slow=4, position_pct=10.0)
    positions: dict = {}
    capital = 100_000.0

    # Rising prices: fast average should cross above slow average.
    prices = [100, 101, 103, 106, 110, 115]
    buy_signal = None
    for i, price in enumerate(prices):
        signals = strategy.on_bar(f"day-{i}", {"AAA": {"close": price}}, positions, capital)
        if signals:
            buy_signal = signals[0]
            positions["AAA"] = _fake_position("AAA", buy_signal.quantity, price)
            break

    assert buy_signal is not None
    assert buy_signal.action == "buy"
    assert buy_signal.quantity and buy_signal.quantity > 0

    # Falling prices thereafter: fast average should cross back below slow,
    # producing a sell signal for the full held quantity.
    falling_prices = [110, 100, 90, 80, 70]
    sell_signal = None
    for i, price in enumerate(falling_prices):
        signals = strategy.on_bar(f"down-{i}", {"AAA": {"close": price}}, positions, capital)
        if signals:
            sell_signal = signals[0]
            break

    assert sell_signal is not None
    assert sell_signal.action == "sell"
    assert sell_signal.quantity == positions["AAA"].quantity


def test_sma_crossover_respects_position_pct_not_full_capital() -> None:
    """Regression guard: compute_shares() must receive portfolio_value=capital
    so `pct` actually scales the allocation -- omitting it silently sizes
    every buy at 100% of capital regardless of position_pct."""
    strategy = SMACrossoverStrategy(fast=2, slow=4, position_pct=10.0)
    positions: dict = {}
    capital = 100_000.0

    prices = [100, 101, 103, 106, 110, 115]
    buy_signal = None
    last_price = None
    for i, price in enumerate(prices):
        signals = strategy.on_bar(f"day-{i}", {"AAA": {"close": price}}, positions, capital)
        if signals:
            buy_signal = signals[0]
            last_price = price
            break

    assert buy_signal is not None
    assert buy_signal.quantity is not None
    max_shares_at_full_capital = int(capital / last_price)
    max_shares_at_10pct = int((capital * 0.10) / last_price)
    assert buy_signal.quantity <= max_shares_at_10pct
    assert buy_signal.quantity < max_shares_at_full_capital


def test_register_strategy_adds_a_custom_strategy() -> None:
    class _NoOpStrategy(Strategy):
        name = "noop_test_strategy"

        def on_bar(self, date, market_data, positions, capital) -> list[StrategySignal]:
            return []

    register_strategy(_NoOpStrategy.name, _NoOpStrategy)
    try:
        assert "noop_test_strategy" in available_strategies()
        assert isinstance(get_strategy("noop_test_strategy"), _NoOpStrategy)
    finally:
        from aletheia.extensions.backtest.strategies import _STRATEGY_REGISTRY

        _STRATEGY_REGISTRY.pop("noop_test_strategy", None)


def _fake_position(symbol: str, quantity: float, price: float):
    from aletheia.extensions.backtest.models import Position

    return Position(
        symbol=symbol, quantity=quantity, average_entry_price=price, current_price=price
    )
