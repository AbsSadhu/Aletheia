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
from aletheia.core.infrastructure.cache import TTLCache
from aletheia.core.infrastructure.container import ServiceContainer
from aletheia.core.infrastructure.health import HealthRegistry
from aletheia.core.infrastructure.metrics import MetricsRegistry
from aletheia.core.execution.live_gate import LiveExecutionGate
from aletheia.core.execution.paper_trader import PaperTrader
from aletheia.core.execution.storage import ExecutionStorage
from aletheia.core.marketdata.engine import MarketDataEngine
from aletheia.core.infrastructure.plugins import PluginManager
from aletheia.core.infrastructure.scheduler import TaskScheduler
from aletheia.core.services import RunService
from aletheia.extensions.shadow_account.account import ShadowAccount
from aletheia.extensions.shadow_account.scanner import EntryExitScanner
from aletheia.extensions.shadow_account.storage import ShadowAccountStorage


@lru_cache
def get_container() -> ServiceContainer:
    settings = get_settings()
    container = ServiceContainer()
    container.register_singleton("settings", settings)
    container.register_factory("sqlite_store", get_sqlite_store)
    container.register_factory("duckdb_store", get_duckdb_store)
    container.register_factory(
        "cache",
        lambda: TTLCache(
            max_size=settings.cache_max_size,
            default_ttl_secs=settings.cache_default_ttl_secs,
        ),
    )
    container.register_factory("metrics", MetricsRegistry)
    container.register_factory("scheduler", TaskScheduler)
    container.register_factory("health", HealthRegistry)
    container.register_factory("plugins", lambda: PluginManager(plugin_dirs=[settings.plugin_dir]))
    container.register_factory(
        "market_data",
        lambda: MarketDataEngine(
            duckdb_path=str(settings.duckdb_path),
            cache=container.resolve("cache"),
        ),
    )
    container.register_factory(
        "execution_storage",
        lambda: ExecutionStorage(settings.execution_db_path),
    )
    container.register_factory(
        "paper_trader",
        lambda: PaperTrader(
            storage=container.resolve("execution_storage"),
            market_data=container.resolve("market_data"),
        ),
    )
    container.register_factory(
        "live_gate",
        lambda: LiveExecutionGate(container.resolve("execution_storage")),
    )
    container.register_factory(
        "shadow_account_storage",
        lambda: ShadowAccountStorage(str(settings.execution_db_path)),
    )
    container.register_factory(
        "shadow_account",
        lambda: ShadowAccount(
            storage=container.resolve("shadow_account_storage"),
            market_data=container.resolve("market_data"),
        ),
    )
    container.register_factory(
        "entry_exit_scanner",
        lambda: EntryExitScanner(container.resolve("shadow_account")),
    )
    return container


def get_shadow_account() -> ShadowAccount:
    return get_container().resolve("shadow_account")


def get_entry_exit_scanner() -> EntryExitScanner:
    return get_container().resolve("entry_exit_scanner")


def get_market_data_engine() -> MarketDataEngine:
    return get_container().resolve("market_data")


def get_paper_trader() -> PaperTrader:
    return get_container().resolve("paper_trader")


def get_live_gate() -> LiveExecutionGate:
    return get_container().resolve("live_gate")


@lru_cache
def get_sqlite_store() -> SQLiteStore:
    settings = get_settings()
    return SQLiteStore(settings.sqlite_path)


@lru_cache
def get_duckdb_store() -> DuckDBStore:
    settings = get_settings()
    return DuckDBStore(settings.duckdb_path)


# Explicit, ordered — CollectorAgent tries providers in this order and stops
# at the first one that returns data, so order is meaningful (static seed
# first, for a fast known-symbol dev path; live providers after). Adding a
# provider means adding it here and giving it a `check_available()` override
# if it should be gated behind a settings flag; no other wiring needed.
_PROVIDER_TYPES: tuple[type[MarketDataProvider], ...] = (
    StaticSeedProvider,
    YFinanceProvider,
    CCXTProvider,
)


@lru_cache
def get_providers() -> tuple[MarketDataProvider, ...]:
    settings = get_settings()
    return tuple(cls() for cls in _PROVIDER_TYPES if cls.check_available(settings))


@lru_cache
def get_run_service() -> RunService:
    container = get_container()
    collector = CollectorAgent(list(get_providers()))
    service = RunService(
        collector,
        OracleAgent(),
        SentinelAgent(),
        SageAgent(),
        ScribeAgent(),
        get_sqlite_store(),
        get_duckdb_store(),
    )
    container.register_singleton("run_service", service)
    return service
