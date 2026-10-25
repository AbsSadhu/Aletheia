from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.core.models import MarketQuote

if TYPE_CHECKING:
    from aletheia.core.config.settings import Settings


SEED_QUOTES: dict[str, float] = {
    "RELIANCE": 2920.0,
    "TCS": 3925.0,
    "INFY": 1612.0,
    "HDFCBANK": 1748.0,
    "ICICIBANK": 1184.0,
    "SBIN": 846.0,
    "BTC/USDT": 65200.0,
    "DISAGREE": 2500.0,
}


class StaticSeedProvider(MarketDataProvider):
    """Hardcoded demo prices for offline development. Opt-in (ALETHEIA_STATIC_SEED_ENABLED)
    and last in the chain: these numbers are stale and must never stand in for real quotes."""

    name = "static_seed"

    @classmethod
    def check_available(cls, settings: Settings) -> bool:
        return settings.static_seed_enabled

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
