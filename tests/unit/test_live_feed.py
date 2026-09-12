from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata.live_feed import MarketFeedPoller
from aletheia.extensions.agents.collector import CollectorAgent
from aletheia.extensions.data.providers.static_seed import StaticSeedProvider


async def test_poll_once_emits_market_quote_events() -> None:
    bus = EventBus()
    received: list[dict] = []

    async def on_quote(event) -> None:
        received.append(event.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_quote)

    poller = MarketFeedPoller(
        collector=CollectorAgent([StaticSeedProvider()]),
        bus=bus,
        watchlist=(("RELIANCE", "NSE"), ("BTC/USDT", "BINANCE")),
    )
    await poller.poll_once()

    symbols = {q["symbol"] for q in received}
    assert symbols == {"RELIANCE", "BTC/USDT"}


async def test_poll_once_skips_unresolvable_symbols_without_raising() -> None:
    bus = EventBus()
    received: list[dict] = []

    async def on_quote(event) -> None:
        received.append(event.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_quote)

    poller = MarketFeedPoller(
        collector=CollectorAgent([StaticSeedProvider()]),
        bus=bus,
        watchlist=(("ZZZZZZ", "NSE"),),
    )
    await poller.poll_once()

    assert received == []
