"""
Aletheia Event Bus — async pub/sub for typed agent events.

Publishers: every LangGraph node (via run_service)
Subscribers: WebSocket broadcaster, ComplianceLogger, audit logger
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    AGENT_SKIPPED = "agent_skipped"
    DEBATE_INITIATED = "debate_initiated"
    DEBATE_RESOLVED = "debate_resolved"
    CRITIC_LOOP_STARTED = "critic_loop_started"
    CRITIC_ACCEPTED = "critic_accepted"
    CRITIC_REJECTED = "critic_rejected"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    MACRO_CONTEXT_FETCHED = "macro_context_fetched"


@dataclass
class AletheiaEvent:
    event_type: EventType
    run_id: str
    agent: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": str(self.event_type),
            "run_id": self.run_id,
            "agent": self.agent,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


HandlerType = Callable[[AletheiaEvent], Awaitable[None]]


class EventBus:
    """
    Lightweight in-process async event bus.

    Usage:
        bus = EventBus()
        bus.subscribe(my_async_handler)
        await bus.publish(AletheiaEvent(EventType.AGENT_STARTED, run_id="abc", agent="oracle"))
    """

    def __init__(self, queue_size: int = 256) -> None:
        self._queue: asyncio.Queue[AletheiaEvent] = asyncio.Queue(maxsize=queue_size)
        self._handlers: list[HandlerType] = []
        self._dispatcher_task: asyncio.Task | None = None

    def subscribe(self, handler: HandlerType) -> None:
        """Register an async event handler."""
        self._handlers.append(handler)

    def unsubscribe(self, handler: HandlerType) -> None:
        self._handlers = [h for h in self._handlers if h is not handler]

    async def publish(self, event: AletheiaEvent) -> None:
        """
        Non-blocking publish. Drops event and logs warning if queue is full
        (avoids blocking the LangGraph execution path).
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "EventBus queue full — dropping event %s for run %s",
                event.event_type,
                event.run_id,
            )

    async def publish_sync(self, event: AletheiaEvent) -> None:
        """Blocking publish — waits if queue is full."""
        await self._queue.put(event)

    async def start(self) -> None:
        """Start the background dispatcher coroutine."""
        if self._dispatcher_task is None or self._dispatcher_task.done():
            self._dispatcher_task = asyncio.create_task(self._dispatch_loop())
            logger.info("EventBus dispatcher started.")

    async def stop(self) -> None:
        """Gracefully stop the dispatcher."""
        if self._dispatcher_task and not self._dispatcher_task.done():
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
        logger.info("EventBus dispatcher stopped.")

    async def _dispatch_loop(self) -> None:
        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("EventBus dispatcher error: %s", exc)

    async def _dispatch(self, event: AletheiaEvent) -> None:
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.exception(
                    "EventBus handler %s raised: %s", handler.__name__, exc
                )


# Module-level singleton — imported by run_service, routes, etc.
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
