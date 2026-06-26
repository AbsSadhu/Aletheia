from __future__ import annotations

import ccxt

from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.core.models import MarketQuote


class CCXTProvider(MarketDataProvider):
    name = "ccxt"

    def __init__(self) -> None:
        self.exchange = ccxt.binance()

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        if "/" not in symbol:
            return []
        ticker = self.exchange.fetch_ticker(symbol)
        return [
            MarketQuote(
                symbol=symbol.upper(),
                exchange=exchange,
                currency=ticker.get("quoteVolume") and "USDT" or "USD",
                close=float(ticker["last"]),
                open=float(ticker.get("open") or ticker["last"]),
                high=float(ticker.get("high") or ticker["last"]),
                low=float(ticker.get("low") or ticker["last"]),
                volume=float(ticker.get("baseVolume") or 0.0),
                provider=self.name,
            )
        ]


