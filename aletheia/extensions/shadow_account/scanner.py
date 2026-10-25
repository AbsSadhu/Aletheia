from __future__ import annotations

import logging

from aletheia.core.execution.guard import ExecutionGuard, RiskLimitExceeded
from aletheia.core.models import OracleOutput
from aletheia.extensions.shadow_account.account import ShadowAccount

logger = logging.getLogger(__name__)


class EntryExitScanner:
    """Turns Oracle signals into virtual orders, sized and limited by the ExecutionGuard."""

    def __init__(
        self,
        account: ShadowAccount,
        min_confidence: float = 0.6,
        guard: ExecutionGuard | None = None,
    ) -> None:
        self.account = account
        self.min_confidence = min_confidence
        self.guard = guard or account.guard or ExecutionGuard()

    async def scan(self, oracle_outputs: list[OracleOutput], exchange: str = "NSE") -> list[dict]:
        executed: list[dict] = []
        for output in oracle_outputs:
            if output.data_quality != "ok" or output.confidence < self.min_confidence:
                continue
            equity, cash, held = self.account.account_state()
            symbol = output.symbol

            try:
                if output.signal == "BUY" and symbol not in held:
                    price = await self.account.quote_price(symbol, exchange)
                    qty = self.guard.size_buy(price, equity, output.stop_loss_price)
                    if qty < 1:
                        executed.append({"symbol": symbol, "skipped": "position size rounds to 0"})
                        continue
                    trade = await self.account.execute_virtual_order(symbol, exchange, "buy", qty)
                    executed.append(
                        {
                            "symbol": symbol,
                            "action": "buy",
                            "qty": trade.quantity,
                            "trade_id": trade.id,
                        }
                    )
                elif output.signal == "REDUCE" and symbol in held:
                    trade = await self.account.execute_virtual_order(
                        symbol, exchange, "sell", held[symbol]
                    )
                    executed.append(
                        {
                            "symbol": symbol,
                            "action": "sell",
                            "qty": trade.quantity,
                            "trade_id": trade.id,
                        }
                    )
            except RiskLimitExceeded as exc:
                logger.info("Shadow scan skipped %s: %s", symbol, exc)
                executed.append({"symbol": symbol, "skipped": str(exc)})

        return executed
