"""User-authored strategy contract for the backtest engine.

`Strategy.on_bar` is pure and synchronous by design: it takes the current
day's market snapshot plus the runner's live position/capital state, and
returns zero or more signals — no direct access to order execution, I/O, or
the event loop. That keeps the same contract usable unchanged from
`BacktestRunner` today and from a live LangGraph agent node later; promoting
a strategy to live trading only needs a new caller wrapping `on_bar`, not a
new interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from aletheia.extensions.backtest.models import Position


@dataclass
class StrategySignal:
    symbol: str
    action: str  # "buy" | "sell"
    quantity: float | None = None  # None: caller (the backtest router) sizes the position


class Strategy(ABC):
    name: str

    @abstractmethod
    def on_bar(
        self,
        date: str,
        market_data: dict[str, dict[str, float]],
        positions: dict[str, Position],
        capital: float,
    ) -> list[StrategySignal]:
        """Called once per trading day with that day's OHLCV snapshot for
        every symbol in the backtest, the runner's current open positions,
        and available capital. Return a signal per symbol you want to act
        on; returning nothing is a valid "hold" for that day.
        """
        raise NotImplementedError
