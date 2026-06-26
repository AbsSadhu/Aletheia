from __future__ import annotations

from functools import lru_cache

from aletheia.extensions.agents.collector import CollectorAgent
from aletheia.extensions.agents.oracle import OracleAgent
from aletheia.extensions.agents.sage import SageAgent
from aletheia.extensions.agents.scribe import ScribeAgent
from aletheia.extensions.agents.sentinel import SentinelAgent
from aletheia.core.config.settings import get_settings
from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.extensions.data.providers.ccxt_provider import CCXTProvider
from aletheia.extensions.data.providers.static_seed import StaticSeedProvider
from aletheia.extensions.data.providers.yfinance_provider import YFinanceProvider
from aletheia.core.db.duckdb_store import DuckDBStore
from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.services import RunService


@lru_cache
def get_sqlite_store() -> SQLiteStore:
    settings = get_settings()
    return SQLiteStore(settings.sqlite_path)


@lru_cache
def get_duckdb_store() -> DuckDBStore:
    settings = get_settings()
    return DuckDBStore(settings.duckdb_path)


@lru_cache
def get_providers() -> tuple[MarketDataProvider, ...]:
    settings = get_settings()
    providers: list[MarketDataProvider] = [StaticSeedProvider()]
    if settings.yfinance_enabled:
        providers.append(YFinanceProvider())
    if settings.ccxt_enabled:
        providers.append(CCXTProvider())
    return tuple(providers)


@lru_cache
def get_run_service() -> RunService:
    collector = CollectorAgent(list(get_providers()))
    return RunService(
        collector,
        OracleAgent(),
        SentinelAgent(),
        SageAgent(),
        ScribeAgent(),
        get_sqlite_store(),
        get_duckdb_store(),
    )

