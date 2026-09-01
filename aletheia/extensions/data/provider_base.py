from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from aletheia.core.models import MarketQuote

if TYPE_CHECKING:
    from aletheia.core.config.settings import Settings


class MarketDataProvider(ABC):
    name: str

    @classmethod
    def check_available(cls, settings: Settings) -> bool:
        """Whether this provider should be included, given current settings.

        Overridden by providers gated behind a settings flag (e.g. yfinance,
        ccxt); providers that are always safe to include (e.g. the static
        seed fallback) can rely on this default.
        """
        return True

    @abstractmethod
    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        raise NotImplementedError
