"""Per-second live quotes from Angel One's SmartAPI WebSocket 2.0.

Protocol (verified against Angel One's official SDK source, not against a live account):
  - wss://smartapisocket.angelone.in/smart-stream
  - connect headers: Authorization (jwt), x-api-key, x-client-code, x-feed-token
  - subscribe: {"correlationID", "action": 1|0, "params": {"mode": 2, "tokenList": [
        {"exchangeType": 1, "tokens": ["2885", ...]}]}}   (mode 2 = QUOTE: LTP + OHLC + volume)
  - heartbeat: send the text "ping" about every 10 s; the server answers "pong"
  - ticks arrive as little-endian binary packets (layout in `parse_tick`)

Ticks can arrive many times a second for liquid stocks. They are coalesced so each symbol is
published to the event bus at most once per `emit_interval` (default 1 s) -- the UI wants a
steady per-second update, not a firehose. Prices arrive in paise; the first tick of each session
is compared with a REST quote to confirm the divisor, and the divisor self-corrects if it is wrong.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import struct
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata.hours import market_status
from aletheia.extensions.data.angel_session import AngelOneSession

logger = logging.getLogger(__name__)

STREAM_URL = "wss://smartapisocket.angelone.in/smart-stream"
EXCHANGE_CODES = {"NSE": 1, "BSE": 3}
EXCHANGE_NAMES = {v: k for k, v in EXCHANGE_CODES.items()}
MODE_QUOTE = 2
SUBSCRIBE, UNSUBSCRIBE = 1, 0
BATCH = 100  # tokens per subscribe message
PRICE_DIVISOR = 100.0  # paise -> rupees for NSE/BSE cash

_HEAD = struct.Struct("<BB25sqqq")  # mode, exchange, token, seq, exchange_ts, ltp  (51 bytes)
_QUOTE = struct.Struct("<qqqddqqqq")  # last_qty, avg, volume, buy_qty, sell_qty, o, h, l, c (72)

Connect = Callable[..., Any]
ScaleCheck = Callable[[str, str], Awaitable[float | None]]


@dataclass
class Tick:
    token: str
    exchange_type: int
    ltp: int
    last_qty: int = 0
    avg_price: int = 0
    volume: int = 0
    open: int = 0
    high: int = 0
    low: int = 0
    close: int = 0  # previous session's close
    exchange_ts_ms: int = 0


def parse_tick(data: bytes) -> Tick | None:
    """Decode one binary packet (raw integer prices). None for anything too short to be a tick."""
    if len(data) < _HEAD.size:
        return None
    _mode, exch, raw_token, _seq, ts, ltp = _HEAD.unpack_from(data, 0)
    token = raw_token.split(b"\x00", 1)[0].decode("ascii", errors="ignore")
    tick = Tick(token=token, exchange_type=exch, ltp=ltp, exchange_ts_ms=ts)
    if len(data) >= _HEAD.size + _QUOTE.size:
        qty, avg, vol, _bq, _sq, o, h, low, c = _QUOTE.unpack_from(data, _HEAD.size)
        tick.last_qty, tick.avg_price, tick.volume = qty, avg, vol
        tick.open, tick.high, tick.low, tick.close = o, h, low, c
    return tick


class AngelOneStream:
    label = "Angel One"

    def __init__(
        self,
        session: AngelOneSession,
        bus: EventBus,
        emit_interval: float = 1.0,
        connect: Connect | None = None,
        scale_check: ScaleCheck | None = None,
        stale_after_secs: float = 60.0,
        backoff_max: float = 30.0,
    ) -> None:
        self.session = session
        self.bus = bus
        self.emit_interval = emit_interval
        self._connect = connect
        self._scale_check = scale_check
        self.stale_after_secs = stale_after_secs
        self.backoff_max = backoff_max

        self._wanted: dict[tuple[int, str], str] = {}  # (exchange_type, token) -> SYMBOL
        self._subscribed: set[tuple[int, str]] = set()
        self._latest: dict[tuple[int, str], Tick] = {}
        self._dirty: set[tuple[int, str]] = set()
        self._ws: Any = None
        self._stop = asyncio.Event()
        self._bearer = False  # flips if the server wants "Bearer <jwt>" in Authorization
        self._divisor = PRICE_DIVISOR
        self._scale_verified: bool | None = None
        self._scale_checked_at = 0.0

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
            "price_scale_verified": self._scale_verified,
            "error": self.last_error,
        }

    def covers(self, symbol: str, exchange: str) -> bool:
        code = EXCHANGE_CODES.get(exchange.upper())
        return code is not None and any(
            s == symbol.upper() and c == code for (c, _t), s in self._wanted.items()
        )

    async def set_symbols(self, tokens: dict[tuple[str, str], str]) -> None:
        """tokens: {(EXCHANGE, SYMBOL): instrument token}. Applies the diff live if connected."""
        wanted = {
            (EXCHANGE_CODES[exch], tok): sym
            for (exch, sym), tok in tokens.items()
            if exch in EXCHANGE_CODES
        }
        self._wanted = wanted
        if self._ws is not None and self.connected:
            await self._sync_subscriptions()

    async def run(self) -> None:
        """Connect, stream, reconnect forever (until stop())."""
        flusher = asyncio.create_task(self._flush_loop(), name="angel-stream-flush")
        delay = 1.0
        try:
            while not self._stop.is_set():
                try:
                    await self._session_once()
                    delay = 1.0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning("AngelOneStream: %s", self.last_error)
                self.connected = False
                self._ws = None
                self._subscribed.clear()
                if self._stop.is_set():
                    break
                self.reconnects += 1
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                delay = min(delay * 2, self.backoff_max)
        finally:
            flusher.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await flusher

    def stop(self) -> None:
        self._stop.set()

    # -- connection -------------------------------------------------------------

    async def _open(self) -> Any:
        creds = self.session.credentials()
        if creds is None or not await self.session.ensure():
            raise RuntimeError(self.session.last_error or "Angel One login unavailable.")
        if not self.session.feed_token:
            raise RuntimeError("Login succeeded but returned no feed token.")
        jwt = self.session.jwt or ""
        headers = {
            "Authorization": f"Bearer {jwt}" if self._bearer else jwt,
            "x-api-key": creds["api_key"],
            "x-client-code": creds["client_code"],
            "x-feed-token": self.session.feed_token,
        }
        connect = self._connect
        if connect is None:
            from websockets.asyncio.client import connect as ws_connect

            connect = ws_connect
        return await connect(
            STREAM_URL, additional_headers=headers, ping_interval=10, open_timeout=15
        )

    async def _session_once(self) -> None:
        try:
            ws = await self._open()
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403) and not self._bearer:
                # Some deployments want "Bearer <jwt>"; try that form on the next attempt.
                self._bearer = True
                self.session.invalidate()
            raise
        self._ws = ws
        self.connected = True
        self.last_error = None
        logger.info("AngelOneStream: connected, subscribing %d symbols", len(self._wanted))
        heartbeat = asyncio.create_task(self._heartbeat(ws), name="angel-stream-ping")
        watchdog = asyncio.create_task(self._watchdog(ws), name="angel-stream-watchdog")
        try:
            await self._sync_subscriptions()
            async for message in ws:
                if isinstance(message, bytes | bytearray):
                    self._on_packet(bytes(message))
                else:
                    self._on_text(message)
                if self._stop.is_set():
                    break
        finally:
            heartbeat.cancel()
            watchdog.cancel()
            with contextlib.suppress(Exception):
                await ws.close()

    async def _heartbeat(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(10)
            await ws.send("ping")

    async def _watchdog(self, ws: Any) -> None:
        """Reconnect if the socket is up but silent during market hours."""
        while True:
            await asyncio.sleep(10)
            if not market_status()["is_open"] or not self._wanted:
                continue
            ref = self.last_tick_at or 0.0
            if ref and time.time() - ref > self.stale_after_secs:
                logger.warning(
                    "AngelOneStream: no ticks for %.0fs, reconnecting", time.time() - ref
                )
                self.last_error = "No ticks received; reconnecting."
                await ws.close()
                return

    async def _sync_subscriptions(self) -> None:
        ws = self._ws
        if ws is None:
            return
        to_add = self._wanted.keys() - self._subscribed
        to_drop = self._subscribed - self._wanted.keys()
        for action, keys in ((SUBSCRIBE, to_add), (UNSUBSCRIBE, to_drop)):
            by_exchange: dict[int, list[str]] = {}
            for exch, tok in sorted(keys):  # sorted: deterministic message order
                by_exchange.setdefault(exch, []).append(tok)
            for exch, toks in by_exchange.items():
                for i in range(0, len(toks), BATCH):
                    await ws.send(
                        json.dumps(
                            {
                                "correlationID": "aletheia",
                                "action": action,
                                "params": {
                                    "mode": MODE_QUOTE,
                                    "tokenList": [
                                        {"exchangeType": exch, "tokens": toks[i : i + BATCH]}
                                    ],
                                },
                            }
                        )
                    )
        self._subscribed = set(self._wanted)

    # -- inbound ------------------------------------------------------------------

    def _on_text(self, text: str) -> None:
        if text.strip().lower() == "pong":
            return
        try:
            body = json.loads(text)
        except ValueError:
            return
        if isinstance(body, dict) and (body.get("errorCode") or body.get("errorMessage")):
            self.last_error = f"{body.get('errorCode')}: {body.get('errorMessage')}"
            logger.warning("AngelOneStream server error: %s", self.last_error)

    def _on_packet(self, data: bytes) -> None:
        tick = parse_tick(data)
        if tick is None:
            return
        key = (tick.exchange_type, tick.token)
        if key not in self._wanted:
            return
        self._latest[key] = tick
        self._dirty.add(key)
        self.ticks_total += 1
        self.last_tick_at = time.time()

    # -- outbound -------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.emit_interval)
            await self.flush()

    async def flush(self) -> int:
        """Publish the latest tick of every symbol that changed since the last flush."""
        if not self._dirty:
            return 0
        keys, self._dirty = list(self._dirty), set()
        sent = 0
        for key in keys:
            tick = self._latest.get(key)
            symbol = self._wanted.get(key)
            if tick is None or symbol is None:
                continue
            exchange = EXCHANGE_NAMES.get(tick.exchange_type, "NSE")
            if (
                self._scale_verified is None
                and self._scale_check is not None
                and time.time() - self._scale_checked_at > 15
            ):
                self._scale_checked_at = time.time()
                await self._verify_scale(tick, symbol, exchange)
            payload = self._quote(tick, symbol, exchange)
            self.last_quotes[(symbol, exchange)] = payload
            await self.bus.emit(Topics.MARKET_QUOTE, payload, source="angel_stream")
            sent += 1
        return sent

    async def _verify_scale(self, tick: Tick, symbol: str, exchange: str) -> None:
        """Compare the first streamed price with a REST quote; fix the divisor if it is off."""
        assert self._scale_check is not None
        try:
            ref = await self._scale_check(symbol, exchange)
        except Exception as exc:
            logger.debug("AngelOneStream: scale check unavailable: %s", exc)
            return
        if not ref or ref <= 0:
            return  # try again on a later tick
        for divisor in (self._divisor, 1.0):
            if 0.8 <= (tick.ltp / divisor) / ref <= 1.25:
                if divisor != self._divisor:
                    logger.warning("AngelOneStream: price divisor corrected to %s", divisor)
                    self._divisor = divisor
                self._scale_verified = True
                return
        self._scale_verified = False
        logger.error(
            "AngelOneStream: streamed price %s for %s does not match REST %s; flagged unverified",
            tick.ltp,
            symbol,
            ref,
        )

    def _quote(self, tick: Tick, symbol: str, exchange: str) -> dict[str, Any]:
        d = self._divisor
        ltp = tick.ltp / d
        prev = tick.close / d if tick.close else None
        return {
            "symbol": symbol,
            "exchange": exchange,
            "currency": "INR",
            "close": ltp,  # MarketQuote convention: `close` is the latest price
            "open": tick.open / d or None,
            "high": tick.high / d or None,
            "low": tick.low / d or None,
            "volume": float(tick.volume),
            "prev_close": prev,
            "change_pct": round((ltp / prev - 1) * 100, 2) if prev else None,
            "as_of": datetime.now(UTC).isoformat(),
            "provider": "angel_one_stream",
            "stream": True,
            "price_scale_verified": self._scale_verified,
        }
