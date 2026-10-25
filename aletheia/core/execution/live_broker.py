"""The only path by which Aletheia sends a real order to a broker.

Every check below must pass, in order, or the order is rejected *before* any network call and
the rejection is recorded. Nothing here is advisory:

  1. `live_trading_enabled` setting (off by default)
  2. API-key auth is configured (an open local API must never be able to move money)
  3. execution gate: mode == LIVE, not paused
  4. explicit per-order `confirm`
  5. hard caps: whole-share quantity, max quantity, max order value (INR), max orders per day
  6. delivery-only (CNC) equity on NSE/BSE; MARKET orders need a caller-supplied reference
     price so the value cap can actually be enforced
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from aletheia.core.execution.live_gate import LiveExecutionGate
from aletheia.core.execution.models import ExecutionMode, OrderRequest
from aletheia.core.execution.storage import ExecutionStorage

logger = logging.getLogger(__name__)

ConnectorFactory = Callable[[], Awaitable[Any]]
_IST = timedelta(hours=5, minutes=30)


class LiveOrderRejected(Exception):
    """The order failed a safety check and was NOT sent to the broker."""


class LiveBroker:
    def __init__(
        self,
        gate: LiveExecutionGate,
        storage: ExecutionStorage,
        settings: Any,
        connector_factory: ConnectorFactory,
    ) -> None:
        self.gate = gate
        self.storage = storage
        self.settings = settings
        self._connector_factory = connector_factory

    def _check(self, order: OrderRequest, reference_price: float | None, confirm: bool) -> float:
        s = self.settings
        if not s.live_trading_enabled:
            raise LiveOrderRejected("Live trading is disabled (ALETHEIA_LIVE_TRADING_ENABLED).")
        if not s.api_keys:
            raise LiveOrderRejected("Live orders require ALETHEIA_API_KEYS to be configured.")
        try:
            self.gate.assert_order_allowed(ExecutionMode.LIVE)
        except PermissionError as exc:
            raise LiveOrderRejected(str(exc)) from exc
        if not confirm:
            raise LiveOrderRejected("Each live order needs confirm=true.")

        if order.side.upper() not in ("BUY", "SELL"):
            raise LiveOrderRejected("side must be BUY or SELL.")
        if order.exchange.upper() not in ("NSE", "BSE"):
            raise LiveOrderRejected("Only NSE/BSE equities can be traded live.")
        if order.order_type.upper() not in ("MARKET", "LIMIT"):
            raise LiveOrderRejected("order_type must be MARKET or LIMIT.")
        if order.quantity != int(order.quantity) or order.quantity < 1:
            raise LiveOrderRejected("Quantity must be a whole number of shares.")
        if order.quantity > s.live_max_order_qty:
            raise LiveOrderRejected(f"Quantity exceeds the cap of {s.live_max_order_qty}.")

        price = order.limit_price if order.order_type.upper() == "LIMIT" else reference_price
        if not price or price <= 0:
            raise LiveOrderRejected(
                "A price (limit_price, or reference_price for MARKET) is required."
            )
        value = price * order.quantity
        if value > s.live_max_order_value:
            raise LiveOrderRejected(
                f"Order value INR {value:,.0f} exceeds the cap of INR {s.live_max_order_value:,.0f}."
            )

        ist_now = datetime.now(UTC) + _IST
        ist_midnight_utc = ist_now.replace(hour=0, minute=0, second=0, microsecond=0) - _IST
        if self.storage.count_live_orders_since(ist_midnight_utc) >= s.live_max_orders_per_day:
            raise LiveOrderRejected(
                f"Daily cap of {s.live_max_orders_per_day} live orders reached."
            )
        return price

    async def place(
        self, order: OrderRequest, *, confirm: bool, reference_price: float | None = None
    ) -> dict[str, Any]:
        ref = str(uuid4())
        now = datetime.now(UTC)
        side, otype = order.side.upper(), order.order_type.upper()

        def _record(status: str, price: float | None, broker_id: str | None, detail: str) -> None:
            self.storage.record_live_order(
                ref, now, order.symbol.upper(), order.exchange.upper(), side,
                int(order.quantity), otype, price, status, broker_id, detail,
            )  # fmt: skip

        try:
            price = self._check(order, reference_price, confirm)
        except LiveOrderRejected as exc:
            _record("rejected", order.limit_price, None, str(exc))
            raise

        try:
            connector = await self._connector_factory()
            result = await connector.place_order(
                symbol=order.symbol,
                side=side,
                qty=int(order.quantity),
                order_type=otype,
                price=order.limit_price if otype == "LIMIT" else None,
                exchange=order.exchange,
            )
        except Exception as exc:
            _record("failed", price, None, str(exc))
            logger.error("Live order %s failed at the broker: %s", ref, exc)
            raise

        _record("submitted", price, result.get("order_id"), "")
        logger.warning(
            "LIVE ORDER submitted: %s %s x%d %s (broker id %s, ref %s)",
            side, order.symbol.upper(), int(order.quantity), otype, result.get("order_id"), ref,
        )  # fmt: skip
        return {"order_ref": ref, **result}
