import pytest
from unittest.mock import AsyncMock, MagicMock
from aletheia.extensions.agents.critic_agent import CriticAgent
from aletheia.core.models import ScribeOutput, CriticVerdict, Recommendation


@pytest.mark.asyncio
async def test_critic_agent_llm_pass():
    llm = MagicMock()
    llm.generate_structured = AsyncMock(
        return_value={
            "passed": True,
            "score": 0.9,
            "notes": ["All criteria met, tax drag addressed."],
        }
    )

    agent = CriticAgent(llm_client=llm)
    scribe_out = ScribeOutput(
        executive_summary="We recommend buying RELIANCE. Stop loss at 2400. Tax implications are minimal.",
        overall_confidence=0.8,
        agreement_level="CONSENSUS",
        recommendations=[
            Recommendation(
                symbol="RELIANCE",
                action="BUY",
                confidence=0.8,
                explanation="Bullish trend",
                stop_loss=2400.0,
            )
        ],
        notes=[],
    )

    res = await agent.audit(scribe_out, sentinel_output={}, sage_outputs=[], iteration=1)

    assert isinstance(res, CriticVerdict)
    assert res.passed is True
    assert res.score == 0.9
    assert "All criteria met" in res.notes[0]


@pytest.mark.asyncio
async def test_critic_agent_llm_fail():
    llm = MagicMock()
    llm.generate_structured = AsyncMock(
        return_value={"passed": False, "score": 0.5, "notes": ["Fails to mention VaR risk."]}
    )

    agent = CriticAgent(llm_client=llm)
    scribe_out = ScribeOutput(
        executive_summary="Buy Reliance.",
        overall_confidence=0.9,
        agreement_level="CONSENSUS",
        recommendations=[
            Recommendation(
                symbol="RELIANCE", action="BUY", confidence=0.9, explanation="Strong trend"
            )
        ],
        notes=[],
    )

    res = await agent.audit(
        scribe_out, sentinel_output={"portfolio_var_95": 0.12}, sage_outputs=[], iteration=1
    )

    assert isinstance(res, CriticVerdict)
    assert res.passed is False
    assert res.score == 0.5
    assert res.iteration == 1


@pytest.mark.asyncio
async def test_critic_agent_rule_based():
    # Pass an LLM client that raises an exception to trigger the rule-based fallback
    llm = MagicMock()
    llm.generate_structured = AsyncMock(side_effect=Exception("LLM offline"))

    agent = CriticAgent(llm_client=llm)
    scribe_out = ScribeOutput(
        executive_summary="Buy Reliance.",  # too brief
        overall_confidence=0.9,
        agreement_level="CONSENSUS",
        recommendations=[],  # missing
        notes=[],
    )

    sentinel_out = {"portfolio_var_95": 0.12, "alerts": ["High risk position"]}

    res = await agent.audit(scribe_out, sentinel_output=sentinel_out, sage_outputs=[], iteration=1)

    assert isinstance(res, CriticVerdict)
    assert res.passed is False
    assert len(res.notes) >= 3
