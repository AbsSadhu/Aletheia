from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from aletheia.core.marketdata.adapters import MarketDataAdapter
from aletheia.core.marketdata.engine import MarketDataEngine
from aletheia.core.marketdata.models import Candle, MarketDataRequest, Tick
from aletheia.core.models import MarketQuote


class FakeAdapter(MarketDataAdapter):
    name = "fake"

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        return [
            MarketQuote(
                symbol=symbol.upper(),
                exchange=exchange,
                close=101.0,
                open=100.0,
                high=102.0,
                low=99.0,
                volume=500.0,
                provider=self.name,
            )
        ]

    async def get_historical(
        self,
        symbol: str,
        exchange: str,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> list[Candle]:
        return [
            Candle(
                symbol=symbol.upper(),
                exchange=exchange,
                timeframe=interval,
                ts=datetime(2026, 6, 1, tzinfo=UTC),
                open=100.0,
                high=103.0,
                low=99.0,
                close=101.0,
                volume=1000.0,
                provider=self.name,
            ),
            Candle(
                symbol=symbol.upper(),
                exchange=exchange,
                timeframe=interval,
                ts=datetime(2026, 6, 2, tzinfo=UTC),
                open=101.0,
                high=104.0,
                low=100.0,
                close=103.0,
                volume=1100.0,
                provider=self.name,
            ),
        ]


def test_market_data_engine_quote_and_history(tmp_path: Path) -> None:
    engine = MarketDataEngine(
        duckdb_path=str(tmp_path / "market.duckdb"),
        adapters=[FakeAdapter()],
    )

    async def scenario() -> None:
        quote = await engine.get_quote(MarketDataRequest(symbol="RELIANCE", exchange="NSE"))
        assert quote.close == 101.0
        candles = await engine.get_historical(
            MarketDataRequest(symbol="RELIANCE", exchange="NSE"),
            start="2026-06-01",
            end="2026-06-02",
        )
        assert len(candles) == 2
        loaded = engine.load_candles("RELIANCE", "NSE", "2026-06-01", "2026-06-02", "1d")
        assert len(loaded) >= 2

    asyncio.run(scenario())


def test_market_data_engine_aggregates_ticks(tmp_path: Path) -> None:
    engine = MarketDataEngine(
        duckdb_path=str(tmp_path / "market.duckdb"),
        adapters=[FakeAdapter()],
    )

    async def scenario() -> None:
        await engine.record_tick(
            Tick(
                symbol="BTC/USDT",
                exchange="BINANCE",
                price=100.0,
                size=1.0,
                provider="fake",
                ts=datetime(2026, 6, 1, 10, 0, 1, tzinfo=UTC),
            )
        )
        await engine.record_tick(
            Tick(
                symbol="BTC/USDT",
                exchange="BINANCE",
                price=102.0,
                size=2.0,
                provider="fake",
                ts=datetime(2026, 6, 1, 10, 0, 30, tzinfo=UTC),
            )
        )
        candles = await engine.aggregate_ticks_to_candles("BTC/USDT", "BINANCE", "1m")
        assert len(candles) == 1
        assert candles[0].open == 100.0
        assert candles[0].close == 102.0
        assert candles[0].volume == 3.0

    asyncio.run(scenario())


def test_market_data_engine_replay(tmp_path: Path) -> None:
    engine = MarketDataEngine(
        duckdb_path=str(tmp_path / "market.duckdb"),
        adapters=[FakeAdapter()],
    )

    async def scenario() -> None:
        await engine.store_candles(
            [
                Candle(
                    symbol="AAPL",
                    exchange="NASDAQ",
                    timeframe="1d",
                    ts=datetime(2026, 6, 1, tzinfo=UTC),
                    open=1,
                    high=2,
                    low=1,
                    close=2,
                    volume=10,
                    provider="fake",
                ),
                Candle(
                    symbol="AAPL",
                    exchange="NASDAQ",
                    timeframe="1d",
                    ts=datetime(2026, 6, 2, tzinfo=UTC),
                    open=2,
                    high=3,
                    low=2,
                    close=3,
                    volume=20,
                    provider="fake",
                ),
            ]
        )
        replayed = []
        async for candle in engine.replay_candles(
            "AAPL",
            "NASDAQ",
            "2026-06-01",
            "2026-06-02",
            "1d",
        ):
            replayed.append(candle)
        assert len(replayed) == 2

    asyncio.run(scenario())
