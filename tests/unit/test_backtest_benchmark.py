from __future__ import annotations

from pathlib import Path

import pytest

from aletheia.extensions.backtest import benchmark as benchmark_module
from aletheia.extensions.backtest.benchmark import (
    BUILTIN_SCENARIOS,
    BenchmarkHarness,
    BenchmarkResult,
    ScenarioConfig,
)


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BenchmarkHarness:
    # BenchmarkHarness reads/writes the module-level _BENCHMARK_DIR constant
    # directly rather than an instance attribute — redirect it to a temp dir
    # so tests never touch the real ~/.aletheia/benchmarks.
    monkeypatch.setattr(benchmark_module, "_BENCHMARK_DIR", tmp_path / "benchmarks")
    return BenchmarkHarness()


class TestScenarios:
    def test_builtin_scenario_lookup(self, harness: BenchmarkHarness) -> None:
        scenario = harness.get_scenario("nse_starter_2024")
        assert scenario.name == "nse_starter_2024"
        assert "RELIANCE.NS" in scenario.symbols

    def test_unknown_scenario_raises_with_helpful_message(self, harness: BenchmarkHarness) -> None:
        with pytest.raises(ValueError, match="not found"):
            harness.get_scenario("does_not_exist")

    def test_custom_scenario_round_trip(self, harness: BenchmarkHarness) -> None:
        custom = ScenarioConfig(
            name="my_custom_scenario",
            symbols=["FOO"],
            start_date="2024-01-01",
            end_date="2024-02-01",
        )
        harness.save_scenario(custom)
        loaded = harness.get_scenario("my_custom_scenario")
        assert loaded.symbols == ["FOO"]
        assert loaded.start_date == "2024-01-01"

    def test_all_builtin_scenarios_are_valid_configs(self) -> None:
        for name, scenario in BUILTIN_SCENARIOS.items():
            assert scenario.name == name
            assert len(scenario.symbols) > 0
            assert scenario.initial_capital > 0


class TestResultsAndComparison:
    def _make_result(self, label: str, sharpe: float, max_dd: float) -> BenchmarkResult:
        return BenchmarkResult(
            label=label,
            scenario="nse_starter_2024",
            timestamp="2024-01-01",
            metrics={"sharpe": sharpe, "max_drawdown": max_dd},
        )

    def test_save_and_load_result_round_trip(self, harness: BenchmarkHarness) -> None:
        result = self._make_result("run_a", sharpe=1.2, max_dd=0.1)
        harness._save_result(result)
        loaded = harness.load_result("run_a")
        assert loaded is not None
        assert loaded.metrics["sharpe"] == 1.2

    def test_load_missing_result_returns_none(self, harness: BenchmarkHarness) -> None:
        assert harness.load_result("nonexistent") is None

    def test_compare_computes_deltas(self, harness: BenchmarkHarness) -> None:
        harness._save_result(self._make_result("before", sharpe=1.0, max_dd=0.2))
        harness._save_result(self._make_result("after", sharpe=1.5, max_dd=0.1))

        comparison = harness.compare("before", "after")
        assert comparison["diffs"]["sharpe"]["delta"] == pytest.approx(0.5)
        assert comparison["diffs"]["max_drawdown"]["delta"] == pytest.approx(-0.1)

    def test_compare_missing_result_raises(self, harness: BenchmarkHarness) -> None:
        harness._save_result(self._make_result("only_one", sharpe=1.0, max_dd=0.1))
        with pytest.raises(FileNotFoundError):
            harness.compare("only_one", "missing")

    def test_list_results(self, harness: BenchmarkHarness) -> None:
        harness._save_result(self._make_result("a", sharpe=1.0, max_dd=0.1))
        harness._save_result(self._make_result("b", sharpe=1.0, max_dd=0.1))
        results = harness.list_results()
        assert set(results) == {"a", "b"}
