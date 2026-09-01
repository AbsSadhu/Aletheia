from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

HealthCheckFn = Callable[[], bool | dict[str, Any] | Awaitable[bool | dict[str, Any]]]


@dataclass
class HealthCheckResult:
    name: str
    ok: bool
    details: dict[str, Any]
    checked_at: str


class HealthRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, HealthCheckFn] = {}

    def register(self, name: str, check: HealthCheckFn) -> None:
        self._checks[name] = check

    async def run_checks(self) -> list[HealthCheckResult]:
        results: list[HealthCheckResult] = []
        for name, check in self._checks.items():
            value = check()
            if inspect.isawaitable(value):
                value = await value
            ok, details = self._normalize_result(value)
            results.append(
                HealthCheckResult(
                    name=name,
                    ok=ok,
                    details=details,
                    checked_at=datetime.now(UTC).isoformat(),
                )
            )
        return results

    @staticmethod
    def _normalize_result(value: bool | dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        if isinstance(value, bool):
            return value, {}
        return bool(value.get("ok", True)), value
