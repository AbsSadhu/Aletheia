# Aletheia Plugins

Drop a `.py` file in this directory and it's loaded automatically at backend
startup (`aletheia/core/infrastructure/plugins.py`, `PluginManager.load_all()`,
called from the FastAPI lifespan before the app starts serving requests).

## Writing a plugin

A plugin module must expose either:

- a `PLUGIN_CLASS` — a class with a no-arg constructor and a `register()` method, or
- a `register_plugin()` function returning an object with a `register()` method

`register()` is called once at startup. What it does depends on what you're extending:

### Adding a market data provider

Implement `MarketDataProvider` (`aletheia/extensions/data/provider_base.py` —
one method, `get_quote(symbol, exchange) -> list[MarketQuote]`) and register
an instance in `register()`:

```python
from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.extensions.data.registry import register_provider


class MyProvider(MarketDataProvider):
    name = "my_provider"

    async def get_quote(self, symbol, exchange):
        ...


class MyPlugin:
    name = "my_provider_plugin"

    def register(self) -> None:
        register_provider(MyProvider())


PLUGIN_CLASS = MyPlugin
```

Your provider is tried after the built-in providers (`StaticSeedProvider`,
`YFinanceProvider`, `CCXTProvider`) in `CollectorAgent`'s fallback chain — no
other wiring needed. See `example_provider.py.example` in this directory for
a complete, runnable version (rename to `.py` to try it).

### Adding a backtest strategy

See `aletheia/extensions/backtest/strategy.py` for the `Strategy` contract
and `aletheia/extensions/backtest/strategies.py` for `register_strategy()`.
