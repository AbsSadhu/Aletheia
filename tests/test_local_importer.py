"""
Tests for local data importer (local_importer.py).
"""

import os
import tempfile
import pandas as pd
import pytest

from aletheia.extensions.backtest.local_importer import import_local_file
from aletheia.extensions.backtest.data_feed import HistoricalDataFeed


def test_import_csv() -> None:
    # 1. Create a dummy CSV file with custom column names
    data = {
        "timestamp": ["2026-06-01", "2026-06-02", "2026-06-03"],
        "Opening": [100.0, 101.0, 102.0],
        "HighPrice": [105.0, 106.0, 107.0],
        "LowPrice": [95.0, 96.0, 97.0],
        "Closing": [101.0, 102.0, 103.0],
        "Vol": [1000, 1100, 1200],
    }
    df = pd.DataFrame(data)

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        csv_path = f.name
    try:
        df.to_csv(csv_path, index=False)

        # 2. Ingest the CSV into a temporary DuckDB
        db_path = os.path.join(tempfile.gettempdir(), "test_db_csv.duckdb")
        if os.path.exists(db_path):
            os.remove(db_path)

        try:
            # We explicitly specify column mapping
            mapping = {
                "date": "timestamp",
                "open": "Opening",
                "high": "HighPrice",
                "low": "LowPrice",
                "close": "Closing",
                "volume": "Vol",
            }
            rows = import_local_file(
                symbol="TEST_LOCAL",
                file_path=csv_path,
                duckdb_path=db_path,
                column_mapping=mapping,
            )
            assert rows == 3

            # 3. Use HistoricalDataFeed to read it back
            feed = HistoricalDataFeed(duckdb_path=db_path)
            candles = feed.get_candles("TEST_LOCAL", "2026-06-01", "2026-06-03")
            assert len(candles) == 3
            assert candles[0].open == 100.0
            assert candles[1].close == 102.0
            assert candles[2].volume == 1200.0
            assert candles[0].provider == "local"

            # 4. Check prefix routing
            candles_prefix = feed.get_candles("local:TEST_LOCAL", "2026-06-01", "2026-06-03")
            assert len(candles_prefix) == 3

        finally:
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except OSError:
                    pass
    finally:
        if os.path.exists(csv_path):
            os.remove(csv_path)


def test_import_parquet() -> None:
    # Verify pyarrow is installed; if not, skip parquet test
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        pytest.skip("pyarrow not installed — skipping parquet import test")

    # 1. Create a dummy Parquet file
    data = {
        "date": ["2026-06-01", "2026-06-02", "2026-06-03"],
        "open": [10.0, 11.0, 12.0],
        "high": [15.0, 16.0, 17.0],
        "low": [9.0, 9.5, 9.8],
        "close": [11.0, 12.0, 13.0],
        "volume": [500.0, 600.0, 700.0],
    }
    df = pd.DataFrame(data)

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        pq_path = f.name
    try:
        df.to_parquet(pq_path, index=False)

        # 2. Ingest
        db_path = os.path.join(tempfile.gettempdir(), "test_db_pq.duckdb")
        if os.path.exists(db_path):
            os.remove(db_path)

        try:
            rows = import_local_file(
                symbol="pq_stock",
                file_path=pq_path,
                duckdb_path=db_path,
            )
            assert rows == 3

            feed = HistoricalDataFeed(duckdb_path=db_path)
            # Ensure _is_local_symbol returns True
            assert feed._is_local_symbol("pq_stock") is True
            assert feed._is_local_symbol("local:pq_stock") is True

        finally:
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except OSError:
                    pass
    finally:
        if os.path.exists(pq_path):
            os.remove(pq_path)
