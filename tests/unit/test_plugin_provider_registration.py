import asyncio

from aletheia.core.infrastructure.plugins import PluginManager
from aletheia.extensions.data.registry import (
    get_registered_providers,
    reset_registered_providers,
)

PLUGIN_SOURCE = '''
from aletheia.core.models import MarketQuote
from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.extensions.data.registry import register_provider
from datetime import datetime, UTC


class _TestProvider(MarketDataProvider):
    name = "test_plugin_provider"

    async def get_quote(self, symbol, exchange):
        if symbol.upper() != "PLUGINSYM":
            return []
        return [MarketQuote(
            symbol="PLUGINSYM", exchange=exchange, close=42.0, open=41.0,
            high=43.0, low=40.0, volume=1, as_of=datetime.now(UTC),
            provider=self.name,
        )]


class _TestPlugin:
    name = "test_plugin"

    def register(self):
        register_provider(_TestProvider())


PLUGIN_CLASS = _TestPlugin
'''


def test_plugin_can_register_a_market_data_provider(tmp_path) -> None:
    reset_registered_providers()
    try:
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(PLUGIN_SOURCE)

        manager = PluginManager(plugin_dirs=[tmp_path])
        manager.load_all()

        registered = get_registered_providers()
        assert len(registered) == 1
        assert registered[0].name == "test_plugin_provider"

        quotes = asyncio.run(registered[0].get_quote("PLUGINSYM", "NSE"))
        assert quotes and quotes[0].close == 42.0
    finally:
        reset_registered_providers()
