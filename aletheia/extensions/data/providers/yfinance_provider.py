from __future__ import annotations

import logging
from datetime import UTC, datetime

import yfinance as yf

from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.core.models import MarketQuote

logger = logging.getLogger(__name__)


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    @classmethod
    def check_available(cls, settings) -> bool:
        return settings.yfinance_enabled

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        import asyncio

        # imported here: aletheia.core.marketdata imports the providers, so a module-level import
        # would be circular depending on which side is loaded first
        from aletheia.core.marketdata.symbols import yahoo_symbol

        ticker_symbol = symbol
        if exchange.upper() in ("NSE", "BSE", "BINANCE") or "/" in symbol:
            ticker_symbol = yahoo_symbol(symbol, exchange)

        loop = asyncio.get_event_loop()

        def _fetch(sym: str):
            t = yf.Ticker(sym)
            h = t.history(period="5d")
            return t, h.dropna(subset=["Close"])

        ticker, history = await loop.run_in_executor(None, _fetch, ticker_symbol)

        if history.empty and (ticker_symbol.endswith(".NS") or ticker_symbol.endswith(".BO")):
            fallback_sym = symbol.split(".")[0]
            logger.info("YFinanceProvider: fallback lookup for raw symbol %s", fallback_sym)
            ticker, history = await loop.run_in_executor(None, _fetch, fallback_sym)
            if not history.empty:
                symbol = fallback_sym
                exchange = "US"

        if history.empty:
            return []

        latest = history.iloc[-1]
        return [
            MarketQuote(
                symbol=symbol.upper(),
                exchange=exchange,
                close=float(latest["Close"]),
                open=float(latest["Open"]),
                high=float(latest["High"]),
                low=float(latest["Low"]),
                volume=float(latest["Volume"]),
                as_of=datetime.now(UTC),
                provider=self.name,
            )
        ]
