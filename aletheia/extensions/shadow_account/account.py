from __future__ import annotations

import logging
from uuid import uuid4

from aletheia.core.marketdata.engine import MarketDataEngine
from aletheia.core.marketdata.models import MarketDataRequest
from aletheia.extensions.shadow_account.models import AccountSnapshot, TradeEntry, VirtualPosition
from aletheia.extensions.shadow_account.storage import ShadowAccountStorage

logger = logging.getLogger(__name__)


class ShadowAccount:
    """Virtual position/order manager backed by SQLite (execution.sqlite3)."""

    def __init__(
        self,
        storage: ShadowAccountStorage,
        market_data: MarketDataEngine,
        starting_cash: float = 1_000_000.0,
    ) -> None:
        self.storage = storage
        self.market_data = market_data
        self.starting_cash = starting_cash

    def _positions_from_trades(self, trades: list[TradeEntry]) -> dict[str, VirtualPosition]:
        positions: dict[str, VirtualPosition] = {}
        for trade in trades:
            pos = positions.get(trade.symbol)
            if trade.action == "buy":
                if pos is None:
                    positions[trade.symbol] = VirtualPosition(
                        symbol=trade.symbol,
                        quantity=trade.quantity,
                        average_price=trade.price,
                    )
                else:
                    total_cost = pos.quantity * pos.average_price + trade.quantity * trade.price
                    new_qty = pos.quantity + trade.quantity
                    pos.quantity = new_qty
                    pos.average_price = total_cost / new_qty if new_qty else 0.0
            elif trade.action == "sell" and pos is not None:
                remaining = pos.quantity - trade.quantity
                if remaining <= 0:
                    positions.pop(trade.symbol, None)
                else:
                    pos.quantity = remaining
        return positions

    async def execute_virtual_order(
        self, symbol: str, exchange: str, action: str, quantity: float
    ) -> TradeEntry:
        """Execute a virtual BUY/SELL against the live market quote and persist it."""
        action = action.lower()
        if action not in {"buy", "sell"}:
            raise ValueError(f"Unsupported action: {action}")

        quote = await self.market_data.get_quote(
            MarketDataRequest(symbol=symbol, exchange=exchange)
        )
        trade = TradeEntry(
            id=str(uuid4()),
            symbol=symbol.upper(),
            action=action,
            quantity=quantity,
            price=quote.close,
        )
        self.storage.log_trade(trade)
        await self._snapshot()
        return trade

    async def _snapshot(self) -> AccountSnapshot:
        trades = self.storage.get_trades()
        positions = self._positions_from_trades(trades)

        cash = self.starting_cash
        realized_pnl_by_symbol: dict[str, float] = {}
        running_qty: dict[str, float] = {}
        running_avg: dict[str, float] = {}
        for trade in trades:
            if trade.action == "buy":
                cash -= trade.quantity * trade.price
                prev_qty = running_qty.get(trade.symbol, 0.0)
                prev_avg = running_avg.get(trade.symbol, 0.0)
                new_qty = prev_qty + trade.quantity
                running_avg[trade.symbol] = (
                    (prev_qty * prev_avg + trade.quantity * trade.price) / new_qty
                    if new_qty
                    else 0.0
                )
                running_qty[trade.symbol] = new_qty
            else:
                cash += trade.quantity * trade.price
                avg = running_avg.get(trade.symbol, trade.price)
                realized_pnl_by_symbol[trade.symbol] = (
                    realized_pnl_by_symbol.get(trade.symbol, 0.0)
                    + (trade.price - avg) * trade.quantity
                )
                running_qty[trade.symbol] = running_qty.get(trade.symbol, 0.0) - trade.quantity

        for symbol, pos in positions.items():
            try:
                quote = await self.market_data.get_quote(
                    MarketDataRequest(symbol=symbol, exchange="NSE")
                )
                pos.current_price = quote.close
            except Exception:
                pos.current_price = pos.average_price
            pos.unrealized_pnl = (pos.current_price - pos.average_price) * pos.quantity

        holdings_value = sum(p.quantity * p.current_price for p in positions.values())
        snapshot = AccountSnapshot(
            total_equity=cash + holdings_value,
            cash_balance=cash,
            positions=list(positions.values()),
        )
        self.storage.save_snapshot(snapshot)
        return snapshot

    def list_positions(self) -> list[VirtualPosition]:
        snapshot = self.storage.get_latest_snapshot()
        return snapshot.positions if snapshot else []

    def list_orders(self, limit: int = 100) -> list[TradeEntry]:
        trades = sorted(self.storage.get_trades(), key=lambda t: t.timestamp, reverse=True)
        return trades[:limit]

    def equity_curve(self, limit: int = 200) -> list[AccountSnapshot]:
        return self.storage.list_snapshots(limit=limit)
