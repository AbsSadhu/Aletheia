"""OracleAgent had zero direct test coverage before this file — only
exercised indirectly through end-to-end run integration tests. Fakes for
duckdb_store/llm_client keep these hitting neither the network (yfinance)
nor a real Ollama instance, matching >=50 rows so _compute_multi_timeframe
never falls through to its synthetic-random-data tier either.
"""

import pytest

from aletheia.extensions.agents.oracle import OracleAgent
from aletheia.core.models import AssetType, Holding, MarketQuote, TaxProfile


class _FakeConnection:
    def __init__(self, closes: list[float]) -> None:
        self._closes = closes

    def execute(self, query, params=None):
        return self

    def fetchall(self):
        return [(c,) for c in self._closes]

    def close(self) -> None:
        pass


class _FakeDuckDBStore:
    def __init__(self, closes: list[float]) -> None:
        self._closes = closes

    def _connect(self):
        return _FakeConnection(self._closes)


class _FakeLLM:
    def __init__(self, result: dict | None = None) -> None:
        self._result = result

    async def generate_structured(self, prompt, model=None, format="json"):
        return self._result


def _holding(**overrides) -> Holding:
    defaults = dict(
        symbol="RELIANCE",
        quantity=5,
        average_price=2500,
        asset_type=AssetType.EQUITY,
        exchange="NSE",
        tax_profile=TaxProfile.EQUITY,
    )
    defaults.update(overrides)
    return Holding(**defaults)


def _quote(close: float) -> MarketQuote:
    return MarketQuote(
        symbol="RELIANCE",
        exchange="NSE",
        close=close,
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        volume=1000,
        provider="static_seed",
    )


def _agent_with_history(closes: list[float], llm_result: dict | None) -> OracleAgent:
    agent = OracleAgent(duckdb_store=_FakeDuckDBStore(closes))
    agent.llm_client = _FakeLLM(result=llm_result)
    return agent


async def test_analyze_uses_heuristic_fallback_when_llm_returns_none() -> None:
    agent = _agent_with_history([2900.0] * 150, llm_result=None)

    output = await agent.analyze(_holding(average_price=2000), _quote(2900.0))

    assert output.signal in {"BUY", "HOLD", "REDUCE"}
    assert not any("LLM Insights" in r for r in output.rationale)


async def test_analyze_uses_llm_signal_when_valid() -> None:
    agent = _agent_with_history(
        [2900.0] * 150,
        llm_result={"signal": "buy", "confidence": 0.65, "rationale": "strong momentum"},
    )

    output = await agent.analyze(_holding(), _quote(2900.0))

    assert output.signal == "BUY"
    assert any("LLM Insights" in r for r in output.rationale)


async def test_analyze_falls_back_to_heuristic_on_malformed_llm_output() -> None:
    # Missing required "confidence"/"rationale" fields -> OracleLLMOutput
    # validation fails, and analyze() must fall back, not crash the run.
    agent = _agent_with_history([2900.0] * 150, llm_result={"signal": "buy"})

    output = await agent.analyze(_holding(), _quote(2900.0))

    assert any("LLM Fallback" in r for r in output.rationale)
    assert output.signal in {"BUY", "HOLD", "REDUCE"}


async def test_analyze_rejects_invalid_llm_signal_by_defaulting_to_hold() -> None:
    agent = _agent_with_history(
        [2900.0] * 150,
        llm_result={"signal": "STRONG_BUY", "confidence": 0.9, "rationale": "not a real signal value"},
    )

    output = await agent.analyze(_holding(), _quote(2900.0))

    assert output.signal == "HOLD"


async def test_analyze_computes_fair_value_gap_from_average_price() -> None:
    agent = _agent_with_history([2900.0] * 150, llm_result=None)

    output = await agent.analyze(_holding(average_price=2500.0), _quote(2900.0))

    assert output.fair_value_gap_pct == pytest.approx((2900 - 2500) / 2500 * 100, rel=1e-3)


async def test_analyze_high_confidence_gate_caps_buy_without_multi_timeframe_alignment() -> None:
    # Flat closes -> HOLD on every timeframe -> buy_count stays 0, so a
    # high-confidence LLM "buy" must be capped to 0.7 by the gate.
    agent = _agent_with_history(
        [2900.0] * 150,
        llm_result={"signal": "buy", "confidence": 0.95, "rationale": "aggressive"},
    )

    output = await agent.analyze(_holding(), _quote(2900.0))

    assert output.signal == "BUY"
    assert output.confidence == 0.7
    assert any("High Confidence Gate" in r for r in output.rationale)
