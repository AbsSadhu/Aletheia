from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from aletheia.core.models import MarketQuote
from aletheia.core.marketdata.models import Candle
from aletheia.extensions.backtest.data_feed import HistoricalDataFeed
from aletheia.extensions.data.providers.ccxt_provider import CCXTProvider
from aletheia.extensions.data.providers.yfinance_provider import YFinanceProvider


class MarketDataAdapter(ABC):
    name: str

    @abstractmethod
    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        raise NotImplementedError

    async def get_historical(
        self,
        symbol: str,
        exchange: str,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> list[Candle]:
        raise NotImplementedError(f"{self.name} does not support historical data")


class YFinanceAdapter(MarketDataAdapter):
    name = "yfinance"

    def __init__(self, duckdb_path: str) -> None:
        self.provider = YFinanceProvider()
        self.feed = HistoricalDataFeed(duckdb_path=duckdb_path)

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        return await self.provider.get_quote(symbol, exchange)

    async def get_historical(
        self,
        symbol: str,
        exchange: str,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> list[Candle]:
        ticker_symbol = symbol
        if exchange.upper() == "NSE" and not symbol.endswith(".NS"):
            ticker_symbol = f"{symbol}.NS"
        elif exchange.upper() == "BSE" and not symbol.endswith(".BO"):
            ticker_symbol = f"{symbol}.BO"

        await self.feed.fetch_and_store(ticker_symbol, start, end, interval=interval)
        candles = self.feed.get_candles(ticker_symbol, start, end)
        return [
            Candle(
                symbol=symbol.upper(),
                exchange=exchange,
                timeframe=interval,
                ts=datetime.fromisoformat(item.date).replace(tzinfo=UTC),
                open=item.open,
                high=item.high,
                low=item.low,
                close=item.close,
                volume=item.volume,
                provider=self.name,
            )
            for item in candles
        ]


class CCXTAdapter(MarketDataAdapter):
    name = "ccxt"

    def __init__(self) -> None:
        self.provider = CCXTProvider()

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        return await self.provider.get_quote(symbol, exchange)

    async def get_historical(
        self,
        symbol: str,
        exchange: str,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> list[Candle]:
        timeframe = "1d" if interval == "1d" else interval

        def _fetch() -> list[list[float]]:
            return self.provider.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=500)

        rows = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        candles: list[Candle] = []
        for ts_ms, open_, high, low, close, volume in rows:
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            iso_date = ts.date().isoformat()
            if iso_date < start or iso_date > end:
                continue
            candles.append(
                Candle(
                    symbol=symbol.upper(),
                    exchange=exchange,
                    timeframe=interval,
                    ts=ts,
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume),
                    provider=self.name,
                )
            )
        return candles
