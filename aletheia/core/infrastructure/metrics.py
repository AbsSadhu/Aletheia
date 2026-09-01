from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class HistogramSnapshot:
    count: int
    minimum: float | None
    maximum: float | None
    average: float | None


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: defaultdict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: defaultdict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, amount: float = 1.0) -> None:
        self._counters[name] += amount

    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        self._histograms[name].append(value)

    def snapshot(self) -> dict[str, object]:
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                name: HistogramSnapshot(
                    count=len(values),
                    minimum=min(values) if values else None,
                    maximum=max(values) if values else None,
                    average=(sum(values) / len(values)) if values else None,
                ).__dict__
                for name, values in self._histograms.items()
            },
        }
