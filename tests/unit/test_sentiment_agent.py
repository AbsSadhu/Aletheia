import pytest
from unittest.mock import AsyncMock
from aletheia.extensions.agents.sentiment_agent import SentimentAgent
from aletheia.core.models import SentimentOutput


def _agent(headlines, sources):
    agent = SentimentAgent()
    # Mock fetch_headlines to avoid hitting public APIs in unit tests
    agent._fetch_headlines = AsyncMock(return_value=(headlines, sources))
    return agent


@pytest.mark.asyncio
async def test_positive_headlines_score_positive():
    agent = _agent(
        ["Reliance profits hit all time high", "Expansion of retail stores"],
        {"NSE announcements": 1, "MoneyControl": 1},
    )

    res = await agent.analyze("RELIANCE")

    assert isinstance(res, SentimentOutput)
    assert res.symbol == "RELIANCE"
    assert res.sentiment_score > 0.0
    assert res.verdict in ("POSITIVE", "STRONGLY_POSITIVE")
    assert res.confidence == 0.5  # keyword scoring is a rough read
    assert res.headline_count == 2
    assert "Reliance profits" in res.top_headlines[0]
    assert res.source_breakdown == {"NSE announcements": 1, "MoneyControl": 1}


@pytest.mark.asyncio
async def test_negative_headlines_score_negative():
    agent = _agent(["Reliance loss and decline in growth", "weak earnings"], {"MoneyControl": 2})

    res = await agent.analyze("RELIANCE")

    assert res.sentiment_score < 0.0  # bearish keywords dominated
    assert res.verdict == "STRONGLY_NEGATIVE"
    assert res.confidence == 0.5


@pytest.mark.asyncio
async def test_no_headlines_is_neutral_and_low_confidence():
    res = await _agent([], {}).analyze("RELIANCE")

    assert res.verdict == "NEUTRAL"
    assert res.sentiment_score == 0.0
    assert res.headline_count == 0
    assert res.confidence == 0.2
