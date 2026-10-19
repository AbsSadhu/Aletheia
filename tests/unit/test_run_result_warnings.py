"""RunResult must flag runs priced from sample data instead of live quotes."""

from __future__ import annotations

from aletheia.core.models import CollectorOutput, RunResult, RunSummary


def _collector(symbol: str, provider: str) -> CollectorOutput:
    return CollectorOutput(symbol=symbol, provider_used=provider, quotes=[])


def test_static_seed_and_unavailable_symbols_are_flagged() -> None:
    result = RunResult(
        summary=RunSummary(prompt="p"),
        collector_output=[
            _collector("RELIANCE", "static_seed"),
            _collector("TCS", "static_seed"),
            _collector("ITC", "yfinance"),
            _collector("XYZ", "unavailable"),
        ],
    )

    assert len(result.warnings) == 2
    assert "RELIANCE, TCS" in result.warnings[0]
    assert "ITC" not in result.warnings[0]
    assert "XYZ" in result.warnings[1]


def test_live_data_produces_no_warning() -> None:
    result = RunResult(
        summary=RunSummary(prompt="p"),
        collector_output=[_collector("ITC", "yfinance")],
    )
    assert result.warnings == []


def test_warnings_do_not_duplicate_on_roundtrip() -> None:
    result = RunResult(
        summary=RunSummary(prompt="p"),
        collector_output=[_collector("RELIANCE", "static_seed")],
    )
    reloaded = RunResult.model_validate(result.model_dump())
    assert reloaded.warnings == result.warnings
    assert len(reloaded.warnings) == 1
