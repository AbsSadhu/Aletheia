"""Free per-second crypto quotes from Binance's public market-data WebSocket (no account or key).

Protocol (confirmed against the live service):
  - wss://stream.binance.com:9443/stream  (fallback: wss://data-stream.binance.vision/stream)
  - subscribe:   {"method": "SUBSCRIBE",   "params": ["btcusdt@ticker"], "id": 1}
  - unsubscribe: {"method": "UNSUBSCRIBE", "params": [...], "id": 2}
  - each message: {"stream": "btcusdt@ticker", "data": {"E": event ms, "s": "BTCUSDT", "c": last,
                   "o": open, "h": high, "l": low, "v": base volume, "P": change %, ...}}
  - `@ticker` pushes about once per second per symbol, so no coalescing is needed.

The open/high/low/volume/change figures are Binance's rolling 24-hour window, not a calendar day.
Binance closes every connection after 24 hours; the reconnect loop handles that like any drop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from aletheia.core.events.bus import EventBus, Topics

logger = logging.getLogger(__name__)

ENDPOINTS = [
    "wss://stream.binance.com:9443/stream",
    "wss://data-stream.binance.vision/stream",  # Binance's market-data-only host
]
BATCH = 100
_PAIR = re.compile(r"^[a-z0-9]{4,20}$")


def to_stream_name(symbol: str, exchange: str) -> str | None:
    """BTC/USDT on BINANCE -> btcusdt@ticker; anything that isn't a crypto pair -> None."""
    if exchange.upper() != "BINANCE" and "/" not in symbol:
        return None
    pair = symbol.replace("/", "").lower()
    return f"{pair}@ticker" if _PAIR.match(pair) else None


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def tick_to_quote(data: dict[str, Any], display_symbol: str) -> dict[str, Any] | None:
    last = _num(data.get("c"))
    if last is None or last <= 0:
        return None
    event_ms = _num(data.get("E"))
    as_of = (
        datetime.fromtimestamp(event_ms / 1000, UTC)
        if event_ms and event_ms > 0
        else datetime.now(UTC)
    )
    chp = _num(data.get("P"))
    return {
        "symbol": display_symbol,
        "exchange": "BINANCE",
        "currency": display_symbol.split("/")[-1] if "/" in display_symbol else "USDT",
        "close": last,  # MarketQuote convention: `close` is the latest price
        "open": _num(data.get("o")),
        "high": _num(data.get("h")),
        "low": _num(data.get("l")),
        "volume": _num(data.get("v")) or 0.0,
        "prev_close": _num(data.get("o")),  # price 24h ago
        "change_pct": round(chp, 2) if chp is not None else None,
        "window": "24h",
        "as_of": as_of.isoformat(),
        "provider": "binance_stream",
        "stream": True,
        "price_scale_verified": True,
    }


class BinanceStream:
    label = "Binance"

    def __init__(
        self,
        bus: EventBus,
        connect: Any = None,
        endpoints: list[str] | None = None,
        stale_after_secs: float = 60.0,
        backoff_max: float = 60.0,
        watchdog_secs: float = 10.0,
    ) -> None:
        self.bus = bus
        self._connect = connect
        self._endpoints = endpoints or ENDPOINTS
        self.stale_after_secs = stale_after_secs
        self.backoff_max = backoff_max
        self.watchdog_secs = watchdog_secs

        self._wanted: dict[str, str] = {}  # stream name -> display symbol
        self._subscribed: set[str] = set()
        self._ws: Any = None
        self._stop = asyncio.Event()
        self._msg_id = 0
        self._endpoint_index = 0

        self.connected = False
        self.last_error: str | None = None
        self.last_tick_at: float | None = None
        self.ticks_total = 0
        self.reconnects = 0
        self.last_quotes: dict[tuple[str, str], dict[str, Any]] = {}

    # -- public ---------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        age = None if self.last_tick_at is None else round(time.time() - self.last_tick_at, 1)
        return {
            "connected": self.connected,
            "symbols": len(self._wanted),
            "ticks": self.ticks_total,
            "last_tick_age_secs": age,
            "reconnects": self.reconnects,
            "endpoint": self._endpoints[self._endpoint_index % len(self._endpoints)],
            "error": self.last_error,
        }

    def covers(self, symbol: str, exchange: str) -> bool:
        return to_stream_name(symbol, exchange) in self._wanted

    async def set_symbols(self, mapping: dict[tuple[str, str], str]) -> None:
        """mapping: {(EXCHANGE, SYMBOL): stream name}. Applied live when connected."""
        self._wanted = {name: sym for (_exch, sym), name in mapping.items()}
        if self._ws is not None and self.connected:
            await self._sync()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        delay = min(1.0, self.backoff_max)
        while not self._stop.is_set():
            endpoint = self._endpoints[self._endpoint_index % len(self._endpoints)]
            try:
                await self._session(endpoint)
                delay = min(1.0, self.backoff_max)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 451:
                    self.last_error = (
                        "Binance is not available from your location (HTTP 451); trying the "
                        "market-data host."
                    )
                else:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("BinanceStream (%s): %s", endpoint, self.last_error)
                self._endpoint_index += 1  # try the other host next time
            self.connected = False
            self._ws = None
            self._subscribed.clear()
            if self._stop.is_set():
                break
            self.reconnects += 1
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            delay = min(delay * 2, self.backoff_max)

    # -- connection -------------------------------------------------------------

    async def _session(self, endpoint: str) -> None:
        connect = self._connect
        if connect is None:
            from websockets.asyncio.client import connect as ws_connect

            connect = ws_connect
        ws = await connect(endpoint, ping_interval=20, open_timeout=15)
        self._ws = ws
        self.connected = True
        self.last_error = None
        self.last_tick_at = time.time()  # the silence clock starts at connect
        logger.info("BinanceStream: connected to %s, %d symbols", endpoint, len(self._wanted))
        watchdog = asyncio.create_task(self._watchdog(ws), name="binance-watchdog")
        try:
            await self._sync()
            async for raw in ws:
                await self._on_message(raw)
                if self._stop.is_set():
                    break
        finally:
            watchdog.cancel()
            with contextlib.suppress(Exception):
                await ws.close()

    async def _watchdog(self, ws: Any) -> None:
        """Crypto trades 24/7, so total silence on a connection with symbols means it is dead."""
        while True:
            await asyncio.sleep(self.watchdog_secs)
            if not self._wanted or self.last_tick_at is None:
                continue
            if time.time() - self.last_tick_at > self.stale_after_secs:
                self.last_error = "No data received; reconnecting."
                await ws.close()
                return

    async def _sync(self) -> None:
        ws = self._ws
        if ws is None:
            return
        for method, names in (
            ("SUBSCRIBE", sorted(self._wanted.keys() - self._subscribed)),
            ("UNSUBSCRIBE", sorted(self._subscribed - self._wanted.keys())),
        ):
            for i in range(0, len(names), BATCH):
                self._msg_id += 1
                await ws.send(
                    json.dumps(
                        {"method": method, "params": names[i : i + BATCH], "id": self._msg_id}
                    )
                )
        self._subscribed = set(self._wanted)

    # -- inbound ------------------------------------------------------------------

    async def _on_message(self, raw: Any) -> None:
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(msg, dict):
            return
        if "code" in msg and "msg" in msg:  # {"code": 2, "msg": "Invalid request", ...}
            self.last_error = f"{msg['code']}: {msg['msg']}"
            return
        name, data = msg.get("stream"), msg.get("data")
        if not isinstance(data, dict) or name not in self._wanted:
            return  # subscription acks and anything we didn't ask for
        display = self._wanted[name]
        quote = tick_to_quote(data, display)
        if quote is None:
            return
        self.ticks_total += 1
        self.last_tick_at = time.time()
        self.last_quotes[(display, "BINANCE")] = quote
        await self.bus.emit(Topics.MARKET_QUOTE, quote, source="binance_stream")
