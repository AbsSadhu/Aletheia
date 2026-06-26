from pathlib import Path

import pytest

from aletheia.extensions.agents.oracle import OracleAgent
from aletheia.extensions.agents.sage import SageAgent
from aletheia.extensions.agents.scribe import ScribeAgent
from aletheia.extensions.agents.sentinel import SentinelAgent
from aletheia.extensions.agents.collector import CollectorAgent
from aletheia.extensions.data.providers.static_seed import StaticSeedProvider
from aletheia.core.db.duckdb_store import DuckDBStore
from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.services import RunService


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def run_service(temp_data_dir: Path) -> RunService:
    sqlite_store = SQLiteStore(temp_data_dir / "test.sqlite3")
    duckdb_store = DuckDBStore(temp_data_dir / "test.duckdb")
    collector = CollectorAgent([StaticSeedProvider()])
    return RunService(
        collector,
        OracleAgent(),
        SentinelAgent(),
        SageAgent(),
        ScribeAgent(),
        sqlite_store,
        duckdb_store,
    )
