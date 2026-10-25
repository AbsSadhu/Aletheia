"""Zerodha Kite Connect: OAuth login and order/portfolio access over the documented REST API.

Talks HTTPS directly (no `kiteconnect` SDK needed). Login flow:
  1. `login_url(api_key)` -> user logs in on kite.zerodha.com
  2. Kite redirects to the app's registered redirect URL with `request_token`
  3. `exchange_request_token()` POSTs /session/token with sha256(api_key+request_token+secret)
  4. The returned `access_token` is valid until ~6 AM IST the next day, then step 1 repeats.

This module only *talks to* the broker. Whether an order may be sent at all is decided by
`aletheia.core.execution.live_broker`, never here.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from aletheia.extensions.brokers.base import BaseBrokerConnector

logger = logging.getLogger(__name__)

ROOT = "https://api.kite.trade"
LOGIN_URL = "https://kite.zerodha.com/connect/login"


class KiteAuthError(RuntimeError):
    """Token missing/expired or login rejected — the user must log in again."""


def login_url(api_key: str, state: str | None = None) -> str:
    url = f"{LOGIN_URL}?v=3&api_key={api_key}"
    if state:
        # Kite echoes redirect_params back on the callback, which is how we carry a CSRF nonce.
        from urllib.parse import quote

        url += "&redirect_params=" + quote(f"state={state}")
    return url


async def exchange_request_token(
    api_key: str,
    api_secret: str,
    request_token: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    checksum = hashlib.sha256((api_key + request_token + api_secret).encode("utf-8")).hexdigest()
    own = client is None
    http = client or httpx.AsyncClient(base_url=ROOT, timeout=15.0)
    try:
        resp = await http.post(
            "/session/token",
            headers={"X-Kite-Version": "3"},
            data={"api_key": api_key, "request_token": request_token, "checksum": checksum},
        )
        body = resp.json()
    finally:
        if own:
            await http.aclose()
    if body.get("status") != "success" or not body.get("data", {}).get("access_token"):
        raise KiteAuthError(body.get("message") or "Kite rejected the request token.")
    session: dict[str, Any] = body["data"]
    return session


class ZerodhaKiteConnector(BaseBrokerConnector):
    def __init__(
        self,
        api_key: str,
        access_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.api_key = api_key
        self.access_token = access_token
        self._client = client

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.access_token:
            raise KiteAuthError("No Kite access token; log in to Zerodha first.")
        http = self._client or httpx.AsyncClient(base_url=ROOT, timeout=15.0)
        try:
            resp = await http.request(
                method,
                path,
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {self.api_key}:{self.access_token}",
                },
                **kwargs,
            )
            body = resp.json()
        finally:
            if self._client is None:
                await http.aclose()
        if body.get("status") != "success":
            if body.get("error_type") == "TokenException":
                raise KiteAuthError(body.get("message") or "Kite token expired.")
            raise RuntimeError(f"Kite {method} {path} failed: {body.get('message')}")
        return body["data"]

    async def get_account_balance(self) -> dict[str, Any]:
        equity = (await self._request("GET", "/user/margins")).get("equity", {})
        return {
            "cash": equity.get("net", 0.0),
            "margin_used": equity.get("utilised", {}).get("debits", 0.0),
            "available_margin": equity.get("available", {}).get("cash", 0.0),
            "currency": "INR",
        }

    async def get_holdings(self) -> list[dict[str, Any]]:
        """Delivery (CNC) holdings — what a long-term portfolio sync actually wants."""
        return [
            {
                "symbol": h["tradingsymbol"],
                "quantity": h["quantity"] + h.get("t1_quantity", 0),
                "average_price": h["average_price"],
                "pnl": h.get("pnl", 0.0),
                "exchange": h["exchange"],
            }
            for h in await self._request("GET", "/portfolio/holdings")
        ]

    async def get_positions(self) -> list[dict[str, Any]]:
        net = (await self._request("GET", "/portfolio/positions")).get("net", [])
        return [
            {
                "symbol": p["tradingsymbol"],
                "quantity": p["quantity"],
                "average_price": p["average_price"],
                "pnl": p["pnl"],
                "exchange": p["exchange"],
                "product": p["product"],
            }
            for p in net
        ]

    async def get_orders(self) -> list[dict[str, Any]]:
        return [
            {
                "order_id": o["order_id"],
                "symbol": o["tradingsymbol"],
                "side": o["transaction_type"],
                "quantity": o["quantity"],
                "status": o["status"],
                "price": o["price"],
                "exchange": o["exchange"],
                "order_time": str(o["order_timestamp"]),
            }
            for o in await self._request("GET", "/orders")
        ]

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "LIMIT",
        price: float | None = None,
        exchange: str = "NSE",
    ) -> dict[str, Any]:
        order_type = order_type.upper()
        if order_type not in ("MARKET", "LIMIT"):
            raise ValueError(f"Unsupported order type {order_type!r}; use MARKET or LIMIT.")
        if order_type == "LIMIT" and not price:
            raise ValueError("LIMIT orders need a price.")
        form: dict[str, Any] = {
            "exchange": exchange.upper(),
            "tradingsymbol": symbol.upper(),
            "transaction_type": side.upper(),
            "quantity": int(qty),
            "product": "CNC",  # delivery only; no intraday/margin products
            "order_type": order_type,
            "validity": "DAY",
        }
        if order_type == "LIMIT":
            form["price"] = price
        data = await self._request("POST", "/orders/regular", data=form)
        return {"order_id": data["order_id"], "status": "submitted"}

    async def cancel_order(self, order_id: str) -> bool:
        await self._request("DELETE", f"/orders/regular/{order_id}")
        return True
