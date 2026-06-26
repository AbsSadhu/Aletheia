from __future__ import annotations

from datetime import UTC, datetime

from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.core.models import MarketQuote


SEED_QUOTES: dict[str, float] = {
    "RELIANCE": 2920.0,
    "TCS": 3925.0,
    "INFY": 1612.0,
    "HDFCBANK": 1748.0,
    "ICICIBANK": 1184.0,
    "SBIN": 846.0,
    "BTC/USDT": 65200.0,
}


class StaticSeedProvider(MarketDataProvider):
    name = "static_seed"

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        normalized = symbol.upper()
        if normalized not in SEED_QUOTES:
            return []
        close = SEED_QUOTES[normalized]
        return [
            MarketQuote(
                symbol=normalized,
                exchange=exchange,
                close=close,
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.985,
                volume=1000000,
                as_of=datetime.now(UTC),
                provider=self.name,
            )
        ]
