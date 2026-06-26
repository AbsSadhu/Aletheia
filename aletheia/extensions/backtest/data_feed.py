"""
Historical Data Feed — yfinance → DuckDB.

Fetches OHLCV candles for a symbol over a date range via yfinance,
persists them to DuckDB, and exposes a typed read API.

Usage:
    feed = HistoricalDataFeed(duckdb_path="./data/aletheia.duckdb")
    await feed.fetch_and_store("RELIANCE.NS", "2023-01-01", "2024-01-01")
    candles = feed.get_candles("RELIANCE.NS", "2023-01-01", "2024-01-01")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OHLCV:
    symbol: str
    date: str          # ISO format YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float
    provider: str = "yfinance"


class HistoricalDataFeed:
    """
    Downloads and caches historical OHLCV data.

    DuckDB schema (table: historical_candles):
        symbol  TEXT
        date    TEXT
        open    DOUBLE
        high    DOUBLE
        low     DOUBLE
        close   DOUBLE
        volume  DOUBLE
        provider TEXT
        PRIMARY KEY (symbol, date)
    """

    def __init__(self, duckdb_path: str = "./data/aletheia.duckdb"):
        import duckdb
        self._duckdb_path = str(duckdb_path)
        self._init_schema()

    def _conn(self):
        import duckdb
        return duckdb.connect(self._duckdb_path)

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS historical_candles (
                    symbol   VARCHAR NOT NULL,
                    date     VARCHAR NOT NULL,
                    open     DOUBLE,
                    high     DOUBLE,
                    low      DOUBLE,
                    close    DOUBLE,
                    volume   DOUBLE,
                    provider VARCHAR DEFAULT 'yfinance',
                    PRIMARY KEY (symbol, date)
                )
            """)

    # ------------------------------------------------------------------
    # Fetch + Store
    # ------------------------------------------------------------------

    async def fetch_and_store(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "1d",
        force_refresh: bool = False,
    ) -> int:
        """
        Download OHLCV data via yfinance and persist to DuckDB.

        Returns the number of rows inserted/updated.
        """
        symbol = symbol.upper()

        if not force_refresh and self._has_data(symbol, start, end):
            logger.info("HistoricalDataFeed: cache hit for %s (%s → %s)", symbol, start, end)
            return 0

        try:
            import yfinance as yf
        except ImportError:
            raise RuntimeError("yfinance is required: pip install yfinance")

        logger.info("HistoricalDataFeed: downloading %s (%s → %s, %s)", symbol, start, end, interval)
        ticker = yf.Ticker(symbol)

        # yfinance is synchronous — run in thread pool
        import asyncio
        df = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: ticker.history(start=start, end=end, interval=interval, auto_adjust=True),
        )

        if df is None or df.empty:
            logger.warning("HistoricalDataFeed: no data returned for %s", symbol)
            return 0

        rows = []
        for idx, row in df.iterrows():
            date_str = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
            rows.append((
                symbol,
                date_str,
                float(row.get("Open", 0.0) or 0.0),
                float(row.get("High", 0.0) or 0.0),
                float(row.get("Low", 0.0) or 0.0),
                float(row.get("Close", 0.0) or 0.0),
                float(row.get("Volume", 0.0) or 0.0),
                "yfinance",
            ))

        if not rows:
            return 0

        with self._conn() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO historical_candles
                    (symbol, date, open, high, low, close, volume, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        logger.info("HistoricalDataFeed: stored %d candles for %s", len(rows), symbol)
        return len(rows)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_candles(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> list[OHLCV]:
        """
        Read OHLCV candles from DuckDB for the given symbol and date range.
        Returns sorted by date ascending.

        Includes lookahead-bias guard: timestamps are strictly sequential.
        """
        symbol = symbol.upper()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT symbol, date, open, high, low, close, volume, provider
                FROM historical_candles
                WHERE symbol = ? AND date >= ? AND date <= ?
                ORDER BY date ASC
                """,
                (symbol, start, end),
            ).fetchall()

        candles = [
            OHLCV(
                symbol=r[0],
                date=r[1],
                open=r[2],
                high=r[3],
                low=r[4],
                close=r[5],
                volume=r[6],
                provider=r[7],
            )
            for r in rows
        ]

        # Lookahead bias guard — assert strict ordering
        _assert_no_lookahead(candles)
        return candles

    def get_close_series(self, symbol: str, start: str, end: str) -> list[float]:
        """Convenience: return just closing prices for the given range."""
        return [c.close for c in self.get_candles(symbol, start, end)]

    def get_available_range(self, symbol: str) -> tuple[str, str] | None:
        """Return (min_date, max_date) available in DuckDB for this symbol."""
        symbol = symbol.upper()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MIN(date), MAX(date) FROM historical_candles WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        if row and row[0]:
            return (row[0], row[1])
        return None

    def list_symbols(self) -> list[str]:
        """List all symbols with data in the historical store."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM historical_candles ORDER BY symbol"
            ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _has_data(self, symbol: str, start: str, end: str) -> bool:
        """Check if we already have data for this symbol+range (rough check)."""
        with self._conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM historical_candles WHERE symbol = ? AND date >= ? AND date <= ?",
                (symbol, start, end),
            ).fetchone()[0]
        return count > 5  # Require at least a week of data


def _assert_no_lookahead(candles: list[OHLCV]) -> None:
    """
    Guard against lookahead bias: dates must be strictly ascending.
    Raises ValueError if duplicate or out-of-order dates are detected.
    """
    seen: set[str] = set()
    prev: str | None = None
    for c in candles:
        if c.date in seen:
            raise ValueError(
                f"Lookahead bias detected: duplicate date {c.date} for {c.symbol}"
            )
        if prev is not None and c.date < prev:
            raise ValueError(
                f"Lookahead bias detected: date {c.date} is before previous {prev} for {c.symbol}"
            )
        seen.add(c.date)
        prev = c.date
