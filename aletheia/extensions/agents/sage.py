from __future__ import annotations

from aletheia.extensions.backtest.scenario import build_scenario
from aletheia.core.models import Holding, MarketQuote, OracleOutput, SageOutput


class SageAgent:
    async def backtest(
        self, holding: Holding, quote: MarketQuote, oracle: OracleOutput
    ) -> SageOutput:
        return build_scenario(holding, quote, oracle.confidence)
