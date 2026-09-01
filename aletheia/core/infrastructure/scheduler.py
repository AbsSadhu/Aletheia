from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

TaskFn = Callable[[], Awaitable[None]]


class TaskScheduler:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    def schedule_interval(self, name: str, func: TaskFn, interval_secs: float) -> None:
        async def runner() -> None:
            while self._started:
                try:
                    await func()
                except Exception as exc:
                    logger.warning("Scheduled task '%s' failed: %s", name, exc)
                await asyncio.sleep(interval_secs)

        self._tasks.append(asyncio.create_task(runner(), name=f"schedule:{name}"))

    def schedule_once(self, name: str, func: TaskFn) -> None:
        async def runner() -> None:
            try:
                await func()
            except Exception as exc:
                logger.warning("Scheduled task '%s' failed: %s", name, exc)

        self._tasks.append(asyncio.create_task(runner(), name=f"schedule:{name}"))
