import asyncio
import json
from types import SimpleNamespace


from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata import feed_manager
from aletheia.core.marketdata.feed_manager import FeedManager
from aletheia.core.marketdata.live_feed import MarketFeedPoller
from aletheia.core.marketdata.watchlist import WatchItem, WatchlistStore
from aletheia.extensions.data.binance_stream import (
    BinanceStream,
    tick_to_quote,
    to_stream_name,
)

# A real `btcusdt@ticker` payload captured from stream.binance.com during development.
REAL = {
    "e": "24hrTicker", "E": 1792934368015, "s": "BTCUSDT", "p": "-320.05", "P": "-0.397",
    "w": "80300.1", "x": "80712.39000000", "c": "80392.34000000", "Q": "0.001", "b": "80392.33",
    "B": "1.2", "a": "80392.34", "A": "0.9", "o": "80712.39000000", "h": "81033.69000000",
    "l": "79220.74000000", "v": "9594.83647000", "q": "770000000.1",
}  # fmt: skip


def frame(name="btcusdt@ticker", **over):
    return json.dumps({"stream": name, "data": {**REAL, **over}})


class FakeWS:
    def __init__(self, frames=()):
        self.frames, self.sent, self.closed = list(frames), [], False
        self._done = asyncio.Event()

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    async def close(self):
        self.closed = True
        self._done.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.frames:
            return self.frames.pop(0)
        await self._done.wait()
        raise StopAsyncIteration


def test_stream_name_mapping() -> None:
    assert to_stream_name("BTC/USDT", "BINANCE") == "btcusdt@ticker"
    assert to_stream_name("eth/usdt", "NSE") == "ethusdt@ticker"  # a slash means crypto
    assert to_stream_name("RELIANCE", "NSE") is None
    assert to_stream_name("BAD PAIR!", "BINANCE") is None
    assert to_stream_name("X", "BINANCE") is None  # too short to be a pair


def test_real_binance_payload_becomes_a_quote() -> None:
    q = tick_to_quote(REAL, "BTC/USDT")
    assert (q["symbol"], q["exchange"], q["currency"]) == ("BTC/USDT", "BINANCE", "USDT")
    assert q["close"] == 80392.34 and q["high"] == 81033.69 and q["low"] == 79220.74
    assert q["volume"] == 9594.83647 and q["change_pct"] == -0.4 and q["window"] == "24h"
    assert q["as_of"].startswith("2026-10-")  # event time E, not receive time
    assert q["provider"] == "binance_stream" and q["stream"] is True


def test_unusable_payloads_are_rejected() -> None:
    assert tick_to_quote({**REAL, "c": "0"}, "BTC/USDT") is None
    assert tick_to_quote({**REAL, "c": None}, "BTC/USDT") is None
    assert tick_to_quote({**REAL, "c": "nan"}, "BTC/USDT") is None
    assert tick_to_quote({}, "BTC/USDT") is None


async def _running(frames, *, connect=None, **kw):
    bus = EventBus()
    got: list[dict] = []

    async def on_q(e):
        got.append(e.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_q)
    ws = FakeWS(frames)

    async def default_connect(url, **kwargs):
        return ws

    s = BinanceStream(bus, connect=connect or default_connect, backoff_max=0.05, **kw)
    await s.set_symbols(
        {("BINANCE", "BTC/USDT"): "btcusdt@ticker", ("BINANCE", "ETH/USDT"): "ethusdt@ticker"}
    )
    task = asyncio.create_task(s.run())
    return s, ws, got, task


async def _finish(s, ws, task):
    s.stop()
    await ws.close()
    await asyncio.wait_for(task, 3)


async def test_subscribes_then_publishes_each_tick_immediately() -> None:
    s, ws, got, task = await _running([frame(), frame("ethusdt@ticker", s="ETHUSDT", c="2300.5")])
    await asyncio.sleep(0.2)
    try:
        sub = ws.sent[0]
        assert sub["method"] == "SUBSCRIBE" and sub["params"] == [
            "btcusdt@ticker",
            "ethusdt@ticker",
        ]
        assert [q["symbol"] for q in got] == ["BTC/USDT", "ETH/USDT"]
        assert s.status()["connected"] is True and s.status()["ticks"] == 2
        assert s.last_quotes[("BTC/USDT", "BINANCE")]["close"] == 80392.34
        assert s.covers("BTC/USDT", "BINANCE") and not s.covers("RELIANCE", "NSE")
    finally:
        await _finish(s, ws, task)


async def test_acks_unknown_streams_and_garbage_are_ignored() -> None:
    frames = [
        json.dumps({"result": None, "id": 1}),
        frame("dogeusdt@ticker"),
        "not json",
        "[1,2]",
        frame(),
    ]
    s, ws, got, task = await _running(frames)
    await asyncio.sleep(0.2)
    try:
        assert len(got) == 1 and got[0]["symbol"] == "BTC/USDT"
    finally:
        await _finish(s, ws, task)


async def test_server_error_message_is_surfaced() -> None:
    s, ws, _, task = await _running([json.dumps({"code": 2, "msg": "Invalid request"})])
    await asyncio.sleep(0.2)
    try:
        assert "Invalid request" in s.status()["error"]
    finally:
        await _finish(s, ws, task)


async def test_watchlist_changes_apply_live_without_reconnecting() -> None:
    s, ws, _, task = await _running([])
    await asyncio.sleep(0.2)
    ws.sent.clear()
    await s.set_symbols(
        {("BINANCE", "BTC/USDT"): "btcusdt@ticker", ("BINANCE", "SOL/USDT"): "solusdt@ticker"}
    )
    try:
        by_method = {m["method"]: m["params"] for m in ws.sent}
        assert by_method == {"SUBSCRIBE": ["solusdt@ticker"], "UNSUBSCRIBE": ["ethusdt@ticker"]}
        assert s.status()["reconnects"] == 0
    finally:
        await _finish(s, ws, task)


async def test_falls_back_to_the_market_data_host_when_blocked() -> None:
    tried: list[str] = []
    ws = FakeWS([frame()])

    class Blocked(Exception):
        response = SimpleNamespace(status_code=451)

    async def connect(url, **kwargs):
        tried.append(url)
        if len(tried) == 1:
            raise Blocked("server rejected WebSocket connection: HTTP 451")
        return ws

    s, _, got, task = await _running([], connect=connect)
    await asyncio.sleep(1.2)
    try:
        assert len(tried) >= 2 and tried[0] != tried[1]
        assert "binance.vision" in tried[1]
        assert s.status()["connected"] is True
    finally:
        s.stop()
        await ws.close()
        await asyncio.wait_for(task, 3)


async def test_451_error_message_explains_the_region_block() -> None:
    class Blocked(Exception):
        response = SimpleNamespace(status_code=451)

    async def always_blocked(url, **kwargs):
        raise Blocked("HTTP 451")

    s, _, _, task = await _running([], connect=always_blocked)
    await asyncio.sleep(0.3)
    try:
        assert "location" in s.status()["error"] and s.status()["connected"] is False
    finally:
        s.stop()
        await asyncio.wait_for(task, 3)


async def test_reconnects_after_a_dropped_connection() -> None:
    sockets: list[FakeWS] = []

    async def connect(url, **kwargs):
        ws = FakeWS([frame()] if len(sockets) == 0 else [])
        if len(sockets) == 0:
            ws._done.set()  # first connection ends right after its one tick
        sockets.append(ws)
        return ws

    s, _, got, task = await _running([], connect=connect)
    await asyncio.sleep(1.0)
    try:
        assert (
            len(sockets) >= 2 and s.status()["reconnects"] >= 1 and s.status()["connected"] is True
        )
        assert len(got) == 1
        assert sockets[1].sent[0]["method"] == "SUBSCRIBE"  # resubscribed on the new connection
    finally:
        s.stop()
        await sockets[-1].close()
        await asyncio.wait_for(task, 3)


async def test_silent_connection_is_restarted() -> None:
    sockets: list[FakeWS] = []

    async def connect(url, **kwargs):
        ws = FakeWS([])
        sockets.append(ws)
        return ws

    s, _, _, task = await _running([], connect=connect, stale_after_secs=0.2, watchdog_secs=0.1)
    await asyncio.sleep(1.2)
    try:
        assert len(sockets) >= 2 and sockets[0].closed
    finally:
        s.stop()
        await sockets[-1].close()
        await asyncio.wait_for(task, 3)


# -- the feed manager running it alongside the stock feed ---------------------------------
class _Collector:
    async def collect_for_holding(self, holding):  # pragma: no cover
        raise AssertionError


class _FakeBinance:
    """Stands in for BinanceStream so manager tests never touch the network."""

    label = "Binance"

    def __init__(self, bus):
        self.connected = True
        self.symbols = {}
        self.last_quotes = {
            ("BTC/USDT", "BINANCE"): {"symbol": "BTC/USDT", "close": 80000.0, "stream": True}
        }

    async def run(self):
        await asyncio.sleep(3600)

    def stop(self):
        pass

    async def set_symbols(self, mapping):
        self.symbols = mapping

    def covers(self, symbol, exchange):
        return to_stream_name(symbol, exchange) in self.symbols.values()

    def status(self):
        return {
            "connected": self.connected,
            "symbols": len(self.symbols),
            "ticks": 3,
            "last_tick_age_secs": 0.4,
            "reconnects": 0,
            "error": None,
        }


def _manager(tmp_path, monkeypatch, enabled=True):
    monkeypatch.setattr(feed_manager, "BinanceStream", _FakeBinance)
    store = WatchlistStore(tmp_path / "w.json")
    store.save(
        [WatchItem(symbol="BTC/USDT", exchange="BINANCE"), WatchItem(symbol="TCS", exchange="NSE")]
    )
    settings = SimpleNamespace(
        live_feed_provider="angel_one", angel_one_enabled=False, crypto_stream_enabled=enabled,
        market_feed_enabled=True, market_feed_interval_secs=15.0, market_feed_emit_interval_secs=1.0,
    )  # fmt: skip
    bus = EventBus()
    return FeedManager(settings, bus, store, MarketFeedPoller(_Collector(), bus)), store


async def test_manager_streams_crypto_with_no_broker_configured(tmp_path, monkeypatch) -> None:
    m, _ = _manager(tmp_path, monkeypatch)
    await m.start()
    try:
        assert (
            m.stream is None and m.crypto_stream is not None
        )  # no stock broker, crypto still live
        assert m.crypto_stream.symbols == {
            ("BINANCE", "BTC/USDT"): "btcusdt@ticker"
        }  # stocks excluded
        st = m.status()
        assert st["mode"] == "polling" and st["crypto"]["connected"] is True
        assert st["crypto"]["source"].startswith("Binance")
        assert any(q["symbol"] == "BTC/USDT" and q["stream"] for q in m.snapshot())
    finally:
        await m.stop()


async def test_poller_leaves_connected_crypto_to_the_stream_but_still_polls_stocks(
    tmp_path, monkeypatch
) -> None:
    m, _ = _manager(tmp_path, monkeypatch)
    await m.start()
    try:
        assert m.poller._skip("BTC/USDT", "BINANCE") is True
        assert m.poller._skip("TCS", "NSE") is False
        m.crypto_stream.connected = False  # stream down: the poller takes crypto back
        assert m.poller._skip("BTC/USDT", "BINANCE") is False
    finally:
        await m.stop()


async def test_crypto_stream_can_be_switched_off(tmp_path, monkeypatch) -> None:
    m, _ = _manager(tmp_path, monkeypatch, enabled=False)
    await m.start()
    assert m.crypto_stream is None and m.status()["crypto"] is None


async def test_start_is_idempotent(tmp_path, monkeypatch) -> None:
    m, _ = _manager(tmp_path, monkeypatch)
    await m.start()
    first = m.crypto_stream
    await m.start()
    try:
        assert m.crypto_stream is first
    finally:
        await m.stop()
