from __future__ import annotations

from aletheia.core.models import MarketQuote, Portfolio, SentinelOutput
from aletheia.core.risk.metrics import assess_portfolio_risk


class SentinelAgent:
    async def assess(self, portfolio: Portfolio, quotes_by_symbol: dict[str, MarketQuote]) -> SentinelOutput:
        return assess_portfolio_risk(portfolio, quotes_by_symbol)


