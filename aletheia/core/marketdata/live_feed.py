from __future__ import annotations

import logging

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.models import AssetType, Holding
from aletheia.extensions.agents.collector import CollectorAgent

logger = logging.getLogger(__name__)

# Small fixed watchlist so the feed ticks out of the box with zero API keys —
# every symbol here resolves via StaticSeedProvider even with yfinance/ccxt
# disabled. Live deployments with real providers enabled will get real quotes
# for the same symbols instead, since CollectorAgent tries providers in order.
DEFAULT_WATCHLIST: tuple[tuple[str, str], ...] = (
    ("RELIANCE", "NSE"),
    ("TCS", "NSE"),
    ("INFY", "NSE"),
    ("HDFCBANK", "NSE"),
    ("ICICIBANK", "NSE"),
    ("SBIN", "NSE"),
    ("BTC/USDT", "BINANCE"),
)


class MarketFeedPoller:
    """Ticks a watchlist through CollectorAgent's existing provider chain and
    publishes each resulting quote onto the event bus as Topics.MARKET_QUOTE.

    Deliberately thin: all provider selection, retry, and fallback logic
    already lives in CollectorAgent — this just turns a watchlist into
    events on a schedule.
    """

    def __init__(
        self,
        collector: CollectorAgent,
        bus: EventBus,
        watchlist: tuple[tuple[str, str], ...] = DEFAULT_WATCHLIST,
    ) -> None:
        self._collector = collector
        self._bus = bus
        self._watchlist = watchlist

    async def poll_once(self) -> None:
        for symbol, exchange in self._watchlist:
            holding = Holding(
                symbol=symbol,
                quantity=1,
                average_price=1,
                exchange=exchange,
                asset_type=AssetType.CRYPTO if "/" in symbol else AssetType.EQUITY,
            )
            try:
                output = await self._collector.collect_for_holding(holding)
            except Exception as exc:
                logger.warning("MarketFeedPoller: failed to poll %s: %s", symbol, exc)
                continue
            for quote in output.quotes:
                await self._bus.emit(
                    Topics.MARKET_QUOTE, quote.model_dump(mode="json"), source="live_feed"
                )
