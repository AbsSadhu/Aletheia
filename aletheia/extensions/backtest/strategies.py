"""Built-in strategies plus the registry a plugin (or a user) adds to.

`POST /api/v1/backtest`'s `strategy` field is looked up here by name.
"""

from __future__ import annotations

from aletheia.core.execution.position_sizing import PositionSizer
from aletheia.extensions.backtest.models import Position
from aletheia.extensions.backtest.strategy import Strategy, StrategySignal


class SMACrossoverStrategy(Strategy):
    """Classic fast/slow simple-moving-average crossover: buy when the fast
    average crosses above the slow average, sell when it crosses back below.
    A reference implementation of the Strategy contract, not a claim of
    edge — copy this file's shape to write your own.
    """

    name = "sma_crossover"

    def __init__(self, fast: int = 5, slow: int = 20, position_pct: float = 10.0) -> None:
        self.fast = fast
        self.slow = slow
        self.position_pct = position_pct
        self._history: dict[str, list[float]] = {}

    def on_bar(
        self,
        date: str,
        market_data: dict[str, dict[str, float]],
        positions: dict[str, Position],
        capital: float,
    ) -> list[StrategySignal]:
        signals: list[StrategySignal] = []

        for symbol, bar in market_data.items():
            close = bar.get("close")
            if close is None:
                continue

            history = self._history.setdefault(symbol, [])
            history.append(close)
            if len(history) > self.slow:
                history.pop(0)
            if len(history) < self.slow:
                continue

            fast_avg = sum(history[-self.fast :]) / self.fast
            slow_avg = sum(history) / self.slow
            held = positions.get(symbol)

            if fast_avg > slow_avg and held is None:
                qty = PositionSizer.compute_shares(
                    capital, close, pct=self.position_pct, portfolio_value=capital
                )
                if qty > 0:
                    signals.append(StrategySignal(symbol=symbol, action="buy", quantity=qty))
            elif fast_avg < slow_avg and held is not None:
                signals.append(
                    StrategySignal(symbol=symbol, action="sell", quantity=held.quantity)
                )

        return signals


_STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    SMACrossoverStrategy.name: SMACrossoverStrategy,
}


def register_strategy(name: str, strategy_cls: type[Strategy]) -> None:
    """Called by a plugin's register() to add a strategy `POST /backtest`
    can look up by name."""
    _STRATEGY_REGISTRY[name] = strategy_cls


def get_strategy(name: str) -> Strategy:
    strategy_cls = _STRATEGY_REGISTRY.get(name)
    if strategy_cls is None:
        available = ", ".join(sorted(_STRATEGY_REGISTRY))
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return strategy_cls()


def available_strategies() -> list[str]:
    return sorted(_STRATEGY_REGISTRY)
