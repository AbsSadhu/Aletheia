"""
Local Data Importer — Ingests CSV, Parquet, and DuckDB tables into the Aletheia DuckDB database.
"""

from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_MAPPINGS = {
    "date": ["date", "timestamp", "time", "trade_date", "datetime"],
    "open": ["open", "open_price", "opening"],
    "high": ["high", "high_price", "highest"],
    "low": ["low", "low_price", "lowest"],
    "close": ["close", "close_price", "closing"],
    "volume": ["volume", "vol", "turnover"],
}


def auto_detect_columns(columns: list[str]) -> dict[str, str]:
    """Helper to automatically map columns by matching prefixes/exact matches."""
    mapping = {}
    cols_lower = {c.lower(): c for c in columns}

    for std_name, options in DEFAULT_MAPPINGS.items():
        found = False
        # Try exact matches first
        for opt in options:
            if opt in cols_lower:
                mapping[std_name] = cols_lower[opt]
                found = True
                break
        if not found:
            # Try starts with or contains match
            for opt in options:
                matched = [cols_lower[c] for c in cols_lower if opt in c]
                if matched:
                    mapping[std_name] = matched[0]
                    break
    return mapping


def normalize_dataframe(
    df: pd.DataFrame,
    symbol: str,
    column_mapping: dict[str, str] | None = None,
    date_format: str | None = None,
) -> list[tuple[str, str, float, float, float, float, float, str]]:
    """
    Normalizes a pandas DataFrame into standard OHLCV tuples for DuckDB ingestion.
    """
    if df.empty:
        return []

    # If index is a DatetimeIndex and date column is not specified, reset index
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()

    cols = list(df.columns)
    mapping = auto_detect_columns(cols)
    if column_mapping:
        mapping.update(column_mapping)

    # Ensure required columns exist
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(mapping.keys())
    if missing:
        raise ValueError(
            f"Could not map required columns: {missing}. Available: {cols}. Mapped: {mapping}"
        )

    # Rename
    rename_dict = {mapping[k]: k for k in mapping if k != "date" and mapping[k] in df.columns}
    df = df.rename(columns=rename_dict)

    # Date normalization
    date_col = mapping["date"]
    if date_format:
        df["trade_date"] = pd.to_datetime(df[date_col], format=date_format, errors="coerce")
    else:
        df["trade_date"] = pd.to_datetime(df[date_col], errors="coerce")

    # Strip timezone
    if getattr(df["trade_date"].dt, "tz", None) is not None:
        df["trade_date"] = df["trade_date"].dt.tz_localize(None)

    df = df.dropna(subset=["trade_date"])
    df["date_str"] = df["trade_date"].dt.strftime("%Y-%m-%d")

    # Numeric conversion
    numeric_cols = ["open", "high", "low", "close"]
    if "volume" in df.columns:
        numeric_cols.append("volume")
    else:
        df["volume"] = 0.0

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])

    rows = []
    for _, row in df.iterrows():
        rows.append(
            (
                symbol.upper(),
                str(row["date_str"]),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
                "local",
            )
        )

    # Sort by date
    rows.sort(key=lambda x: x[1])
    return rows


def import_local_file(
    symbol: str,
    file_path: str,
    duckdb_path: str = "./data/aletheia.duckdb",
    column_mapping: dict[str, str] | None = None,
    date_format: str | None = None,
    query: str | None = None,
) -> int:
    """
    Imports historical OHLCV data from a CSV, Parquet, or DuckDB file into the local DuckDB.
    """
    path = Path(file_path)
    if not path.exists() and query is None:
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    if ext == ".csv":
        df = pd.read_csv(path)
    elif ext in {".parquet", ".pq"}:
        df = pd.read_parquet(path)
    elif ext in {".duckdb", ".db"} or query is not None:
        import duckdb

        db_file = str(path) if path.exists() else ":memory:"
        if not query:
            raise ValueError("DuckDB import requires a SQL query.")
        with duckdb.connect(db_file, read_only=True) as temp_conn:
            df = temp_conn.execute(query).df()
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use .csv, .parquet, or .duckdb")

    rows = normalize_dataframe(
        df=df, symbol=symbol, column_mapping=column_mapping, date_format=date_format
    )
    if not rows:
        return 0

    import duckdb
    from aletheia.core.config.settings import get_settings

    settings = get_settings()
    config = {}
    if settings.db_encryption_key:
        config["encryption_key"] = settings.db_encryption_key
    with duckdb.connect(str(duckdb_path), config=config) as conn:
        conn.execute(
            """
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
            """
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO historical_candles
                (symbol, date, open, high, low, close, volume, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    logger.info("Successfully imported %d rows into DuckDB for symbol %s", len(rows), symbol)
    return len(rows)
