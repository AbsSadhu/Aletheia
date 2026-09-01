from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from aletheia.core.infrastructure.cache import TTLCache
from aletheia.core.marketdata.adapters import CCXTAdapter, MarketDataAdapter, YFinanceAdapter
from aletheia.core.marketdata.models import Candle, MarketDataRequest, OrderBookSnapshot, Tick
from aletheia.core.models import MarketQuote

logger = logging.getLogger(__name__)


class _SimpleRateLimiter:
    def __init__(self, calls: int = 10, window_secs: float = 1.0) -> None:
        self.calls = calls
        self.window_secs = window_secs
        self._buckets: defaultdict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def acquire(self, key: str) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            bucket = [value for value in self._buckets[key] if now - value < self.window_secs]
            if len(bucket) >= self.calls:
                sleep_for = self.window_secs - (now - bucket[0])
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                now = loop.time()
                bucket = [value for value in bucket if now - value < self.window_secs]
            bucket.append(now)
            self._buckets[key] = bucket


class MarketDataEngine:
    def __init__(
        self,
        duckdb_path: str | Path,
        cache: TTLCache[str, object] | None = None,
        adapters: list[MarketDataAdapter] | None = None,
    ) -> None:
        self.duckdb_path = str(duckdb_path)
        self.cache = cache or TTLCache(max_size=512, default_ttl_secs=15.0)
        self.rate_limiter = _SimpleRateLimiter()
        self.adapters = adapters or [
            YFinanceAdapter(self.duckdb_path),
            CCXTAdapter(),
        ]
        self._init_schema()

    def _conn(self):
        return duckdb.connect(self.duckdb_path)

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_ticks (
                    symbol VARCHAR,
                    exchange VARCHAR,
                    price DOUBLE,
                    size DOUBLE,
                    side VARCHAR,
                    ts TIMESTAMP,
                    provider VARCHAR
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_candles (
                    symbol VARCHAR,
                    exchange VARCHAR,
                    timeframe VARCHAR,
                    ts TIMESTAMP,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume DOUBLE,
                    provider VARCHAR
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS order_book_snapshots (
                    symbol VARCHAR,
                    exchange VARCHAR,
                    ts TIMESTAMP,
                    bids_json VARCHAR,
                    asks_json VARCHAR,
                    provider VARCHAR
                )
                """
            )

    def register_adapter(self, adapter: MarketDataAdapter) -> None:
        self.adapters.append(adapter)

    async def get_quote(
        self,
        request: MarketDataRequest,
        *,
        persist: bool = True,
    ) -> MarketQuote:
        cache_key = f"quote:{request.provider}:{request.exchange}:{request.symbol}"
        cached = self.cache.get(cache_key)
        if isinstance(cached, MarketQuote):
            return cached

        adapters = self._resolve_adapters(request.provider)
        for adapter in adapters:
            await self.rate_limiter.acquire(adapter.name)
            quotes = await adapter.get_quote(request.symbol, request.exchange)
            if not quotes:
                continue
            quote = quotes[0]
            self.cache.set(cache_key, quote, ttl_secs=10.0)
            if persist:
                await self.record_tick(
                    Tick(
                        symbol=quote.symbol,
                        exchange=quote.exchange,
                        price=quote.close,
                        size=quote.volume or 0.0,
                        side="mid",
                        ts=quote.as_of,
                        provider=quote.provider,
                    )
                )
                await self.store_candle(Candle.from_quote(quote))
            return quote

        raise LookupError(f"No market quote available for {request.symbol} on {request.exchange}")

    async def get_historical(
        self,
        request: MarketDataRequest,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> list[Candle]:
        adapters = self._resolve_adapters(request.provider)
        for adapter in adapters:
            try:
                await self.rate_limiter.acquire(adapter.name)
                candles = await adapter.get_historical(
                    request.symbol,
                    request.exchange,
                    start,
                    end,
                    interval=interval,
                )
            except NotImplementedError:
                continue
            if candles:
                await self.store_candles(candles)
                return candles
        return self.load_candles(request.symbol, request.exchange, start, end, interval)

    async def record_tick(self, tick: Tick) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO market_ticks (symbol, exchange, price, size, side, ts, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tick.symbol,
                    tick.exchange,
                    tick.price,
                    tick.size,
                    tick.side,
                    tick.ts.replace(tzinfo=None),
                    tick.provider,
                ),
            )

    async def store_candle(self, candle: Candle) -> None:
        await self.store_candles([candle])

    async def store_candles(self, candles: list[Candle]) -> None:
        if not candles:
            return
        rows = [
            (
                candle.symbol,
                candle.exchange,
                candle.timeframe,
                candle.ts.replace(tzinfo=None),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.provider,
            )
            for candle in candles
        ]
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO market_candles
                    (symbol, exchange, timeframe, ts, open, high, low, close, volume, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    async def store_order_book_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        import json

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO order_book_snapshots (symbol, exchange, ts, bids_json, asks_json, provider)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.symbol,
                    snapshot.exchange,
                    snapshot.ts.replace(tzinfo=None),
                    json.dumps([item.model_dump() for item in snapshot.bids]),
                    json.dumps([item.model_dump() for item in snapshot.asks]),
                    snapshot.provider,
                ),
            )

    async def aggregate_ticks_to_candles(
        self,
        symbol: str,
        exchange: str,
        timeframe: str = "1m",
    ) -> list[Candle]:
        bucket = _timeframe_to_timedelta(timeframe)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT price, size, ts, provider
                FROM market_ticks
                WHERE symbol = ? AND exchange = ?
                ORDER BY ts ASC
                """,
                (symbol, exchange),
            ).fetchall()

        grouped: dict[datetime, list[tuple[float, float, datetime, str]]] = defaultdict(list)
        for price, size, ts, provider in rows:
            timestamp = ts.replace(tzinfo=UTC)
            bucket_start = _bucket_start(timestamp, bucket)
            grouped[bucket_start].append((price, size, timestamp, provider))

        candles: list[Candle] = []
        for bucket_start in sorted(grouped):
            items = grouped[bucket_start]
            prices = [item[0] for item in items]
            volume = sum(item[1] for item in items)
            candles.append(
                Candle(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    ts=bucket_start,
                    open=prices[0],
                    high=max(prices),
                    low=min(prices),
                    close=prices[-1],
                    volume=volume,
                    provider=items[-1][3],
                )
            )

        await self.store_candles(candles)
        return candles

    def load_candles(
        self,
        symbol: str,
        exchange: str,
        start: str,
        end: str,
        timeframe: str,
    ) -> list[Candle]:
        start_dt = datetime.fromisoformat(start).replace(tzinfo=UTC)
        end_dt = datetime.fromisoformat(end).replace(tzinfo=UTC) + timedelta(days=1)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT symbol, exchange, timeframe, ts, open, high, low, close, volume, provider
                FROM market_candles
                WHERE symbol = ? AND exchange = ? AND timeframe = ? AND ts >= ? AND ts < ?
                ORDER BY ts ASC
                """,
                (symbol.upper(), exchange, timeframe, start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None)),
            ).fetchall()
        return [
            Candle(
                symbol=row[0],
                exchange=row[1],
                timeframe=row[2],
                ts=row[3].replace(tzinfo=UTC),
                open=row[4],
                high=row[5],
                low=row[6],
                close=row[7],
                volume=row[8],
                provider=row[9],
            )
            for row in rows
        ]

    async def replay_candles(
        self,
        symbol: str,
        exchange: str,
        start: str,
        end: str,
        timeframe: str,
        speed: float = 0.0,
    ):
        candles = self.load_candles(symbol, exchange, start, end, timeframe)
        previous: datetime | None = None
        for candle in candles:
            if speed > 0 and previous is not None:
                gap = (candle.ts - previous).total_seconds() / speed
                if gap > 0:
                    await asyncio.sleep(min(gap, 1.0))
            previous = candle.ts
            yield candle

    def _resolve_adapters(self, provider: str | None) -> list[MarketDataAdapter]:
        if provider:
            return [adapter for adapter in self.adapters if adapter.name == provider]
        return list(self.adapters)


def _timeframe_to_timedelta(timeframe: str) -> timedelta:
    mapping = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1),
    }
    return mapping.get(timeframe, timedelta(minutes=1))


def _bucket_start(ts: datetime, bucket: timedelta) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    offset = int((ts - epoch).total_seconds() // bucket.total_seconds())
    return epoch + timedelta(seconds=offset * bucket.total_seconds())
