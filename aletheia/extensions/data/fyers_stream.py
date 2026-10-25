"""Per-second live quotes from Fyers, via their official SDK running in a helper process.

See `fyers_bridge.py` for why the SDK runs in its own process and virtualenv. This module owns
that process: starts it, feeds it the watchlist, turns its JSON-line ticks into Aletheia quotes,
coalesces them to at most one publish per symbol per `emit_interval`, and restarts it when it
dies or goes silent. If Fyers reports an expired token it stops retrying (a restart can't fix
that) and waits for a fresh login.

Fyers' stream carries prices in rupees (unlike Angel One's paise), and each tick includes the
exchange's last-trade time, which we pass through so the UI's "age" reflects real staleness.
Only NSE cash equities are mapped (`NSE:SBIN-EQ`); BSE series suffixes vary per stock.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata.hours import market_status

logger = logging.getLogger(__name__)

BRIDGE_PATH = Path(__file__).with_name("fyers_bridge.py")
# Observed from the real SDK: -300 = token could not be decoded (Please provide valid token),
# -99 = token expired, 11001 = Fyers' server rejected authentication. The -8/-15/-16/-17 codes
# are Fyers' REST token errors, kept in case the stream ever surfaces them.
TOKEN_ERROR_CODES = {-8, -15, -16, -17, -99, -300, 11001}


def default_python() -> Path:
    """The isolated interpreter `scripts/fyers_setup.py` creates."""
    venv = Path.home() / ".aletheia" / "fyers-venv"
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def to_fyers_symbol(symbol: str, exchange: str) -> str | None:
    if exchange.upper() != "NSE" or "/" in symbol:
        return None
    return f"NSE:{symbol.upper()}-EQ"


def from_fyers_symbol(fyers_symbol: str) -> tuple[str, str] | None:
    exch, _, rest = fyers_symbol.partition(":")
    if not rest or not rest.endswith("-EQ"):
        return None
    return rest.removesuffix("-EQ"), exch


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def tick_to_quote(tick: dict[str, Any]) -> dict[str, Any] | None:
    """Fyers SymbolUpdate dict -> the quote shape the feed publishes. None if unusable."""
    parsed = from_fyers_symbol(str(tick.get("symbol", "")))
    ltp = _num(tick.get("ltp"))
    if parsed is None or ltp is None or ltp <= 0:
        return None
    symbol, exchange = parsed
    traded = _num(tick.get("last_traded_time"))
    now = time.time()
    # Use the exchange's trade time when it is plausible; otherwise our receive time.
    stamp = traded if traded and now - 7 * 86400 < traded <= now + 300 else now
    prev = _num(tick.get("prev_close_price"))
    chp = _num(tick.get("chp"))
    # Prefer Fyers' own percentage; derive it from the previous close if it is absent.
    change_pct = (
        round(chp, 2) if chp is not None else (round((ltp / prev - 1) * 100, 2) if prev else None)
    )
    return {
        "symbol": symbol,
        "exchange": exchange,
        "currency": "INR",
        "close": ltp,  # MarketQuote convention: `close` is the latest price
        "open": _num(tick.get("open_price")) or None,
        "high": _num(tick.get("high_price")) or None,
        "low": _num(tick.get("low_price")) or None,
        "volume": float(_num(tick.get("vol_traded_today")) or 0.0),
        "prev_close": prev or None,
        "change_pct": change_pct,
        "as_of": datetime.fromtimestamp(stamp, UTC).isoformat(),
        "provider": "fyers_stream",
        "stream": True,
        "price_scale_verified": True,  # rupees by contract, no paise conversion to get wrong
    }


Spawner = Callable[[], Awaitable[Any]]


class FyersStream:
    label = "Fyers"

    def __init__(
        self,
        token_provider: Callable[[], str | None],
        bus: EventBus,
        emit_interval: float = 1.0,
        python: Path | None = None,
        bridge: Path = BRIDGE_PATH,
        spawn: Spawner | None = None,
        stale_after_secs: float = 60.0,
        backoff_max: float = 30.0,
        token_poll_secs: float = 5.0,
    ) -> None:
        self._token_provider = token_provider
        self.bus = bus
        self.emit_interval = emit_interval
        self._python = python or default_python()
        self._bridge = bridge
        self._spawn = spawn
        self.stale_after_secs = stale_after_secs
        self.backoff_max = backoff_max
        self.token_poll_secs = token_poll_secs

        self._wanted: dict[str, tuple[str, str]] = {}  # fyers symbol -> (SYMBOL, EXCHANGE)
        self._proc: Any = None
        self._stop = asyncio.Event()
        self._dirty: set[str] = set()
        self._latest: dict[str, dict[str, Any]] = {}
        self._bad_token: str | None = None

        self.connected = False
        self.last_error: str | None = None
        self.needs_login = False
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
            "price_scale_verified": True,
            "needs_login": self.needs_login,
            "error": self.last_error,
        }

    def covers(self, symbol: str, exchange: str) -> bool:
        return to_fyers_symbol(symbol, exchange) in self._wanted

    async def set_symbols(self, mapping: dict[tuple[str, str], str]) -> None:
        """mapping: {(EXCHANGE, SYMBOL): fyers symbol}. Applied live when the helper is running."""
        self._wanted = {fy: (sym, exch) for (exch, sym), fy in mapping.items()}
        await self._send({"cmd": "set", "symbols": sorted(self._wanted)})

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        flusher = asyncio.create_task(self._flush_loop(), name="fyers-flush")
        delay = 1.0
        try:
            while not self._stop.is_set():
                token = self._token_provider()
                if not token or token == self._bad_token:
                    self.needs_login = True
                    self.last_error = (
                        "Fyers login required."
                        if not token
                        else "Fyers login expired; log in again."
                    )
                    await self._sleep(self.token_poll_secs)
                    continue
                self.needs_login = False
                try:
                    await self._run_once(token)
                    delay = 1.0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning("FyersStream: %s", self.last_error)
                self.connected = False
                self._proc = None
                if self._stop.is_set() or self.needs_login:
                    continue
                self.reconnects += 1
                await self._sleep(delay)
                delay = min(delay * 2, self.backoff_max)
        finally:
            flusher.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await flusher
            await self._kill()

    # -- helper process ------------------------------------------------------------

    async def _sleep(self, secs: float) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=secs)

    async def _launch(self) -> Any:
        if self._spawn is not None:
            return await self._spawn()
        if not self._python.exists():
            raise RuntimeError(
                f"Fyers helper environment not found at {self._python}. "
                "Run: .venv\\Scripts\\python.exe scripts\\fyers_setup.py"
            )
        return await asyncio.create_subprocess_exec(
            str(self._python),
            str(self._bridge),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def _send(self, obj: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            proc.stdin.write((json.dumps(obj) + "\n").encode())
            await proc.stdin.drain()
        except (ConnectionError, RuntimeError, OSError):
            pass  # the process is going away; run() will restart it

    async def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        with contextlib.suppress(Exception):
            if proc.stdin:
                proc.stdin.write(b'{"cmd": "stop"}\n')
                await proc.stdin.drain()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except Exception:
            with contextlib.suppress(Exception):
                proc.terminate()

    async def _run_once(self, token: str) -> None:
        self._proc = proc = await self._launch()
        await self._send(
            {"cmd": "start", "token": token, "symbols": sorted(self._wanted), "log_dir": ""}
        )
        drain = asyncio.create_task(self._drain_stderr(proc))
        watchdog = asyncio.create_task(self._watchdog(proc))
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break  # helper exited
                self._on_line(line.decode("utf-8", errors="replace"), token)
                if self.needs_login or self._stop.is_set():
                    break
        finally:
            drain.cancel()
            watchdog.cancel()
            await self._kill()
        if not self.needs_login and not self._stop.is_set() and self.last_error is None:
            self.last_error = "Fyers helper process exited."

    async def _drain_stderr(self, proc: Any) -> None:
        if proc.stderr is None:
            return
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            logger.debug("fyers-bridge: %s", line.decode("utf-8", errors="replace").rstrip())

    async def _watchdog(self, proc: Any) -> None:
        while True:
            await asyncio.sleep(10)
            if not market_status()["is_open"] or not self._wanted or not self.last_tick_at:
                continue
            if time.time() - self.last_tick_at > self.stale_after_secs:
                self.last_error = "No ticks received; restarting the Fyers helper."
                with contextlib.suppress(Exception):
                    proc.terminate()
                return

    # -- inbound --------------------------------------------------------------------

    def _on_line(self, line: str, token: str) -> None:
        try:
            msg = json.loads(line)
        except ValueError:
            return
        ev = msg.get("ev")
        if ev == "connected":
            # The socket opened, but the SDK reports this even when login then fails (seen with a
            # bad token), so it does NOT mean "streaming". Wait for the authentication ack below.
            return
        if ev == "info":
            data = msg.get("data")
            if isinstance(data, dict) and data.get("type") == "cn" and data.get("s") == "ok":
                self.connected = True  # "Authentication done"
                self.last_error = None
        elif ev == "tick":
            quote = tick_to_quote(msg.get("data") or {})
            if quote is None:
                return
            key = f"{quote['exchange']}:{quote['symbol']}"
            self._latest[key] = quote
            self._dirty.add(key)
            self.ticks_total += 1
            self.last_tick_at = time.time()
        elif ev == "closed":
            self.connected = False
        elif ev == "fatal":
            self.last_error = str(msg.get("message"))
            logger.error("FyersStream fatal: %s", self.last_error)
            self.connected = False
            if "not installed" in self.last_error:
                self._stop.set()  # retrying can't install a package; the hint says what to do
        elif ev == "error":
            data = msg.get("data")
            code = data.get("code") if isinstance(data, dict) else None
            auth_error = isinstance(data, dict) and data.get("type") == "cn"
            text = json.dumps(data) if not isinstance(data, str) else data
            self.last_error = text
            lowered = text.lower()
            if (
                code in TOKEN_ERROR_CODES
                or auth_error
                or "expired" in lowered
                or "valid token" in lowered
            ):
                self._bad_token = token
                self.needs_login = True
                self.connected = False
                self.last_error = "Fyers login expired or invalid; log in again."

    # -- outbound -------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.emit_interval)
            await self.flush()

    async def flush(self) -> int:
        if not self._dirty:
            return 0
        keys, self._dirty = list(self._dirty), set()
        sent = 0
        for key in keys:
            quote = self._latest.get(key)
            if quote is None:
                continue
            self.last_quotes[(quote["symbol"], quote["exchange"])] = quote
            await self.bus.emit(Topics.MARKET_QUOTE, quote, source="fyers_stream")
            sent += 1
        return sent
