"""
Base Broker Connector interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseBrokerConnector(ABC):
    """
    Standard interface for broker integrations. All custom broker connectors
    (e.g., Zerodha, TradingView, Interactive Brokers) should implement this.
    """

    @abstractmethod
    async def get_account_balance(self) -> dict[str, Any]:
        """
        Fetch account cash, equity values, margin, and currency.
        """
        pass

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """
        Fetch active open positions.
        """
        pass

    @abstractmethod
    async def get_orders(self) -> list[dict[str, Any]]:
        """
        Fetch order history for the day or recent orders.
        """
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        qty: int,
        order_type: str = "LIMIT",  # "MARKET", "LIMIT", "SL-M"
        price: float | None = None,
    ) -> dict[str, Any]:
        """
        Place an order with the broker. Returns the order confirmation payload.
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an outstanding pending order. Returns True if successful.
        """
        pass
