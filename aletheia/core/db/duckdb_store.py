from __future__ import annotations

from pathlib import Path

import duckdb

from aletheia.core.models import MarketQuote


class DuckDBStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        conn = duckdb.connect(str(self.db_path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_quotes (
                symbol VARCHAR,
                exchange VARCHAR,
                currency VARCHAR,
                close DOUBLE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                volume DOUBLE,
                as_of TIMESTAMP,
                provider VARCHAR
            )
            """
        )
        conn.close()

    def persist_quotes(self, quotes: list[MarketQuote]) -> None:
        if not quotes:
            return
        conn = duckdb.connect(str(self.db_path))
        for quote in quotes:
            conn.execute(
                """
                INSERT INTO market_quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote.symbol,
                    quote.exchange,
                    quote.currency,
                    quote.close,
                    quote.open,
                    quote.high,
                    quote.low,
                    quote.volume,
                    quote.as_of,
                    quote.provider,
                ),
            )
        conn.close()
