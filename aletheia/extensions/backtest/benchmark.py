"""
Benchmark harness for running historical test scenarios and comparing results.

Usage:
    aletheia benchmark run --scenario nse_starter_2024 --label before_memory_v1
    aletheia benchmark run --scenario nse_starter_2024 --label after_memory_v1
    aletheia benchmark compare before_memory_v1 after_memory_v1
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel

_BENCHMARK_DIR = Path.home() / ".aletheia" / "benchmarks"


class ScenarioConfig(BaseModel):
    name: str
    symbols: list[str]
    start_date: str
    end_date: str
    initial_capital: float = 100_000.0
    description: str = ""


class BenchmarkResult(BaseModel):
    label: str
    scenario: str
    run_id: str | None = None
    timestamp: str
    metrics: dict
    recommendations: list[dict] = []
    runtime_seconds: float = 0.0


# Built-in test scenarios
BUILTIN_SCENARIOS: dict[str, ScenarioConfig] = {
    "nse_starter_2024": ScenarioConfig(
        name="nse_starter_2024",
        symbols=["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"],
        start_date=(date.today() - timedelta(days=365)).isoformat(),
        end_date=date.today().isoformat(),
        description="NSE blue-chip portfolio — 12-month backtest",
    ),
    "crypto_btc_eth_2024": ScenarioConfig(
        name="crypto_btc_eth_2024",
        symbols=["BTC-USD", "ETH-USD"],
        start_date=(date.today() - timedelta(days=180)).isoformat(),
        end_date=date.today().isoformat(),
        description="BTC/ETH 6-month crypto backtest",
    ),
    "nse_midcap_2024": ScenarioConfig(
        name="nse_midcap_2024",
        symbols=["TATAMOTORS.NS", "BAJFINANCE.NS", "AXISBANK.NS"],
        start_date=(date.today() - timedelta(days=365)).isoformat(),
        end_date=date.today().isoformat(),
        description="NSE mid-cap basket — 12-month backtest",
    ),
}


class BenchmarkHarness:
    def __init__(self) -> None:
        _BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

    def get_scenario(self, name: str) -> ScenarioConfig:
        if name in BUILTIN_SCENARIOS:
            return BUILTIN_SCENARIOS[name]
        custom_path = _BENCHMARK_DIR / f"{name}.json"
        if custom_path.exists():
            return ScenarioConfig.model_validate_json(custom_path.read_text())
        raise ValueError(f"Scenario '{name}' not found. Use one of: {list(BUILTIN_SCENARIOS)}")

    def save_scenario(self, scenario: ScenarioConfig) -> None:
        path = _BENCHMARK_DIR / f"{scenario.name}.json"
        path.write_text(scenario.model_dump_json(indent=2))

    async def run_scenario(
        self,
        scenario: ScenarioConfig,
        label: str,
    ) -> BenchmarkResult:
        """Run a backtest scenario and record the result."""
        from aletheia.extensions.backtest.runner import BacktestRunner
        from aletheia.extensions.backtest.data_feed import HistoricalDataFeed
        from aletheia.core.config.settings import get_settings
        import asyncio

        settings = get_settings()
        feed = HistoricalDataFeed(duckdb_path=settings.duckdb_path)
        runner = BacktestRunner(initial_capital=scenario.initial_capital)

        start_time = time.time()
        # Fetch data
        await asyncio.gather(
            *[
                feed.fetch_and_store(sym, scenario.start_date, scenario.end_date)
                for sym in scenario.symbols
            ]
        )

        # Build candle map
        all_candles: dict[str, list] = {}
        for sym in scenario.symbols:
            candles = feed.get_candles(sym, scenario.start_date, scenario.end_date)
            all_candles[sym] = candles

        # Drive event loop
        date_set: set[str] = set()
        for candles in all_candles.values():
            for c in candles:
                date_set.add(c.date)

        for trading_date in sorted(date_set):
            day_data: dict[str, dict] = {}
            for sym, candles in all_candles.items():
                candle = next((c for c in candles if c.date == trading_date), None)
                if candle:
                    day_data[sym] = {
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                    }
            runner.execute_orders(day_data)
            runner.update_equity(day_data)

        report = runner.generate_report(
            strategy_name="benchmark_run",
            start_date=scenario.start_date,
            end_date=scenario.end_date,
        )
        runtime = time.time() - start_time

        result = BenchmarkResult(
            label=label,
            scenario=scenario.name,
            timestamp=date.today().isoformat(),
            metrics=report.model_dump() if hasattr(report, "model_dump") else {},
            runtime_seconds=round(runtime, 2),
        )
        self._save_result(result)
        return result

    def _result_path(self, label: str) -> Path:
        return _BENCHMARK_DIR / f"result_{label}.json"

    def _save_result(self, result: BenchmarkResult) -> None:
        self._result_path(result.label).write_text(result.model_dump_json(indent=2))

    def load_result(self, label: str) -> BenchmarkResult | None:
        path = self._result_path(label)
        if not path.exists():
            return None
        return BenchmarkResult.model_validate_json(path.read_text())

    def compare(self, label_a: str, label_b: str) -> dict:
        a = self.load_result(label_a)
        b = self.load_result(label_b)
        if a is None or b is None:
            missing = label_a if a is None else label_b
            raise FileNotFoundError(f"Benchmark result '{missing}' not found.")

        comparison: dict = {
            "label_a": label_a,
            "label_b": label_b,
            "scenario": a.scenario,
            "diffs": {},
        }
        all_keys = set(a.metrics) | set(b.metrics)
        for key in all_keys:
            va = a.metrics.get(key)
            vb = b.metrics.get(key)
            try:
                delta = float(vb) - float(va) if va is not None and vb is not None else None
            except (TypeError, ValueError):
                delta = None
            comparison["diffs"][key] = {"a": va, "b": vb, "delta": delta}
        return comparison

    def list_results(self) -> list[str]:
        return [p.stem.replace("result_", "") for p in _BENCHMARK_DIR.glob("result_*.json")]
