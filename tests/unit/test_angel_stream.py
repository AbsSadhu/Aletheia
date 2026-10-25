import asyncio
import json
import struct

import pytest

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata.hours import market_status
from aletheia.extensions.data.angel_session import AngelOneSession
from aletheia.extensions.data.angel_stream import (
    EXCHANGE_CODES,
    STREAM_URL,
    AngelOneStream,
    parse_tick,
)

CREDS = {
    "api_key": "K",
    "client_code": "C1",
    "pin": "1234",
    "totp_secret": "JBSWY3DPEHPK3PXP",  # pragma: allowlist secret (well-known example key)
}


def packet(token: str, ltp_paise: int, *, exch: int = 1, volume: int = 5000, prev_close: int = 0):
    """Binary tick laid out exactly as Angel One's SmartWebSocketV2 parses it (little-endian)."""
    head = struct.pack(
        "<BB25sqqq", 2, exch, token.encode().ljust(25, b"\x00"), 1, 1_700_000_000_000, ltp_paise
    )
    body = struct.pack(
        "<qqqddqqqq",
        10,
        ltp_paise,
        volume,
        1.0,
        2.0,
        ltp_paise - 500,
        ltp_paise + 700,
        ltp_paise - 900,
        prev_close,
    )
    return head + body


class FakeSession(AngelOneSession):
    def __init__(self) -> None:
        super().__init__(CREDS)
        self.jwt, self.feed_token = "JWT", "FEED"
        self._at = 10**12  # never expires

    async def ensure(self) -> bool:
        return True


class FakeWS:
    """Plays back scripted frames, then blocks (like a quiet socket) until closed."""

    def __init__(self, frames: list) -> None:
        self.frames, self.sent, self.closed = list(frames), [], False
        self._done = asyncio.Event()

    async def send(self, msg) -> None:
        self.sent.append(msg)

    async def close(self) -> None:
        self.closed = True
        self._done.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.frames:
            return self.frames.pop(0)
        await self._done.wait()
        raise StopAsyncIteration


def test_parse_tick_reads_every_field_at_the_documented_offsets() -> None:
    t = parse_tick(packet("2885", 123456, volume=777, prev_close=120000))
    assert (t.token, t.exchange_type, t.ltp, t.volume, t.close) == ("2885", 1, 123456, 777, 120000)
    assert (t.open, t.high, t.low) == (122956, 124156, 122556)
    assert t.exchange_ts_ms == 1_700_000_000_000


def test_parse_tick_rejects_short_and_handles_ltp_only_packets() -> None:
    assert parse_tick(b"\x01\x02") is None
    ltp_only = packet("2885", 5000)[:51]
    t = parse_tick(ltp_only)
    assert t.ltp == 5000 and t.volume == 0


async def _make_stream(frames, *, scale_check=None, emit_interval=0.05):
    bus = EventBus()
    got: list[dict] = []

    async def on_q(e) -> None:
        got.append(e.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_q)
    ws = FakeWS(frames)
    seen: dict = {}

    async def connect(url, **kwargs):
        seen["url"], seen["headers"] = url, kwargs["additional_headers"]
        return ws

    s = AngelOneStream(
        FakeSession(), bus, emit_interval=emit_interval, connect=connect, scale_check=scale_check
    )
    await s.set_symbols({("NSE", "RELIANCE"): "2885", ("NSE", "TCS"): "11536"})
    return s, ws, got, seen


async def test_subscribes_and_publishes_scaled_quotes() -> None:
    s, ws, got, seen = await _make_stream([packet("2885", 125050, prev_close=120000)])
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.3)
    s.stop()
    await ws.close()
    await asyncio.wait_for(task, 2)

    assert seen["url"] == STREAM_URL
    assert seen["headers"] == {
        "Authorization": "JWT", "x-api-key": "K", "x-client-code": "C1", "x-feed-token": "FEED",
    }  # fmt: skip
    sub = json.loads(next(m for m in ws.sent if m.startswith("{")))
    assert sub["action"] == 1 and sub["params"]["mode"] == 2
    assert sub["params"]["tokenList"] == [
        {"exchangeType": 1, "tokens": ["11536", "2885"]}
    ]  # sorted, so deterministic

    q = got[0]
    assert (q["symbol"], q["exchange"], q["close"]) == (
        "RELIANCE",
        "NSE",
        1250.5,
    )  # paise -> rupees
    assert q["prev_close"] == 1200.0 and q["change_pct"] == pytest.approx(4.21, abs=0.01)
    assert q["provider"] == "angel_one_stream" and q["stream"] is True


async def test_ticks_are_coalesced_to_one_update_per_interval() -> None:
    frames = [packet("2885", 100000 + i * 10) for i in range(50)]  # 50 ticks in a burst
    s, ws, got, _ = await _make_stream(frames, emit_interval=0.2)
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.1)  # before the first flush
    assert s.ticks_total == 50 and got == []
    await asyncio.sleep(0.3)
    s.stop()
    await ws.close()
    await asyncio.wait_for(task, 2)

    reliance = [q for q in got if q["symbol"] == "RELIANCE"]
    assert len(reliance) == 1 and reliance[0]["close"] == 1004.9  # the LATEST of the burst


async def test_unsubscribed_tokens_and_garbage_are_ignored() -> None:
    s, ws, got, _ = await _make_stream([packet("99999", 1000), b"\x00\x01", "pong"])
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.2)
    s.stop()
    await ws.close()
    await asyncio.wait_for(task, 2)
    assert got == [] and s.ticks_total == 0


async def test_server_error_message_is_surfaced() -> None:
    s, ws, _, _ = await _make_stream(
        [json.dumps({"errorCode": "401", "errorMessage": "Invalid token"})]
    )
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.2)
    assert "Invalid token" in s.status()["error"]
    s.stop()
    await ws.close()
    await asyncio.wait_for(task, 2)


async def test_set_symbols_applies_a_live_diff() -> None:
    s, ws, _, _ = await _make_stream([])
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.2)
    ws.sent.clear()
    await s.set_symbols({("NSE", "RELIANCE"): "2885", ("NSE", "INFY"): "1594"})

    msgs = [json.loads(m) for m in ws.sent if m.startswith("{")]
    add = next(m for m in msgs if m["action"] == 1)
    drop = next(m for m in msgs if m["action"] == 0)
    assert add["params"]["tokenList"][0]["tokens"] == ["1594"]
    assert drop["params"]["tokenList"][0]["tokens"] == ["11536"]
    s.stop()
    await ws.close()
    await asyncio.wait_for(task, 2)


async def test_wrong_price_scale_is_detected_and_corrected() -> None:
    async def ref(symbol, exchange):
        return 1250.5  # REST says the stock is Rs 1250.5

    # Packet carries 1250.5 as a plain rupee value (not paise): divisor must flip to 1.
    s, ws, got, _ = await _make_stream([packet("2885", 1250)], scale_check=ref)
    s._latest = {}
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.3)
    s.stop()
    await ws.close()
    await asyncio.wait_for(task, 2)
    assert s.status()["price_scale_verified"] is True
    assert got[0]["close"] == pytest.approx(1250.0)


async def test_unmatchable_scale_is_flagged_not_hidden() -> None:
    async def ref(symbol, exchange):
        return 777_777.0

    s, ws, got, _ = await _make_stream([packet("2885", 125050)], scale_check=ref)
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.3)
    s.stop()
    await ws.close()
    await asyncio.wait_for(task, 2)
    assert s.status()["price_scale_verified"] is False
    assert got and got[0]["price_scale_verified"] is False


async def test_reconnects_after_a_dropped_connection() -> None:
    bus = EventBus()
    attempts = {"n": 0}
    sockets: list[FakeWS] = []

    async def connect(url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("boom")
        ws = FakeWS([])
        sockets.append(ws)
        return ws

    s = AngelOneStream(FakeSession(), bus, connect=connect, backoff_max=0.05)
    s._stop.clear()
    await s.set_symbols({("NSE", "RELIANCE"): "2885"})
    task = asyncio.create_task(s.run())
    await asyncio.sleep(1.5)
    assert attempts["n"] >= 2 and s.connected and s.reconnects >= 1
    s.stop()
    await sockets[-1].close()
    await asyncio.wait_for(task, 3)


def test_covers_only_streamed_nse_bse_symbols() -> None:
    s = AngelOneStream(FakeSession(), EventBus())
    s._wanted = {(EXCHANGE_CODES["NSE"], "2885"): "RELIANCE"}
    assert s.covers("reliance", "NSE") is True
    assert s.covers("RELIANCE", "BSE") is False
    assert s.covers("BTC/USDT", "BINANCE") is False


def test_market_status_by_ist_clock() -> None:
    from datetime import UTC, datetime

    # 2026-10-26 is a Monday. 04:00 UTC = 09:30 IST (open); 11:00 UTC = 16:30 IST (closed).
    assert market_status(datetime(2026, 10, 26, 4, 0, tzinfo=UTC))["state"] == "open"
    assert market_status(datetime(2026, 10, 26, 11, 0, tzinfo=UTC))["state"] == "closed"
    assert (
        market_status(datetime(2026, 10, 26, 3, 40, tzinfo=UTC))["state"] == "pre_open"
    )  # 09:10 IST
    assert market_status(datetime(2026, 10, 25, 5, 0, tzinfo=UTC))["state"] == "closed"  # Sunday
