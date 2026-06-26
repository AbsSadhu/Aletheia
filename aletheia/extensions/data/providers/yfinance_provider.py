from __future__ import annotations

from datetime import UTC, datetime

import yfinance as yf

from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.core.models import MarketQuote


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        ticker_symbol = symbol
        if exchange.upper() == "NSE" and not symbol.endswith(".NS"):
            ticker_symbol = f"{symbol}.NS"
        elif exchange.upper() == "BSE" and not symbol.endswith(".BO"):
            ticker_symbol = f"{symbol}.BO"

        ticker = yf.Ticker(ticker_symbol)
        history = ticker.history(period="5d")
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
