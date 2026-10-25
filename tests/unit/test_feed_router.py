from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aletheia.core.api.routers import feed
from aletheia.core.events.bus import EventBus
from aletheia.core.marketdata.feed_manager import FeedManager
from aletheia.core.marketdata.live_feed import MarketFeedPoller
from aletheia.core.marketdata.watchlist import DEFAULT_ITEMS, WatchItem, WatchlistStore


class _Collector:
    async def collect_for_holding(self, holding):  # pragma: no cover - not used here
        raise AssertionError


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = WatchlistStore(tmp_path / "watchlist.json")
    settings = SimpleNamespace(
        angel_one_enabled=False, market_feed_enabled=True, market_feed_interval_secs=15.0
    )
    poller = MarketFeedPoller(_Collector(), EventBus(), watchlist_fn=store.items)
    manager = FeedManager(settings, EventBus(), store, poller)
    monkeypatch.setattr(feed, "get_watchlist_store", lambda: store)
    monkeypatch.setattr(feed, "get_feed_manager", lambda: manager)
    app = FastAPI()
    app.include_router(feed.router)
    return TestClient(app), store, manager


def test_default_watchlist_until_the_user_saves_one(client) -> None:
    c, _, _ = client
    items = c.get("/api/v1/watchlist").json()["items"]
    assert [(i["symbol"], i["exchange"]) for i in items] == DEFAULT_ITEMS


def test_save_normalises_dedupes_and_persists(client) -> None:
    c, store, _ = client
    r = c.put(
        "/api/v1/watchlist",
        json={
            "items": [
                {"symbol": " infy ", "exchange": "nse"},
                {"symbol": "INFY", "exchange": "NSE"},
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["items"] == [{"symbol": "INFY", "exchange": "NSE"}]
    assert store.items() == [("INFY", "NSE")]  # survives a reload


@pytest.mark.parametrize(
    "item",
    [
        {"symbol": "BAD SYMBOL!", "exchange": "NSE"},
        {"symbol": "TCS", "exchange": "NYSE"},
        {"symbol": "", "exchange": "NSE"},
    ],
)
def test_invalid_items_are_rejected(client, item) -> None:
    c, store, _ = client
    assert c.put("/api/v1/watchlist", json={"items": [item]}).status_code == 422
    assert store.items() == DEFAULT_ITEMS  # nothing saved


def test_watchlist_size_is_capped(client) -> None:
    c, _, _ = client
    many = [{"symbol": f"S{i}", "exchange": "NSE"} for i in range(101)]
    assert c.put("/api/v1/watchlist", json={"items": many}).status_code == 422


def test_corrupt_watchlist_file_falls_back_to_defaults(tmp_path) -> None:
    p = tmp_path / "w.json"
    p.write_text("{not json")
    assert WatchlistStore(p).items() == DEFAULT_ITEMS


def test_status_reports_polling_and_a_setup_hint_when_not_configured(client) -> None:
    c, _, manager = client
    manager.start_error = "Angel One credentials are not saved yet."
    body = c.get("/api/v1/marketdata/feed-status").json()
    assert body["mode"] == "polling" and "15" in body["source"]
    assert body["stream_configured"] is False
    assert "credentials" in body["setup_hint"]
    assert body["market"]["state"] in {"open", "closed", "pre_open"}


def test_snapshot_merges_poller_and_stream_with_stream_winning(client) -> None:
    c, _, manager = client
    manager.poller.last_quotes[("TCS", "NSE")] = {"symbol": "TCS", "close": 1.0, "stream": False}
    manager.poller.last_quotes[("INFY", "NSE")] = {"symbol": "INFY", "close": 2.0, "stream": False}
    manager.stream = SimpleNamespace(
        last_quotes={("TCS", "NSE"): {"symbol": "TCS", "close": 3.0, "stream": True}},
        status=lambda: {"connected": True},
        connected=True,
    )
    quotes = {q["symbol"]: q for q in c.get("/api/v1/marketdata/snapshot").json()["quotes"]}
    assert quotes["TCS"]["close"] == 3.0 and quotes["INFY"]["close"] == 2.0
    assert c.get("/api/v1/marketdata/feed-status").json()["mode"] == "stream"


async def test_poller_skips_what_the_stream_covers(tmp_path) -> None:
    polled: list[str] = []

    class Collector:
        async def collect_for_holding(self, holding):
            polled.append(holding.symbol)
            return SimpleNamespace(quotes=[])

    poller = MarketFeedPoller(
        Collector(),
        EventBus(),
        watchlist=(("RELIANCE", "NSE"), ("BTC/USDT", "BINANCE")),
        skip=lambda s, e: e == "NSE",
    )
    await poller.poll_once()
    assert polled == ["BTC/USDT"]


def test_watch_item_validation_directly() -> None:
    assert WatchItem(symbol="m&m", exchange="nse").symbol == "M&M"
    with pytest.raises(ValueError):
        WatchItem(symbol="X" * 30)
