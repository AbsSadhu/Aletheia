"""SentinelAgent.assess()/debate() had zero direct test coverage before this
file (assess_portfolio_risk() itself is covered by test_risk.py). Fakes for
duckdb_store/compute_client/llm_client keep these off the network and off a
real Ollama instance.
"""

from aletheia.extensions.agents.sentinel import SentinelAgent
from aletheia.core.models import (
    AssetType,
    Holding,
    MarketQuote,
    OracleOutput,
    Portfolio,
    SentinelOutput,
    TaxProfile,
)


class _FakeComputeClient:
    def __init__(self, regime: str = "bull") -> None:
        self._regime = regime

    async def regime_detection(self, returns):
        return {"current_regime": self._regime}


class _FakeLLM:
    def __init__(self, result: dict | None = None) -> None:
        self._result = result

    async def generate_structured(self, prompt, model=None, format="json"):
        return self._result


def _portfolio() -> Portfolio:
    return Portfolio(
        name="Starter",
        holdings=[
            Holding(
                symbol="RELIANCE",
                quantity=5,
                average_price=2500,
                asset_type=AssetType.EQUITY,
                tax_profile=TaxProfile.EQUITY,
            )
        ],
    )


def _quotes() -> dict[str, MarketQuote]:
    quote = MarketQuote(
        symbol="RELIANCE",
        exchange="NSE",
        close=2920.0,
        open=2890.0,
        high=2950.0,
        low=2880.0,
        volume=1000,
        provider="static_seed",
    )
    return {"RELIANCE": quote}


async def test_assess_uses_default_brief_when_no_llm_and_no_regime_detection() -> None:
    agent = SentinelAgent()
    agent.llm_client = _FakeLLM(result=None)

    output = await agent.assess(_portfolio(), _quotes())

    assert isinstance(output, SentinelOutput)
    assert "Portfolio VaR is" in output.natural_language_brief
    assert output.regime_detail == "unknown"


async def test_assess_updates_regime_from_compute_client() -> None:
    agent = SentinelAgent(compute_client=_FakeComputeClient(regime="crash"))
    agent.llm_client = _FakeLLM(result=None)

    output = await agent.assess(_portfolio(), _quotes())

    assert output.regime_detail == "crash"
    assert output.market_regime == "bearish"


async def test_assess_uses_llm_natural_language_brief_when_valid() -> None:
    agent = SentinelAgent()
    agent.llm_client = _FakeLLM(result={"natural_language_brief": "Real LLM risk commentary."})

    output = await agent.assess(_portfolio(), _quotes())

    assert output.natural_language_brief == "Real LLM risk commentary."


async def test_debate_returns_unchanged_when_not_ollama_provider() -> None:
    agent = SentinelAgent()
    agent.settings.default_llm_provider = "openai"
    sentinel_output = SentinelOutput(
        portfolio_var_95=-100.0,
        concentration_risk=0.3,
        max_single_position_pct=30.0,
        market_regime="balanced",
        confidence=0.5,
    )

    result = await agent.debate(sentinel_output, oracle_outputs=[])

    assert result is sentinel_output


async def test_debate_applies_valid_llm_revision() -> None:
    agent = SentinelAgent()
    agent.settings.default_llm_provider = "ollama"
    agent.llm_client = _FakeLLM(result={"confidence": 0.35, "alerts": ["revised alert"]})
    sentinel_output = SentinelOutput(
        portfolio_var_95=-100.0,
        concentration_risk=0.3,
        max_single_position_pct=30.0,
        market_regime="balanced",
        confidence=0.5,
    )
    oracle = OracleOutput(symbol="RELIANCE", signal="BUY", confidence=0.7, rationale=["r"])

    result = await agent.debate(sentinel_output, oracle_outputs=[oracle])

    assert result.confidence == 0.35
    assert result.alerts == ["revised alert"]


async def test_debate_falls_back_to_original_when_llm_result_lacks_confidence() -> None:
    agent = SentinelAgent()
    agent.settings.default_llm_provider = "ollama"
    agent.llm_client = _FakeLLM(result={"something_else": True})
    sentinel_output = SentinelOutput(
        portfolio_var_95=-100.0,
        concentration_risk=0.3,
        max_single_position_pct=30.0,
        market_regime="balanced",
        confidence=0.5,
    )

    result = await agent.debate(sentinel_output, oracle_outputs=[])

    assert result is sentinel_output
