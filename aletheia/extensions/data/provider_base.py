from __future__ import annotations

from abc import ABC, abstractmethod

from aletheia.core.models import MarketQuote


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        raise NotImplementedError
