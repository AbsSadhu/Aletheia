"""Owns the live feed: one broker stream (per-second) with the poller as fallback.

  stream connected   -> NSE (and BSE for Angel One) symbols tick every second; the poller only
                        handles what the stream can't (crypto)
  stream unavailable -> the poller handles everything every `market_feed_interval_secs`

Which broker streams is `live_feed_provider`: "angel_one" (default) or "fyers".
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from aletheia.core.events.bus import EventBus
from aletheia.core.marketdata.hours import market_status
from aletheia.core.marketdata.live_feed import MarketFeedPoller
from aletheia.core.marketdata.watchlist import WatchlistStore
from aletheia.extensions.data.angel_session import AngelOneSession
from aletheia.extensions.data.angel_stream import AngelOneStream
from aletheia.extensions.data.binance_stream import BinanceStream, to_stream_name
from aletheia.extensions.data.bse_web_stream import BseWebStream, load_bse_scrips
from aletheia.extensions.data.fyers_stream import FyersStream, default_python, to_fyers_symbol
from aletheia.extensions.data.providers.angel_one_provider import (
    AngelOneProvider,
    load_scrip_tokens,
)

logger = logging.getLogger(__name__)

AnyStream = AngelOneStream | FyersStream | BseWebStream


class FeedManager:
    def __init__(
        self,
        settings: Any,
        bus: EventBus,
        watchlist: WatchlistStore,
        poller: MarketFeedPoller,
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.watchlist = watchlist
        self.poller = poller
        self.stream: AnyStream | None = None
        self.crypto_stream: BinanceStream | None = None
        self._crypto_task: asyncio.Task[None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._scrips: dict[tuple[str, str], str] = {}
        self._bse_scrips: dict[str, str] = {}
        self._provider: AngelOneProvider | None = None
        self.start_error: str | None = None

    @property
    def provider(self) -> str:
        return str(getattr(self.settings, "live_feed_provider", "angel_one") or "angel_one")

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        await self._start_crypto()
        if self.stream is None:
            if self.provider == "fyers":
                await self._start_fyers()
            elif self.provider == "bse_web":
                await self._start_bse()
            else:
                await self._start_angel()
            if self.stream is not None:
                self._task = asyncio.create_task(self.stream.run(), name=f"{self.provider}-stream")
        # The poller defers to a stream for whatever it covers while that stream is connected.
        if self.stream is not None or self.crypto_stream is not None:
            self.poller._skip = self._covered_by_a_live_stream
        await self.apply_watchlist()

    def _covered_by_a_live_stream(self, symbol: str, exchange: str) -> bool:
        for s in (self.stream, self.crypto_stream):
            if s is not None and s.connected and s.covers(symbol, exchange):
                return True
        return False

    async def _start_crypto(self) -> None:
        """Free, no-account, per-second crypto from Binance. Idempotent."""
        if self.crypto_stream is not None or not getattr(
            self.settings, "crypto_stream_enabled", True
        ):
            return
        self.crypto_stream = BinanceStream(self.bus)
        self._crypto_task = asyncio.create_task(self.crypto_stream.run(), name="binance-stream")

    async def _start_angel(self) -> None:
        s = self.settings
        if not (
            getattr(s, "angel_one_enabled", False) and getattr(s, "angel_one_stream_enabled", True)
        ):
            return
        session = AngelOneSession()
        if session.credentials() is None:
            self.start_error = (
                "Angel One credentials are not saved yet (Settings -> Broker Integrations)."
            )
            logger.info("FeedManager: %s", self.start_error)
            return
        self._provider = AngelOneProvider(session=session)

        async def reference_price(symbol: str, exchange: str) -> float | None:
            quotes = await self._provider.get_quote(symbol, exchange)  # type: ignore[union-attr]
            return quotes[0].close if quotes else None

        stream = AngelOneStream(
            session,
            self.bus,
            emit_interval=getattr(s, "market_feed_emit_interval_secs", 1.0),
            scale_check=reference_price,
        )
        try:
            self._scrips = await load_scrip_tokens()
        except Exception as exc:
            self.start_error = f"Could not load the Angel One instrument list: {exc}"
            logger.warning("FeedManager: %s", self.start_error)
            return
        self.stream = stream

    async def _start_bse(self) -> None:
        """Free, no-account, unofficial: poll BSE's public website API (see bse_web_stream.py)."""
        try:
            self._bse_scrips = await load_bse_scrips()
        except Exception as exc:
            self.start_error = f"Could not load BSE's scrip list: {exc}"
            logger.warning("FeedManager: %s", self.start_error)
            return
        self.stream = BseWebStream(
            self.bus, poll_secs=getattr(self.settings, "bse_web_poll_secs", 2.0)
        )

    async def _start_fyers(self) -> None:
        from aletheia.extensions.brokers.fyers_session import current_ws_token

        if not default_python().exists():
            self.start_error = (
                "Fyers helper environment is missing. Run: "
                ".venv\\Scripts\\python.exe scripts\\fyers_setup.py"
            )
            logger.info("FeedManager: %s", self.start_error)
            return
        self.stream = FyersStream(
            current_ws_token,
            self.bus,
            emit_interval=getattr(self.settings, "market_feed_emit_interval_secs", 1.0),
        )

    async def stop(self) -> None:
        if self.stream:
            self.stream.stop()
        if self.crypto_stream:
            self.crypto_stream.stop()
        for task in (self._task, self._crypto_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def apply_watchlist(self) -> None:
        """Push the saved watchlist to the streams (call after every change)."""
        if self.crypto_stream is not None:
            crypto = {
                (exch, sym): name
                for sym, exch in self.watchlist.items()
                if (name := to_stream_name(sym, exch))
            }
            await self.crypto_stream.set_symbols(crypto)
        if self.stream is None:
            return
        if isinstance(self.stream, BseWebStream):
            codes = {
                (exch, sym): self._bse_scrips[sym.upper()]
                for sym, exch in self.watchlist.items()
                if exch in ("NSE", "BSE") and sym.upper() in self._bse_scrips
            }
            await self.stream.set_symbols(codes)
            return
        if isinstance(self.stream, FyersStream):
            fy = {
                (exch, sym): to_fyers_symbol(sym, exch)
                for sym, exch in self.watchlist.items()
                if to_fyers_symbol(sym, exch)
            }
            await self.stream.set_symbols({k: v for k, v in fy.items() if v})
            return
        tokens = {
            (exch, sym): self._scrips[(exch, sym)]
            for sym, exch in self.watchlist.items()
            if (exch, sym) in self._scrips
        }
        await self.stream.set_symbols(tokens)

    # -- read side ---------------------------------------------------------------

    def unresolved_symbols(self) -> list[str]:
        """Equity watchlist symbols the active broker can't stream (typo, wrong exchange...)."""
        items = self.watchlist.items()
        if isinstance(self.stream, BseWebStream):
            return [
                f"{s}:{e}"
                for s, e in items
                if e in ("NSE", "BSE") and s.upper() not in self._bse_scrips
            ]
        if isinstance(self.stream, FyersStream):
            return [
                f"{s}:{e}" for s, e in items if e in ("NSE", "BSE") and not to_fyers_symbol(s, e)
            ]
        if not self._scrips:
            return []
        return [
            f"{sym}:{exch}"
            for sym, exch in items
            if exch in ("NSE", "BSE") and (exch, sym) not in self._scrips
        ]

    def snapshot(self) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = dict(self.poller.last_quotes)
        for s in (self.stream, self.crypto_stream):
            if s:
                merged.update(s.last_quotes)  # a stream is fresher where it exists
        return list(merged.values())

    def _crypto_status(self) -> dict[str, Any] | None:
        if self.crypto_stream is None:
            return None
        st = self.crypto_stream.status()
        return {**st, "source": "Binance (live, ~1s)", "window": "24h rolling"}

    def status(self) -> dict[str, Any]:
        stream = self.stream.status() if self.stream else None
        if isinstance(self.stream, BseWebStream):
            label, cadence = "BSE website", f"~{getattr(self.stream, 'poll_secs', 2.0):g}s"
        elif isinstance(self.stream, FyersStream):
            label, cadence = "Fyers", "~1s"
        else:
            label, cadence = "Angel One", "~1s"
        if stream and stream["connected"]:
            mode, source = "stream", f"{label} (live, {cadence})"
        elif getattr(self.settings, "market_feed_enabled", True):
            mode = "polling"
            source = f"Polling every {self.settings.market_feed_interval_secs:g}s (delayed)"
        else:
            mode, source = "idle", "Live feed is disabled"
        hint = self.start_error
        if hint is None and stream and stream.get("needs_login"):
            hint = stream.get("error")
        return {
            "mode": mode,
            "source": source,
            "provider": self.provider,
            "market": market_status(),
            "stream": stream,
            "stream_configured": self.stream is not None,
            "crypto": self._crypto_status(),
            "setup_hint": hint,
            "unresolved_symbols": self.unresolved_symbols(),
        }
