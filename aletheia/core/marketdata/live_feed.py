from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.models import AssetType, CollectorOutput, Holding
from aletheia.core.marketdata.watchlist import DEFAULT_ITEMS
from aletheia.extensions.agents.collector import CollectorAgent

logger = logging.getLogger(__name__)

# Kept for callers/tests that import it; the live list now comes from the saved watchlist.
DEFAULT_WATCHLIST: tuple[tuple[str, str], ...] = tuple(DEFAULT_ITEMS)


class MarketFeedPoller:
    """Polls a watchlist through CollectorAgent's provider chain and publishes each quote onto
    the event bus as Topics.MARKET_QUOTE.

    This is the fallback path (15 s cadence, delayed public data). When the Angel One stream is
    connected it covers NSE/BSE symbols per-second, so `skip` lets the poller leave those alone
    and only handle what the stream can't (crypto, or everything if the stream is down).
    """

    def __init__(
        self,
        collector: CollectorAgent,
        bus: EventBus,
        watchlist: tuple[tuple[str, str], ...] = DEFAULT_WATCHLIST,
        watchlist_fn: Callable[[], list[tuple[str, str]]] | None = None,
        skip: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._collector = collector
        self._bus = bus
        self._watchlist = watchlist
        self._watchlist_fn = watchlist_fn
        self._skip = skip
        self.last_quotes: dict[tuple[str, str], dict[str, Any]] = {}

    def current_watchlist(self) -> list[tuple[str, str]]:
        return self._watchlist_fn() if self._watchlist_fn else list(self._watchlist)

    async def _collect_one(self, symbol: str, exchange: str) -> CollectorOutput | None:
        holding = Holding(
            symbol=symbol,
            quantity=1,
            average_price=1,
            exchange=exchange,
            asset_type=AssetType.CRYPTO if "/" in symbol else AssetType.EQUITY,
        )
        try:
            return await self._collector.collect_for_holding(holding)
        except Exception as exc:
            logger.warning("MarketFeedPoller: failed to poll %s: %s", symbol, exc)
            return None

    async def poll_once(self) -> None:
        # Fetched concurrently: CollectorAgent retries each provider up to 3x with a 5 s timeout,
        # so polling serially could overrun the next scheduled tick.
        targets = [
            (s, e) for s, e in self.current_watchlist() if not (self._skip and self._skip(s, e))
        ]
        results = await asyncio.gather(*(self._collect_one(s, e) for s, e in targets))
        for output in results:
            if output is None:
                continue
            for quote in output.quotes:
                payload = quote.model_dump(mode="json")
                payload["stream"] = False
                self.last_quotes[(quote.symbol, quote.exchange)] = payload
                await self._bus.emit(Topics.MARKET_QUOTE, payload, source="live_feed")
