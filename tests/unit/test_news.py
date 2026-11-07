"""News: sentiment lexicon, RSS parsing, symbol tagging, mood, tracker, and movers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from aletheia.core.news.feeds import RawItem, parse_rss
from aletheia.core.news.sentiment import label_for, score_headline
from aletheia.core.news.service import NewsService
from aletheia.core.news.store import NewsAlertStore

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Sensex surges 900 points as banks rally - Mint Desk</title>
<link>https://example.com/a</link><pubDate>Mon, 26 Oct 2026 09:30:00 +0000</pubDate></item>
<item><title>   </title><link>https://example.com/blank</link></item>
<item><title>Infosys misses estimates, shares tumble</title>
<link>https://example.com/b</link><pubDate>Mon, 26 Oct 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""


def _item(title: str, hours_ago: float = 1.0, source: str = "Test") -> RawItem:
    return RawItem(
        title=title,
        link="https://example.com/x",
        source=source,
        published=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


def _service(items: list[RawItem]) -> NewsService:
    async def fetch():
        return items, {"Test": True}

    return NewsService(fetch=fetch, ttl_seconds=0)


def test_score_direction_and_label():
    assert score_headline("Sensex surges as banks rally to record high") > 0.5
    assert score_headline("Markets crash as selloff deepens") < -0.5
    assert label_for(score_headline("Board meeting scheduled for Thursday")) == "neutral"


def test_negation_flips_a_positive_word():
    assert score_headline("Company fails to gain from rally") < score_headline(
        "Company set to gain from rally"
    )


def test_parse_rss_skips_blank_titles_and_splits_google_news_publisher():
    items = parse_rss(RSS, "Google News")
    assert [i.title for i in items] == [
        "Sensex surges 900 points as banks rally",
        "Infosys misses estimates, shares tumble",
    ]
    assert items[0].source == "Mint Desk"
    assert items[0].published.tzinfo is not None


def test_parse_rss_returns_nothing_for_garbage():
    assert parse_rss(b"not xml at all", "X") == []


def test_tagging_uses_aliases_and_word_boundaries():
    svc = _service([])
    assert "INFY" in svc.tag("Infosys wins large deal")
    assert "SBIN" in svc.tag("SBI raises lending rates")
    assert "SBIN" not in svc.tag("Subsidiary basis points")  # no partial-word matches
    assert "BTC" in svc.tag("Bitcoin slips below support", ["BTC/USDT"])


def test_refresh_dedupes_scores_and_tags():
    svc = _service(
        [
            _item("Infosys wins big deal, shares jump"),
            _item("infosys wins big deal shares jump!"),
            _item("Nifty slumps on global selloff"),
        ]
    )
    asyncio.run(svc.refresh())
    heads = svc.headlines()
    assert len(heads) == 2
    by_title = {h["title"].lower(): h for h in heads}
    infy = next(h for t, h in by_title.items() if "infosys" in t)
    assert infy["label"] == "bullish" and "INFY" in infy["symbols"]
    assert svc.mood()["counts"]["bearish"] == 1


def test_old_items_are_pruned():
    svc = _service([_item("Nifty gains", hours_ago=2), _item("Sensex falls", hours_ago=60)])
    asyncio.run(svc.refresh())
    assert len(svc.headlines()) == 1


def test_mood_weights_recent_headlines_more():
    svc = _service(
        [
            _item("Markets surge on strong growth", hours_ago=0.2),
            _item("Markets crash on selloff", hours_ago=5.5),
        ]
    )
    asyncio.run(svc.refresh())
    assert svc.mood()["value"] > 0


def test_tracker_includes_watched_symbols_without_news():
    svc = _service([_item("Infosys wins big deal, shares jump")])
    asyncio.run(svc.refresh())
    rows = {r["symbol"]: r for r in svc.tracker(["INFY", "WIPRO"])}
    assert rows["INFY"]["mentions"] == 1 and rows["INFY"]["label"] == "bullish"
    assert rows["WIPRO"]["mentions"] == 0 and rows["WIPRO"]["watched"] is True


def test_movers_pair_a_move_with_headlines_and_prefer_aligned_ones():
    svc = _service(
        [
            _item("Infosys shares tumble on weak guidance", hours_ago=3),
            _item("Infosys wins large deal, stock jumps", hours_ago=1),
        ]
    )
    asyncio.run(svc.refresh())
    quotes = [
        {"symbol": "INFY", "exchange": "NSE", "close": 1500.0, "change_pct": 2.4},
        {"symbol": "TCS", "exchange": "NSE", "close": 3500.0, "change_pct": -0.5},
        {"symbol": "ITC", "exchange": "NSE", "close": 400.0, "change_pct": None},
    ]
    movers = svc.movers(quotes)
    assert [m["symbol"] for m in movers] == ["INFY", "TCS"]  # no quote change, no mover
    infy = movers[0]
    assert infy["direction"] == "up" and infy["drivers"][0]["aligned"] is True
    assert "jumps" in infy["reason"]
    assert movers[1]["reason"] is None  # honest about having nothing to say
    assert "not proof" in infy["note"]


def test_general_news_feed_is_filtered_to_market_stories():
    svc = _service(
        [
            _item("Pujara picks his ODI World XI, Brook miss out", source="NDTV Profit"),
            _item("Udta Teer box office collection crosses Rs 25 crore", source="NDTV Profit"),
            _item("Sensex jumps 483 points as banks rally", source="NDTV Profit"),
            _item("Infosys wins large deal", source="NDTV Profit"),
            _item(
                "Pujara picks his ODI World XI, Brook miss out", source="Mint"
            ),  # a markets feed is trusted
        ]
    )
    asyncio.run(svc.refresh())
    titles = {h["title"] for h in svc.headlines()}
    assert "Sensex jumps 483 points as banks rally" in titles
    assert "Infosys wins large deal" in titles
    assert not any("box office" in t for t in titles)
    assert sum("Pujara" in t for t in titles) == 1  # kept only from the markets feed


def _flip_service(batches: list[list[RawItem]]) -> NewsService:
    calls = iter(batches)

    async def fetch():
        return next(calls), {"Test": True}

    return NewsService(fetch=fetch, ttl_seconds=0)


BULL = ["Infosys wins large deal, stock jumps", "Infosys profit growth strong, shares rally"]
BEAR = [
    "Infosys shares tumble on weak guidance",
    "Infosys cuts outlook, stock plunges",
    "Infosys faces probe, shares slump",
    "Infosys loses key client, shares sink",
]


def test_first_reading_sets_a_baseline_without_alerting():
    svc = _flip_service([[_item(t, hours_ago=2) for t in BULL]])
    asyncio.run(svc.refresh(["INFY"]))
    assert svc.alerts() == []
    assert svc._states["INFY"] == "bullish"


def test_flip_from_bullish_to_bearish_raises_one_alert_with_evidence():
    svc = _flip_service(
        [
            [_item(t, hours_ago=5) for t in BULL],
            [_item(t, hours_ago=5) for t in BULL] + [_item(t, hours_ago=0.1) for t in BEAR],
        ]
    )
    asyncio.run(svc.refresh(["INFY"]))
    asyncio.run(svc.refresh(["INFY"]))
    alerts = svc.alerts()
    assert len(alerts) == 1
    a = alerts[0]
    assert (a["symbol"], a["from"], a["to"]) == ("INFY", "bullish", "bearish")
    assert a["score"] < -0.2 and a["headline"]["label"] == "bearish"


def test_no_alert_when_the_tone_holds_or_the_symbol_is_not_watched():
    held = [[_item(t, hours_ago=2) for t in BULL], [_item(t, hours_ago=2) for t in BULL]]
    svc = _flip_service(held)
    asyncio.run(svc.refresh(["INFY"]))
    asyncio.run(svc.refresh(["INFY"]))
    assert svc.alerts() == []
    other = _flip_service(
        [
            [_item(t, hours_ago=5) for t in BULL],
            [_item(t, hours_ago=5) for t in BULL] + [_item(t, hours_ago=0.1) for t in BEAR],
        ]
    )
    asyncio.run(other.refresh(["TCS"]))
    asyncio.run(other.refresh(["TCS"]))
    assert other.alerts() == []


def test_a_single_headline_is_not_enough_to_flip():
    svc = _flip_service(
        [
            [_item(t, hours_ago=5) for t in BULL],
            [_item(t, hours_ago=5) for t in BULL] + [_item(BEAR[0], hours_ago=0.1)],
        ]
    )
    asyncio.run(svc.refresh(["INFY"]))
    asyncio.run(svc.refresh(["INFY"]))
    assert (
        svc.alerts() == []
    )  # one bearish headline against two bullish ones does not cross the line


def test_symbol_view_collects_headlines_tone_and_alerts():
    svc = _flip_service(
        [
            [_item(t, hours_ago=5) for t in BULL],
            [_item(t, hours_ago=5) for t in BULL] + [_item(t, hours_ago=0.1) for t in BEAR],
        ]
    )
    asyncio.run(svc.refresh(["INFY"]))
    asyncio.run(svc.refresh(["INFY"]))
    view = svc.symbol_view("INFY.NS")  # exchange suffixes are ignored
    assert view["symbol"] == "INFY"
    assert (
        view["tone"]["mentions"] == 6
        and view["tone"]["bearish"] == 4
        and view["tone"]["label"] == "bearish"
    )
    assert view["state"] == "bearish" and len(view["alerts"]) == 1
    assert view["headlines"][0]["published"] >= view["headlines"][-1]["published"]
    assert svc.symbol_view("TCS")["tone"]["mentions"] == 0


def _persisted_service(db, batches):
    calls = iter(batches)

    async def fetch():
        return next(calls), {"Test": True}

    return NewsService(fetch=fetch, ttl_seconds=0, store=NewsAlertStore(db))


def test_alert_history_survives_a_restart(tmp_path):
    db = tmp_path / "news_alerts.db"
    first = _persisted_service(
        db,
        [
            [_item(t, hours_ago=5) for t in BULL],
            [_item(t, hours_ago=5) for t in BULL] + [_item(t, hours_ago=0.1) for t in BEAR],
        ],
    )
    asyncio.run(first.refresh(["INFY"]))
    asyncio.run(first.refresh(["INFY"]))
    assert len(first.alerts()) == 1

    reopened = _persisted_service(db, [[]])
    assert [a["id"] for a in reopened.alerts()] == [a["id"] for a in first.alerts()]
    assert reopened.alerts()[0]["headline"]["label"] == "bearish"


def test_a_flip_while_the_app_was_closed_alerts_instead_of_resetting_the_baseline(tmp_path):
    db = tmp_path / "news_alerts.db"
    before = _persisted_service(db, [[_item(t, hours_ago=2) for t in BULL]])
    asyncio.run(before.refresh(["INFY"]))
    assert before.alerts() == []  # first reading: baseline only

    after = _persisted_service(db, [[_item(t, hours_ago=0.1) for t in BEAR]])
    asyncio.run(after.refresh(["INFY"]))
    flips = after.alerts()
    assert len(flips) == 1 and (flips[0]["from"], flips[0]["to"]) == ("bullish", "bearish")


def test_store_keeps_only_the_newest_alerts_in_memory_but_all_on_disk(tmp_path):
    store = NewsAlertStore(tmp_path / "a.db")
    for i in range(5):
        store.add_alert({"id": f"id{i}", "t": f"2026-01-0{i + 1}T00:00:00", "symbol": "INFY"})
    assert [a["id"] for a in store.recent_alerts(2)] == ["id4", "id3"]
