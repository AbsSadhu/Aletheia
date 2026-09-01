"""
Aletheia Event Bus — async in-process pub/sub for decoupled component communication.

Design:
  - Each topic is a string key (e.g. "market.quote", "agent.oracle.signal")
  - Subscribers register an async callable
  - Publishers emit events; all subscribers are invoked concurrently
  - Error in one subscriber does NOT prevent others from receiving the event
  - Built on asyncio — zero threading overhead

Wildcard subscriptions: prefix match using "*" suffix
  e.g. subscribe("agent.*") receives all events starting with "agent."

Usage:
    bus = get_event_bus()
    bus.subscribe("market.quote", on_quote)
    await bus.emit("market.quote", QuoteEvent(...))
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event envelope
# ---------------------------------------------------------------------------


@dataclass
class Event:
    """Standard event envelope. All events carry a topic, payload, and timestamp."""

    topic: str
    payload: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = ""
    event_id: str = field(default_factory=lambda: _gen_id())


def _gen_id() -> str:
    import uuid

    return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# Subscriber type
# ---------------------------------------------------------------------------

SubscriberFn = Callable[[Event], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------


class EventBus:
    """
    Async in-process pub/sub event bus.

    Thread-safety: NOT thread-safe (designed for async event loop use only).
    For cross-thread use, call asyncio.run_coroutine_threadsafe from other threads.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[SubscriberFn]] = defaultdict(list)
        self._history: list[Event] = []
        self._history_limit: int = 500
        self._stats: dict[str, int] = defaultdict(int)

    def subscribe(self, topic: str, fn: SubscriberFn) -> None:
        """
        Register a subscriber for a topic.
        Supports wildcard suffix: subscribe("agent.*") matches "agent.oracle", "agent.sentinel", etc.
        """
        self._subs[topic].append(fn)
        logger.debug("EventBus: subscribed %s → %s", fn.__name__, topic)

    def unsubscribe(self, topic: str, fn: SubscriberFn) -> None:
        """Remove a subscriber from a topic."""
        listeners = self._subs.get(topic, [])
        self._subs[topic] = [f for f in listeners if f is not fn]

    async def emit(self, topic: str, payload: Any = None, source: str = "") -> None:
        """
        Emit an event to all registered subscribers (exact match + wildcard).
        Each subscriber is called concurrently; exceptions are logged, not raised.
        """
        event = Event(topic=topic, payload=payload, source=source)

        # Track history
        self._history.append(event)
        if len(self._history) > self._history_limit:
            self._history.pop(0)
        self._stats[topic] += 1

        # Gather matching subscribers
        targets: list[SubscriberFn] = []
        for sub_topic, fns in self._subs.items():
            if sub_topic == topic:
                targets.extend(fns)
            elif sub_topic.endswith("*") and topic.startswith(sub_topic[:-1]):
                targets.extend(fns)

        if not targets:
            return

        # Run all subscribers concurrently; absorb exceptions
        results = await asyncio.gather(
            *[fn(event) for fn in targets],
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "EventBus: subscriber %s raised on topic %s: %s",
                    targets[i].__name__,
                    topic,
                    result,
                )

    def emit_sync(self, topic: str, payload: Any = None, source: str = "") -> None:
        """
        Fire-and-forget emit from synchronous code.
        If no running event loop exists, creates one for the emit.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(topic, payload, source))
        except RuntimeError:
            asyncio.run(self.emit(topic, payload, source))

    def get_history(self, topic: str | None = None, limit: int = 50) -> list[Event]:
        """Return recent events, optionally filtered by topic prefix."""
        events = self._history[-limit:]
        if topic:
            events = [e for e in events if e.topic.startswith(topic)]
        return events

    def get_stats(self) -> dict[str, int]:
        """Return emit counts per topic."""
        return dict(self._stats)

    def clear_subscribers(self, topic: str | None = None) -> None:
        """Remove all subscribers for a topic, or all topics if None."""
        if topic:
            self._subs.pop(topic, None)
        else:
            self._subs.clear()


# ---------------------------------------------------------------------------
# Well-known topic constants
# ---------------------------------------------------------------------------


class Topics:
    """Canonical topic names — use these instead of raw strings."""

    # Market data
    MARKET_QUOTE = "market.quote"
    MARKET_OHLCV = "market.ohlcv"
    MARKET_ORDERBOOK = "market.orderbook"

    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # Agent outputs
    ORACLE_SIGNAL = "agent.oracle.signal"
    SENTINEL_ALERT = "agent.sentinel.alert"
    SAGE_PROJECTION = "agent.sage.projection"
    SCRIBE_RECOMMENDATION = "agent.scribe.recommendation"

    # Execution
    TRADE_PAPER = "trade.paper"
    TRADE_SETTLED = "trade.settled"
    PORTFOLIO_UPDATED = "portfolio.updated"

    # System
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    HEALTH_CHECK = "system.health"

    # Config
    CONFIG_CHANGED = "config.changed"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the global EventBus singleton."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    """Reset the global bus — for testing only."""
    global _bus
    _bus = None
