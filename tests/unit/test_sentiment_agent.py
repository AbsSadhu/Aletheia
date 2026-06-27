import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from aletheia.extensions.agents.sentiment_agent import SentimentAgent
from aletheia.core.models import SentimentOutput

@pytest.mark.asyncio
async def test_sentiment_agent_basic():
    # Mock LLM client
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=json.dumps({
        "sentiment_score": 0.8,
        "verdict": "BULLISH",
    }))

    agent = SentimentAgent(llm_client=llm)

    # Mock fetch_headlines to avoid hitting public APIs in unit tests
    agent._fetch_headlines = AsyncMock(return_value=(
        ["Reliance profits hit all time high", "Expansion of retail stores"],
        {"NSE announcements": 1, "MoneyControl": 1}
    ))

    res = await agent.analyze("RELIANCE")

    assert isinstance(res, SentimentOutput)
    assert res.symbol == "RELIANCE"
    assert res.sentiment_score == 0.8
    assert res.verdict == "BULLISH"
    assert res.confidence == 0.75
    assert res.headline_count == 2
    assert "Reliance profits" in res.top_headlines[0]

@pytest.mark.asyncio
async def test_sentiment_agent_keyword_fallback():
    # Test keyword fallback when LLM fails
    llm = MagicMock()
    llm.generate = AsyncMock(side_effect=Exception("LLM failure"))

    agent = SentimentAgent(llm_client=llm)
    agent._fetch_headlines = AsyncMock(return_value=(
        ["Reliance loss and decline in growth", "weak earnings"],
        {"MoneyControl": 2}
    ))

    res = await agent.analyze("RELIANCE")

    assert isinstance(res, SentimentOutput)
    assert res.sentiment_score < 0.0  # bearish keywords dominated
    assert res.verdict == "STRONGLY_NEGATIVE"
    assert res.confidence == 0.5  # fallback confidence
