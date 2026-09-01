from __future__ import annotations

import logging

from aletheia.core.models import OracleOutput
from aletheia.extensions.shadow_account.account import ShadowAccount

logger = logging.getLogger(__name__)

_DEFAULT_QTY = 1.0


class EntryExitScanner:
    """Scans Oracle signals and auto-executes virtual orders on ShadowAccount."""

    def __init__(self, account: ShadowAccount, min_confidence: float = 0.6) -> None:
        self.account = account
        self.min_confidence = min_confidence

    async def scan(self, oracle_outputs: list[OracleOutput], exchange: str = "NSE") -> list[dict]:
        executed: list[dict] = []
        open_symbols = {p.symbol for p in self.account.list_positions()}

        for output in oracle_outputs:
            if output.confidence < self.min_confidence:
                continue

            if output.signal == "BUY" and output.symbol not in open_symbols:
                trade = await self.account.execute_virtual_order(
                    output.symbol, exchange, "buy", _DEFAULT_QTY
                )
                executed.append({"symbol": output.symbol, "action": "buy", "trade_id": trade.id})
            elif output.signal == "REDUCE" and output.symbol in open_symbols:
                trade = await self.account.execute_virtual_order(
                    output.symbol, exchange, "sell", _DEFAULT_QTY
                )
                executed.append({"symbol": output.symbol, "action": "sell", "trade_id": trade.id})

        return executed
