"""ScribeAgent had zero direct test coverage before this file. Its
synthesis logic (recommendation building, Oracle/Sage disagreement
detection, confidence blending) is pure/deterministic aside from the LLM
call, which is faked here to keep these off the network."""

from aletheia.extensions.agents.scribe import ScribeAgent
from aletheia.core.models import (
    OracleOutput,
    SageOutput,
    SageScenario,
    SentinelOutput,
    TaxProfile,
    TaxSummary,
)


class _FakeLLM:
    def __init__(self, result: dict | None = None) -> None:
        self._result = result

    async def generate_structured(self, prompt, model=None, format="json"):
        return self._result


def _agent(llm_result: dict | None = None) -> ScribeAgent:
    agent = ScribeAgent()
    agent.llm_client = _FakeLLM(result=llm_result)
    return agent


def _oracle(symbol: str, signal: str, confidence: float = 0.7) -> OracleOutput:
    return OracleOutput(
        symbol=symbol,
        signal=signal,
        confidence=confidence,
        rationale=[f"{signal} signal for {symbol}."],
        fair_value_gap_pct=5.0,
        momentum_pct=1.0,
        timeframe_agreement="ALL_AGREE",
    )


def _sage(symbol: str, post_tax_return_pct: float) -> SageOutput:
    return SageOutput(
        symbol=symbol,
        scenario=SageScenario(
            scenario_name="base_tax_aware_projection",
            projected_return_pct=post_tax_return_pct + 3,
            projected_post_tax_return_pct=post_tax_return_pct,
            projected_sharpe=1.0,
            tax_summary=TaxSummary(
                tax_profile=TaxProfile.EQUITY,
                pre_tax_profit=1000.0,
                tax_drag_pct=20.0,
                estimated_tax_amount=200.0,
                post_tax_profit=800.0,
            ),
        ),
        confidence=0.6,
        rationale=["projection"],
    )


async def test_synthesize_with_no_sage_or_sentinel_produces_recommendations() -> None:
    agent = _agent(llm_result=None)
    output = await agent.synthesize(
        oracle_outputs=[_oracle("RELIANCE", "BUY")],
        sentinel_output=None,
        sage_outputs=[],
    )

    assert len(output.recommendations) == 1
    assert output.recommendations[0].action == "BUY"
    assert output.agreement_level == "high"


async def test_synthesize_downgrades_buy_when_sage_projects_muted_return() -> None:
    agent = _agent(llm_result=None)
    output = await agent.synthesize(
        oracle_outputs=[_oracle("RELIANCE", "BUY")],
        sentinel_output=None,
        sage_outputs=[_sage("RELIANCE", post_tax_return_pct=1.0)],
    )

    rec = output.recommendations[0]
    assert rec.action == "HOLD"
    assert output.agreement_level == "moderate"
    assert any("tax-aware scenario is muted" in n for n in output.notes)


async def test_synthesize_flags_disagreement_when_sage_favorable_despite_reduce() -> None:
    agent = _agent(llm_result=None)
    output = await agent.synthesize(
        oracle_outputs=[_oracle("RELIANCE", "REDUCE")],
        sentinel_output=None,
        sage_outputs=[_sage("RELIANCE", post_tax_return_pct=8.0)],
    )

    rec = output.recommendations[0]
    assert rec.action == "REDUCE"  # not overridden, just flagged
    assert output.agreement_level == "moderate"
    assert any("backtest scenario remains favorable" in n for n in output.notes)


async def test_synthesize_records_skipped_and_failed_agents_in_notes() -> None:
    agent = _agent(llm_result=None)
    output = await agent.synthesize(
        oracle_outputs=[],
        sentinel_output=None,
        sage_outputs=[],
        agent_statuses={"sage": "skipped", "sentiment": "failed", "oracle": "completed"},
    )

    assert "Agent sage was skipped." in output.notes
    assert "Agent sentiment failed during execution." in output.notes
    assert not any("oracle" in n for n in output.notes)


async def test_synthesize_blends_sentinel_confidence_and_surfaces_alerts() -> None:
    agent = _agent(llm_result=None)
    sentinel = SentinelOutput(
        portfolio_var_95=-100.0,
        concentration_risk=0.5,
        max_single_position_pct=50.0,
        market_regime="bearish",
        confidence=0.4,
        alerts=["Single-position exposure is above 40% of portfolio market value."],
    )

    output = await agent.synthesize(
        oracle_outputs=[_oracle("RELIANCE", "BUY", confidence=0.8)],
        sentinel_output=sentinel,
        sage_outputs=[],
    )

    assert output.overall_confidence == round((0.8 + 0.4) / 2, 2)
    assert "Single-position exposure is above 40% of portfolio market value." in output.notes


async def test_synthesize_uses_llm_executive_summary_when_valid() -> None:
    agent = _agent(
        llm_result={
            "executive_summary": "Real synthesized view.",
            "synthesized_recommendation": "Trim RELIANCE.",
            "market_regime": "neutral",
            "stop_loss_suggested": True,
            "target_allocation_shift": "Reduce equity 5%",
        }
    )
    output = await agent.synthesize(
        oracle_outputs=[_oracle("RELIANCE", "BUY")],
        sentinel_output=None,
        sage_outputs=[],
    )

    assert "[LLM Insights]" in output.executive_summary
    assert "Real synthesized view." in output.executive_summary
    assert "Market Regime: neutral" in output.notes
    assert "System suggests tight stop losses." in output.notes


async def test_synthesize_falls_back_to_default_summary_on_malformed_llm_output() -> None:
    agent = _agent(llm_result={"executive_summary": "incomplete"})  # missing required fields
    output = await agent.synthesize(
        oracle_outputs=[_oracle("RELIANCE", "BUY")],
        sentinel_output=None,
        sage_outputs=[],
    )

    assert "India-first market data" in output.executive_summary
    assert any("LLM Fallback" in n for n in output.notes)
