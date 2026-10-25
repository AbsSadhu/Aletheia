"""Oracle's signal is the deterministic quant composite. The LLM only comments on it,
and with no trustworthy history the signal is HOLD at zero confidence (never synthetic
data). The loader is injected so nothing here touches yfinance or Ollama."""

import numpy as np
import pandas as pd
import pytest

from aletheia.core.models import AssetType, Holding, MarketQuote, TaxProfile
from aletheia.extensions.agents.oracle import OracleAgent


class _FakeLLM:
    def __init__(self, result: dict | None = None) -> None:
        self._result = result

    async def generate_structured(self, prompt, model=None, format="json"):
        return self._result


def _history(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    close = 2000 * np.cumprod(1 + 0.001 + rng.normal(0, 0.01, n))
    idx = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=n)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1e6},
        index=idx,
    )


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


def _quote(close: float = 2900.0) -> MarketQuote:
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


def _agent(df: pd.DataFrame | None, llm_result: dict | None = None) -> OracleAgent:
    async def loader(symbol: str):
        return df

    agent = OracleAgent(ohlcv_loader=loader)
    agent.llm_client = _FakeLLM(result=llm_result)
    return agent


async def test_no_history_never_fabricates_a_signal() -> None:
    out = await _agent(None).analyze(_holding(), _quote())

    assert out.signal == "HOLD"
    assert out.confidence == 0.0
    assert out.data_quality == "insufficient_history"
    assert out.stop_loss_price is None and out.target_price is None
    assert out.multi_timeframe_signals == []


async def test_signal_comes_from_quant_not_llm() -> None:
    llm = {"signal": "buy", "confidence": 0.99, "rationale": "to the moon"}
    base = await _agent(_history(), llm_result=None).analyze(_holding(), _quote())
    with_llm = await _agent(_history(), llm_result=llm).analyze(_holding(), _quote())

    assert with_llm.signal == base.signal
    assert with_llm.confidence == base.confidence
    assert any("LLM Insights" in r for r in with_llm.rationale)


async def test_llm_dissent_is_surfaced_not_obeyed() -> None:
    base = await _agent(_history()).analyze(_holding(), _quote())
    other = "REDUCE" if base.signal != "REDUCE" else "BUY"
    out = await _agent(
        _history(), llm_result={"signal": other, "confidence": 0.9, "rationale": "x"}
    ).analyze(_holding(), _quote())

    assert out.signal == base.signal
    assert any("LLM Dissent" in r for r in out.rationale)


async def test_malformed_llm_output_does_not_crash_or_change_signal() -> None:
    base = await _agent(_history()).analyze(_holding(), _quote())
    out = await _agent(_history(), llm_result={"signal": "buy"}).analyze(_holding(), _quote())

    assert out.signal == base.signal
    assert any("LLM Fallback" in r for r in out.rationale)


async def test_cost_basis_gap_is_reported_but_does_not_drive_signal() -> None:
    cheap = await _agent(_history()).analyze(_holding(average_price=100.0), _quote())
    dear = await _agent(_history()).analyze(_holding(average_price=9000.0), _quote())

    assert cheap.fair_value_gap_pct == pytest.approx((2900 - 100) / 100 * 100)
    assert (cheap.signal, cheap.confidence) == (dear.signal, dear.confidence)


async def test_debate_can_only_derisk() -> None:
    agent = _agent(_history(), llm_result={"signal": "BUY", "confidence": 0.95, "rationale": "x"})
    from aletheia.core.models import OracleOutput, SentinelOutput

    original = OracleOutput(symbol="X", signal="HOLD", confidence=0.5, stop_loss_price=1.0)
    out = await agent.debate(original, SentinelOutput())

    assert out.signal == "HOLD"
    assert out.confidence <= 0.5
    assert out.stop_loss_price == 1.0
