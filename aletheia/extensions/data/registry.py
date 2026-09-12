"""Plugin registration point for market data providers.

A plugin's `register()` (see `aletheia.core.infrastructure.plugins`) calls
`register_provider()` to add itself to the same fallback chain
`CollectorAgent` already uses for the built-in providers
(`StaticSeedProvider`, `YFinanceProvider`, `CCXTProvider`) — no other wiring
needed. Plugin providers are tried after the built-ins.
"""

from __future__ import annotations

from aletheia.extensions.data.provider_base import MarketDataProvider

_plugin_providers: list[MarketDataProvider] = []


def register_provider(provider: MarketDataProvider) -> None:
    _plugin_providers.append(provider)


def get_registered_providers() -> list[MarketDataProvider]:
    return list(_plugin_providers)


def reset_registered_providers() -> None:
    """Testing only — plugin registration is otherwise append-only for the
    life of the process."""
    _plugin_providers.clear()
