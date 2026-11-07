"""Lets the chat agent PROPOSE a paper trade. It never executes anything.

The proposal is stored and shown to the user as a confirm card; only the user's click (the
`/chat/proposals/{id}/execute` endpoint) can place it, through the normal paper-trading path with
its risk limits. News or web text steering the model toward a trade therefore still needs a human.
"""

import asyncio
from typing import Any, ClassVar

from aletheia.core.db.chat_store import ChatStore
from aletheia.core.tools.market_data_tool import load_bars
from aletheia.core.tools.registry import BaseTool

MAX_QUANTITY = 10_000


class ProposePaperOrderTool(BaseTool):
    name: ClassVar[str] = "propose_paper_order"
    auto_register: ClassVar[bool] = False  # needs the chat thread; added per request
    description: ClassVar[str] = (
        "Propose a PAPER (simulated) trade for the user to confirm. Use only when the user "
        "explicitly asks to buy or sell. This does NOT place the order: the user must press "
        "Confirm on a card. Never tell the user an order was placed; say it awaits confirmation."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE/BSE ticker, e.g. RELIANCE."},
            "side": {"type": "string", "enum": ["BUY", "SELL"]},
            "quantity": {"type": "integer", "description": "Number of shares (whole)."},
            "exchange": {"type": "string", "enum": ["NSE", "BSE"], "description": "Default NSE."},
            "order_type": {
                "type": "string",
                "enum": ["MARKET", "LIMIT"],
                "description": "Default MARKET.",
            },
            "limit_price": {"type": "number", "description": "Required for LIMIT orders."},
            "rationale": {
                "type": "string",
                "description": "One sentence on why, shown on the card.",
            },
        },
        "required": ["symbol", "side", "quantity"],
    }

    def __init__(self, store: ChatStore, thread_id: str) -> None:
        self.store = store
        self.thread_id = thread_id

    async def execute(
        self,
        symbol: str,
        side: str,
        quantity: int,
        exchange: str = "NSE",
        order_type: str = "MARKET",
        limit_price: float | None = None,
        rationale: str = "",
        **kwargs: Any,
    ) -> Any:
        side = str(side).upper()
        exchange = str(exchange).upper()
        order_type = str(order_type).upper()
        if side not in ("BUY", "SELL"):
            return {"error": "side must be BUY or SELL."}
        if exchange not in ("NSE", "BSE"):
            return {"error": "Paper orders support NSE or BSE only."}
        try:
            qty = int(quantity)
        except (TypeError, ValueError):
            return {"error": "quantity must be a whole number."}
        if not 0 < qty <= MAX_QUANTITY:
            return {"error": f"quantity must be between 1 and {MAX_QUANTITY}."}
        if order_type == "LIMIT" and not (limit_price and limit_price > 0):
            return {"error": "A LIMIT order needs a positive limit_price."}
        if order_type not in ("MARKET", "LIMIT"):
            return {"error": "order_type must be MARKET or LIMIT."}

        clean = symbol.strip().upper().removesuffix(".NS").removesuffix(".BO")
        loaded = await asyncio.to_thread(load_bars, clean, exchange, "5d", "1d")
        if "error" in loaded:
            return {"error": f"Could not price {clean} on {exchange}, so no order was proposed."}
        reference = float(loaded["bars"][-1]["close"])
        price = float(limit_price) if order_type == "LIMIT" and limit_price else reference

        order = {
            "symbol": clean,
            "exchange": exchange,
            "side": side,
            "quantity": qty,
            "order_type": order_type,
            "limit_price": float(limit_price) if order_type == "LIMIT" and limit_price else None,
        }
        display = {
            "type": "proposal",
            "symbol": clean,
            "exchange": exchange,
            "side": side,
            "quantity": qty,
            "order_type": order_type,
            "limit_price": order["limit_price"],
            "reference_price": round(reference, 2),
            "estimated_value": round(price * qty, 2),
            "currency": loaded["currency"],
            "rationale": rationale.strip()[:300],
        }
        proposal_id = self.store.create_proposal(self.thread_id, order, display)
        return {
            "proposal_id": proposal_id,
            "status": "awaiting_user_confirmation",
            "summary": f"{side} {qty} {clean} ({order_type}) at about {price:.2f} {loaded['currency']}",
            "instruction": "Tell the user the order is waiting for their confirmation on the card. "
            "Do not say it was placed.",
            "_display": {**display, "proposal_id": proposal_id},
        }
