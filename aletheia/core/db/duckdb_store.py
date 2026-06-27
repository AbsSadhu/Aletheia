from __future__ import annotations

from pathlib import Path

import duckdb

from aletheia.core.models import MarketQuote


class DuckDBStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        from aletheia.core.config.settings import get_settings
        settings = get_settings()
        config = {}
        if settings.db_encryption_key:
            config["encryption_key"] = settings.db_encryption_key
        return duckdb.connect(str(self.db_path), config=config)

    def _initialize(self) -> None:
        conn = self._connect()
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_quotes_symbol_as_of ON market_quotes (symbol, as_of)"
        )
        conn.close()

    def persist_quotes(self, quotes: list[MarketQuote]) -> None:
        if not quotes:
            return
        conn = self._connect()
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

    def prune_old_quotes(self, days: int) -> int:
        import datetime
        import duckdb
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
        conn = self._connect()
        try:
            count_res = conn.execute("SELECT COUNT(*) FROM market_quotes WHERE as_of < ?", (cutoff,)).fetchone()
            count = count_res[0] if count_res else 0
            conn.execute("DELETE FROM market_quotes WHERE as_of < ?", (cutoff,))
            conn.commit()
            return count
        finally:
            conn.close()

