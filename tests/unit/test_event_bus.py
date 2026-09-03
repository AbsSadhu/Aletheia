"""
Unit tests for the Aletheia EventBus.
"""

from __future__ import annotations

import pytest

from aletheia.core.events.bus import EventBus, Event, Topics, reset_event_bus, get_event_bus


@pytest.fixture(autouse=True)
def reset_bus():
    """Ensure a fresh singleton for each test."""
    reset_event_bus()
    yield
    reset_event_bus()


class TestEventBusBasics:
    @pytest.mark.asyncio
    async def test_emit_reaches_subscriber(self):
        received: list[Event] = []

        async def handler(event: Event):
            received.append(event)

        bus = EventBus()
        bus.subscribe("test.topic", handler)
        await bus.emit("test.topic", payload={"x": 1})

        assert len(received) == 1
        assert received[0].topic == "test.topic"
        assert received[0].payload == {"x": 1}

    @pytest.mark.asyncio
    async def test_no_subscriber_no_error(self):
        bus = EventBus()
        # Should not raise
        await bus.emit("ghost.topic", payload=42)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_called(self):
        counts: list[int] = [0, 0, 0]

        async def h1(e):
            counts[0] += 1

        async def h2(e):
            counts[1] += 1

        async def h3(e):
            counts[2] += 1

        bus = EventBus()
        bus.subscribe("shared", h1)
        bus.subscribe("shared", h2)
        bus.subscribe("shared", h3)
        await bus.emit("shared")

        assert counts == [1, 1, 1]

    @pytest.mark.asyncio
    async def test_error_in_subscriber_does_not_block_others(self):
        results: list[str] = []

        async def bad(e):
            raise ValueError("intentional failure")

        async def good(e):
            results.append("ok")

        bus = EventBus()
        bus.subscribe("topic", bad)
        bus.subscribe("topic", good)
        await bus.emit("topic")  # Should not raise

        assert results == ["ok"]


class TestWildcardSubscriptions:
    @pytest.mark.asyncio
    async def test_wildcard_matches_prefix(self):
        received: list[str] = []

        async def handler(event: Event):
            received.append(event.topic)

        bus = EventBus()
        bus.subscribe("agent.*", handler)

        await bus.emit("agent.oracle.signal")
        await bus.emit("agent.sentinel.alert")
        await bus.emit("market.quote")  # should NOT match

        assert "agent.oracle.signal" in received
        assert "agent.sentinel.alert" in received
        assert "market.quote" not in received

    @pytest.mark.asyncio
    async def test_exact_and_wildcard_both_trigger(self):
        counts = {"exact": 0, "wild": 0}

        async def exact_h(e):
            counts["exact"] += 1

        async def wild_h(e):
            counts["wild"] += 1

        bus = EventBus()
        bus.subscribe(Topics.ORACLE_SIGNAL, exact_h)
        bus.subscribe("agent.*", wild_h)

        await bus.emit(Topics.ORACLE_SIGNAL)
        assert counts == {"exact": 1, "wild": 1}


class TestUnsubscribe:
    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self):
        calls: list[int] = []

        async def handler(e):
            calls.append(1)

        bus = EventBus()
        bus.subscribe("topic", handler)
        await bus.emit("topic")
        assert calls == [1]

        bus.unsubscribe("topic", handler)
        await bus.emit("topic")
        assert calls == [1]  # Not called again


class TestHistory:
    @pytest.mark.asyncio
    async def test_history_records_events(self):
        bus = EventBus()
        await bus.emit("a.b", payload="first")
        await bus.emit("a.c", payload="second")

        history = bus.get_history()
        topics = [e.topic for e in history]
        assert "a.b" in topics
        assert "a.c" in topics

    @pytest.mark.asyncio
    async def test_history_filter_by_prefix(self):
        bus = EventBus()
        await bus.emit("agent.oracle.signal")
        await bus.emit("market.quote")

        agent_events = bus.get_history(topic="agent")
        market_events = bus.get_history(topic="market")

        assert all(e.topic.startswith("agent") for e in agent_events)
        assert all(e.topic.startswith("market") for e in market_events)


class TestSingleton:
    def test_get_event_bus_returns_same_instance(self):
        b1 = get_event_bus()
        b2 = get_event_bus()
        assert b1 is b2

    def test_reset_clears_singleton(self):
        b1 = get_event_bus()
        reset_event_bus()
        b2 = get_event_bus()
        assert b1 is not b2


class TestStats:
    @pytest.mark.asyncio
    async def test_emit_count_tracked(self):
        bus = EventBus()
        for _ in range(5):
            await bus.emit("counted.topic")
        stats = bus.get_stats()
        assert stats.get("counted.topic", 0) == 5


class TestTopicConstants:
    def test_topic_constants_are_strings(self):
        assert isinstance(Topics.MARKET_QUOTE, str)
        assert isinstance(Topics.ORACLE_SIGNAL, str)
        assert isinstance(Topics.TRADE_PAPER, str)
        assert isinstance(Topics.RUN_COMPLETED, str)
