import asyncio
import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata import feed_manager
from aletheia.core.marketdata.feed_manager import FeedManager
from aletheia.core.marketdata.live_feed import MarketFeedPoller
from aletheia.core.marketdata.watchlist import WatchItem, WatchlistStore
from aletheia.extensions.data.bse_web_stream import (
    BseWebStream,
    load_bse_scrips,
    parse_ason,
    parse_quote,
)

# A real getScripHeaderData response for Reliance (scrip 500325), captured during development.
REAL = {
    "CurrRate": {"LTP": "1190.00", "Chg": "+14.00", "PcChg": "+1.19"},
    "Cmpname": {"FullN": "Reliance Industries Ltd"},
    "Header": {
        "Ason": "23 Oct 26 | 16:00", "LTP": "1190.00", "PrevClose": "1176.00",
        "Open": "1184.75", "High": "1201.95", "Low": "1163.25", "Category": "Listed",
    },
}  # fmt: skip

# Monday 26 Oct 2026, 10:20 IST == 04:50 UTC: inside market hours.
MON_OPEN = datetime(2026, 10, 26, 4, 50, tzinfo=UTC)


def test_ason_is_parsed_as_ist() -> None:
    assert parse_ason("23 Oct 26 | 16:00") == datetime(2026, 10, 23, 10, 30, tzinfo=UTC)
    assert parse_ason("garbage") is None and parse_ason(None) is None


def test_real_payload_becomes_a_quote_with_lag_only_during_market_hours() -> None:
    q = parse_quote(REAL, "RELIANCE", "NSE", MON_OPEN, market_open=True)
    assert (q["symbol"], q["exchange"], q["price_exchange"]) == ("RELIANCE", "NSE", "BSE")
    assert q["close"] == 1190.0 and q["open"] == 1184.75 and q["high"] == 1201.95
    assert q["low"] == 1163.25 and q["prev_close"] == 1176.0 and q["change_pct"] == 1.19
    assert q["provider"] == "bse_web" and q["volume"] is None
    assert q["exchange_time"].startswith("2026-10-23T10:30")
    assert (
        q["data_lag_secs"] > 3 * 86400 * 0.9
    )  # Friday's close seen on Monday morning: obviously stale

    closed = parse_quote(REAL, "RELIANCE", "NSE", MON_OPEN, market_open=False)
    assert closed["data_lag_secs"] is None  # no alarm when nothing is supposed to be moving


def test_unusable_payloads_are_rejected() -> None:
    assert parse_quote({}, "X", "NSE", MON_OPEN, True) is None
    assert parse_quote({"Header": {"LTP": "0"}}, "X", "NSE", MON_OPEN, True) is None
    assert parse_quote({"Header": {"LTP": "abc"}}, "X", "NSE", MON_OPEN, True) is None


def _transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_scrip_list_maps_ids_and_is_cached(tmp_path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json=[
                {"SCRIP_CD": "500325", "scrip_id": "RELIANCE", "Scrip_Name": "Reliance"},
                {"SCRIP_CD": "999999", "scrip_id": "RELIANCE", "Scrip_Name": "dup"},
                {"SCRIP_CD": "500520", "scrip_id": "m&m"},
                {"SCRIP_CD": "", "scrip_id": "BAD"},
            ],
        )

    path = tmp_path / "scrips.json"
    mapping = await load_bse_scrips(path, _transport(handler))
    assert mapping == {
        "RELIANCE": "500325",
        "M&M": "500520",
    }  # first wins; blanks dropped; upper-cased
    again = await load_bse_scrips(path, _transport(handler))
    assert again == mapping and calls["n"] == 1  # second call came from the day cache


def _stream(handler, **kw):
    bus = EventBus()
    got: list[dict] = []

    async def on_q(e) -> None:
        got.append(e.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_q)
    s = BseWebStream(bus, client=_transport(handler), **kw)
    return s, got


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=REAL)


async def test_poll_publishes_one_quote_per_symbol_keeping_the_watchlist_row() -> None:
    s, got = _stream(_ok)
    await s.set_symbols({("NSE", "RELIANCE"): "500325", ("BSE", "TCS"): "532540"})
    assert await s.poll_once() == 2
    assert {(q["symbol"], q["exchange"]) for q in got} == {("RELIANCE", "NSE"), ("TCS", "BSE")}
    assert all(q["price_exchange"] == "BSE" and q["stream"] for q in got)
    st = s.status()
    assert st["connected"] is True and st["ticks"] == 2 and st["unofficial"] is True
    assert s.covers("reliance", "NSE") and not s.covers("RELIANCE", "BSE")


async def test_requests_are_globally_rate_limited() -> None:
    starts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(time.monotonic())
        return httpx.Response(200, json=REAL)

    s, _ = _stream(handler, max_rps=20.0)  # one request start per 50 ms
    await s.set_symbols({("NSE", f"S{i}"): str(500000 + i) for i in range(8)})
    await s.poll_once()
    gaps = [b - a for a, b in zip(sorted(starts), sorted(starts)[1:])]
    assert len(starts) == 8 and min(gaps) >= 0.04  # never a burst, however many symbols


async def test_backs_off_when_bse_refuses_then_recovers() -> None:
    mode = {"status": 429}

    def handler(request: httpx.Request) -> httpx.Response:
        if mode["status"] == 429:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json=REAL)

    s, got = _stream(handler)
    await s.set_symbols({("NSE", "RELIANCE"): "500325"})
    for expected_penalty in (2.0, 4.0, 8.0):
        await s.poll_once()
        assert s._penalty == expected_penalty  # exponential, so we ease off instead of hammering
    assert s.status()["connected"] is False and "429" in s.status()["error"]
    assert got == []

    mode["status"] = 200
    assert await s.poll_once() == 1
    assert s.status()["connected"] is True and s._penalty == 0 and s.status()["reconnects"] == 1


async def test_penalty_is_capped_at_a_minute() -> None:
    s, _ = _stream(lambda r: httpx.Response(503))
    await s.set_symbols({("NSE", "RELIANCE"): "500325"})
    for _ in range(10):
        await s.poll_once()
    assert s._penalty == 60.0


async def test_bad_responses_do_not_crash_or_publish() -> None:
    s, got = _stream(lambda r: httpx.Response(200, text="<html>maintenance</html>"))
    await s.set_symbols({("NSE", "RELIANCE"): "500325"})
    assert await s.poll_once() == 0 and got == []
    assert "non-JSON" in s.status()["error"]

    def boom(request):
        raise httpx.ConnectError("no route")

    s2, _ = _stream(boom)
    await s2.set_symbols({("NSE", "RELIANCE"): "500325"})
    assert await s2.poll_once() == 0 and "ConnectError" in s2.status()["error"]


async def test_stale_exchange_data_is_surfaced_as_lag_not_hidden() -> None:
    # Exchange 'as on' time is 20 minutes before we fetched it, during market hours.
    payload = json.loads(json.dumps(REAL))
    payload["Header"]["Ason"] = "26 Oct 26 | 10:00"
    clock = lambda: MON_OPEN  # 10:20 IST  # noqa: E731
    s, got = _stream(lambda r: httpx.Response(200, json=payload), clock=clock)
    await s.set_symbols({("NSE", "RELIANCE"): "500325"})
    await s.poll_once()
    assert got[0]["data_lag_secs"] == 1200
    assert s.status()["data_lag_secs"] == 1200  # the UI shows "data 20 min old"

    fresh = json.loads(json.dumps(REAL))
    fresh["Header"]["Ason"] = "26 Oct 26 | 10:20"
    s2, got2 = _stream(lambda r: httpx.Response(200, json=fresh), clock=clock)
    await s2.set_symbols({("NSE", "RELIANCE"): "500325"})
    await s2.poll_once()
    assert got2[0]["data_lag_secs"] == 0


def test_poll_interval_has_a_one_second_floor() -> None:
    assert BseWebStream(EventBus(), poll_secs=0.01).poll_secs == 1.0


async def test_run_polls_and_stops_promptly() -> None:
    s, got = _stream(_ok, poll_secs=1.0)
    await s.set_symbols({("NSE", "RELIANCE"): "500325"})
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.3)
    s.stop()
    await asyncio.wait_for(task, 3)
    assert len(got) >= 1


async def test_nothing_to_poll_makes_no_requests() -> None:
    called = []
    s, _ = _stream(lambda r: called.append(1) or httpx.Response(200, json=REAL))
    assert await s.poll_once() == 0 and called == []


# -- feed manager with provider = bse_web --------------------------------------------------
class _Collector:
    async def collect_for_holding(self, holding):  # pragma: no cover
        raise AssertionError


def _manager(tmp_path, monkeypatch, scrips=None):
    async def fake_load(*a, **k):
        if scrips is None:
            raise RuntimeError("BSE unreachable")
        return scrips

    monkeypatch.setattr(feed_manager, "load_bse_scrips", fake_load)
    store = WatchlistStore(tmp_path / "w.json")
    store.save(
        [WatchItem(symbol="RELIANCE", exchange="NSE"), WatchItem(symbol="ZZZZ", exchange="NSE")]
    )
    settings = SimpleNamespace(
        live_feed_provider="bse_web", crypto_stream_enabled=False, market_feed_enabled=True,
        market_feed_interval_secs=15.0, market_feed_emit_interval_secs=1.0, bse_web_poll_secs=2.0,
    )  # fmt: skip
    bus = EventBus()
    return FeedManager(settings, bus, store, MarketFeedPoller(_Collector(), bus))


async def test_manager_maps_symbols_to_scrip_codes_and_flags_unknowns(
    tmp_path, monkeypatch
) -> None:
    m = _manager(tmp_path, monkeypatch, {"RELIANCE": "500325"})
    await m._start_bse()
    await m.apply_watchlist()
    try:
        assert m.stream.covers("RELIANCE", "NSE") and not m.stream.covers("ZZZZ", "NSE")
        assert m.unresolved_symbols() == ["ZZZZ:NSE"]
        m.stream.connected = True
        st = m.status()
        assert st["mode"] == "stream" and st["source"] == "BSE website (live, ~2s)"
        assert st["stream"]["unofficial"] is True
    finally:
        await m.stop()


async def test_manager_reports_when_the_scrip_list_cannot_load(tmp_path, monkeypatch) -> None:
    m = _manager(tmp_path, monkeypatch, scrips=None)
    await m._start_bse()
    assert m.stream is None and "scrip list" in m.status()["setup_hint"]
    assert m.status()["mode"] == "polling"  # falls back to the delayed feed
