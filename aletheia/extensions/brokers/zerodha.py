"""
Zerodha Kite Connect Broker API Integration Blueprint.

Provides template code to integrate Aletheia with Zerodha Kite Connect API.
"""
from __future__ import annotations

import logging
from typing import Any
from aletheia.extensions.brokers.base import BaseBrokerConnector

logger = logging.getLogger(__name__)


class ZerodhaKiteConnector(BaseBrokerConnector):
    """
    Blueprint implementation for Zerodha Kite Connect.
    To use this, install the official Kite Connect SDK:
        pip install kiteconnect
    """

    def __init__(self, api_key: str, access_token: str | None = None):
        self.api_key = api_key
        self.access_token = access_token
        self.kite: Any = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            from kiteconnect import KiteConnect
            self.kite = KiteConnect(api_key=self.api_key)
            if self.access_token:
                self.kite.set_access_token(self.access_token)
        except ImportError:
            logger.warning("kiteconnect package not found. Run 'pip install kiteconnect' to use Zerodha.")

    async def get_account_balance(self) -> dict[str, Any]:
        """Fetch cash margins from Zerodha."""
        if not self.kite:
            raise RuntimeError("Kite client not initialized")
        
        # kite.margins() is synchronous; wrap or run direct
        margins = self.kite.margins()
        equity = margins.get("equity", {})
        return {
            "cash": equity.get("net", 0.0),
            "margin_used": equity.get("utilised", 0.0),
            "available_margin": equity.get("available", {}).get("cash", 0.0),
            "currency": "INR"
        }

    async def get_positions(self) -> list[dict[str, Any]]:
        """Fetch open net/day positions."""
        if not self.kite:
            raise RuntimeError("Kite client not initialized")
            
        positions = self.kite.positions()
        net_positions = positions.get("net", [])
        return [
            {
                "symbol": pos["tradingsymbol"],
                "quantity": pos["quantity"],
                "average_price": pos["average_price"],
                "pnl": pos["pnl"],
                "exchange": pos["exchange"],
                "product": pos["product"]  # CNC, MIS, NRML
            }
            for pos in net_positions
        ]

    async def get_orders(self) -> list[dict[str, Any]]:
        """Fetch order book."""
        if not self.kite:
            raise RuntimeError("Kite client not initialized")
            
        orders = self.kite.orders()
        return [
            {
                "order_id": order["order_id"],
                "symbol": order["tradingsymbol"],
                "side": order["transaction_type"],  # BUY / SELL
                "quantity": order["quantity"],
                "status": order["status"],  # COMPLETE, REJECTED, OPEN
                "price": order["price"],
                "exchange": order["exchange"],
                "order_time": str(order["order_timestamp"])
            }
            for order in orders
        ]

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "LIMIT",
        price: float | None = None,
    ) -> dict[str, Any]:
        """
        Place an order on NSE/BSE.
        Parameters map transaction_type and order_type to Zerodha constants.
        """
        if not self.kite:
            raise RuntimeError("Kite client not initialized")
            
        # Side mapping
        side_upper = side.upper()
        tx_type = self.kite.TRANSACTION_TYPE_BUY if side_upper == "BUY" else self.kite.TRANSACTION_TYPE_SELL
        
        # Order type mapping
        type_upper = order_type.upper()
        if type_upper == "MARKET":
            k_type = self.kite.ORDER_TYPE_MARKET
        elif type_upper == "LIMIT":
            k_type = self.kite.ORDER_TYPE_LIMIT
        else:
            k_type = self.kite.ORDER_TYPE_LIMIT

        # Default product as CNC (delivery) for Equities or MIS (intraday)
        product = self.kite.PRODUCT_CNC
        exchange = self.kite.EXCHANGE_NSE

        order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=symbol.upper(),
            transaction_type=tx_type,
            quantity=qty,
            product=product,
            order_type=k_type,
            price=price,
            validity=self.kite.VALIDITY_DAY
        )
        return {"order_id": order_id, "status": "submitted"}

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order by ID."""
        if not self.kite:
            raise RuntimeError("Kite client not initialized")
            
        self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
        return True
