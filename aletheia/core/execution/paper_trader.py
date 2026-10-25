from __future__ import annotations

from datetime import UTC, datetime

from aletheia.core.execution.guard import ExecutionGuard, RiskLimitExceeded
from aletheia.core.execution.models import OrderRequest, PaperPosition, PaperTradeResult
from aletheia.core.execution.storage import ExecutionStorage
from aletheia.core.marketdata.engine import MarketDataEngine
from aletheia.core.marketdata.models import MarketDataRequest


class PaperTrader:
    def __init__(
        self,
        storage: ExecutionStorage,
        market_data: MarketDataEngine,
        guard: ExecutionGuard | None = None,
        starting_cash: float = 1_000_000.0,
    ) -> None:
        self.storage = storage
        self.market_data = market_data
        self.guard = guard
        self.starting_cash = starting_cash

    def _account_state(self) -> tuple[float, float]:
        """(equity, cash) at cost: starting cash + realised P&L, less capital tied up in positions."""
        positions = self.storage.list_positions()
        invested = sum(p.quantity * p.average_price for p in positions)
        equity = self.starting_cash + sum(p.realized_pnl for p in positions) + 0.0
        return equity, equity - invested

    async def submit_order(
        self, order: OrderRequest, run_id: str | None = None
    ) -> PaperTradeResult:
        quote = await self.market_data.get_quote(
            MarketDataRequest(symbol=order.symbol, exchange=order.exchange)
        )
        fill_price = order.limit_price or quote.close
        side = order.side.upper()
        position = self.storage.get_position(order.symbol.upper(), order.exchange)
        realized_pnl = 0.0

        if self.guard is not None:
            # Strict: a manual order that breaks a limit is rejected, never silently resized.
            if side == "BUY":
                equity, cash = self._account_state()
                held_value = position.quantity * position.average_price if position else 0.0
                decision = self.guard.check_buy(
                    order.symbol, order.quantity, fill_price, equity, cash, held_value
                )
                if decision.reduced:
                    raise RiskLimitExceeded(
                        f"Order too large; the most allowed right now is {decision.approved_qty} shares.",
                        decision.notes,
                    )
            elif side == "SELL":
                self.guard.check_sell(
                    order.symbol, order.quantity, position.quantity if position else 0.0
                )

        if side == "BUY":
            if position:
                total_cost = (position.quantity * position.average_price) + (
                    order.quantity * fill_price
                )
                new_qty = position.quantity + order.quantity
                position.quantity = new_qty
                position.average_price = total_cost / new_qty
                position.updated_at = datetime.now(UTC)
            else:
                position = PaperPosition(
                    symbol=order.symbol.upper(),
                    exchange=order.exchange,
                    quantity=order.quantity,
                    average_price=fill_price,
                )
            self.storage.upsert_position(position)
        elif side == "SELL":
            if position is None or position.quantity < order.quantity:
                raise ValueError("Cannot sell more than the current paper position.")
            realized_pnl = (fill_price - position.average_price) * order.quantity
            remaining = position.quantity - order.quantity
            if remaining <= 0:
                self.storage.delete_position(order.symbol.upper(), order.exchange)
            else:
                position.quantity = remaining
                position.realized_pnl += realized_pnl
                position.updated_at = datetime.now(UTC)
                self.storage.upsert_position(position)
        else:
            raise ValueError(f"Unsupported order side: {order.side}")

        trade = PaperTradeResult(
            run_id=run_id,
            symbol=order.symbol.upper(),
            exchange=order.exchange,
            side=side,
            recommendation=side,
            simulated_qty=order.quantity,
            simulated_fill_price=fill_price,
            simulated_pnl=realized_pnl,
        )
        self.storage.record_trade(trade)
        return trade

    async def settle_trade(
        self,
        trade_id: str,
        actual_close: float,
    ) -> PaperTradeResult | None:
        """
        Settle a paper trade with the actual market closing price.
        Computes realized P&L delta vs simulated fill, updates trade record.
        """
        trades = self.storage.list_trades(limit=5000)
        trade = next((t for t in trades if t.trade_id == trade_id), None)
        if trade is None:
            return None

        actual_pnl = (actual_close - trade.simulated_fill_price) * trade.simulated_qty
        trade.simulated_pnl = round(actual_pnl, 2)
        trade.status = "settled"
        # Store actual close in metadata via storage update
        self.storage.update_trade_settlement(trade_id, actual_close, actual_pnl)
        return trade

    def get_pending_settlements(
        self,
        cutoff_dt: datetime | None = None,
    ) -> list[PaperTradeResult]:
        """Return BUY trades that haven't been settled yet."""
        if cutoff_dt is None:
            cutoff_dt = datetime.now(UTC)
        trades = self.storage.list_trades(limit=1000)
        return [
            t
            for t in trades
            if t.side == "BUY" and t.status == "filled" and t.timestamp <= cutoff_dt
        ]

    def list_trades(self, limit: int = 50) -> list[PaperTradeResult]:
        return self.storage.list_trades(limit=limit)

    def list_positions(self) -> list[PaperPosition]:
        return self.storage.list_positions()
