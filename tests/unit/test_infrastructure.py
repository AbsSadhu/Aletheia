from __future__ import annotations

import asyncio
from pathlib import Path

from aletheia.core.infrastructure.cache import TTLCache
from aletheia.core.infrastructure.container import ServiceContainer
from aletheia.core.infrastructure.health import HealthRegistry
from aletheia.core.infrastructure.metrics import MetricsRegistry
from aletheia.core.infrastructure.plugins import PluginManager
from aletheia.core.infrastructure.scheduler import TaskScheduler


def test_ttl_cache_eviction_and_expiry() -> None:
    cache = TTLCache[str, int](max_size=2, default_ttl_secs=0.01)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    asyncio.run(asyncio.sleep(0.02))
    assert cache.get("b") is None


def test_service_container_singleton_and_factory() -> None:
    container = ServiceContainer()
    container.register_singleton("answer", 42)
    counter = {"value": 0}

    def build() -> int:
        counter["value"] += 1
        return counter["value"]

    container.register_factory("factory", build, singleton=False)
    assert container.resolve("answer") == 42
    assert container.resolve("factory") == 1
    assert container.resolve("factory") == 2


def test_metrics_registry_snapshot() -> None:
    registry = MetricsRegistry()
    registry.increment("runs")
    registry.set_gauge("workers", 2)
    registry.observe("latency_ms", 10)
    registry.observe("latency_ms", 30)
    snapshot = registry.snapshot()
    assert snapshot["counters"]["runs"] == 1.0
    assert snapshot["gauges"]["workers"] == 2
    assert snapshot["histograms"]["latency_ms"]["average"] == 20


def test_plugin_manager_loads_plugin(tmp_path: Path) -> None:
    plugin_file = tmp_path / "sample_plugin.py"
    plugin_file.write_text(
        "\n".join(
            [
                "class SamplePlugin:",
                "    name = 'sample'",
                "    def register(self):",
                "        self.loaded = True",
                "",
                "PLUGIN_CLASS = SamplePlugin",
            ]
        ),
        encoding="utf-8",
    )
    manager = PluginManager(plugin_dirs=[tmp_path])
    loaded = manager.load_all()
    assert "sample" in loaded


def test_health_registry_supports_async_checks() -> None:
    registry = HealthRegistry()

    async def async_check() -> dict[str, object]:
        return {"ok": True, "source": "async"}

    registry.register("async", async_check)
    results = asyncio.run(registry.run_checks())
    assert results[0].ok is True
    assert results[0].details["source"] == "async"


def test_scheduler_runs_task() -> None:
    calls: list[str] = []

    async def job() -> None:
        calls.append("x")

    async def scenario() -> None:
        scheduler = TaskScheduler()
        await scheduler.start()
        scheduler.schedule_once("job", job)
        await asyncio.sleep(0.05)
        await scheduler.stop()

    asyncio.run(scenario())
    assert calls == ["x"]
