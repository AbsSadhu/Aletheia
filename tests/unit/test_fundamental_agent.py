import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from aletheia.extensions.agents.fundamental_agent import FundamentalAgent
from aletheia.core.models import FundamentalOutput

@pytest.mark.asyncio
async def test_fundamental_agent_basic():
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=json.dumps({
        "valuation_verdict": "UNDERVALUED",
        "valuation_commentary": "Solid promoter holding, low P/E compared to sector."
    }))

    agent = FundamentalAgent(llm_client=llm)

    # Mock _fetch_fundamentals directly to avoid Yahoo Finance/NSE fetches in unit tests
    agent._fetch_fundamentals = AsyncMock(return_value={
        "pe_ratio": 15.4,
        "sector_pe": 22.1,
        "promoter_holding_pct": 54.5,
        "market_cap": 250000000000.0,
    })

    res = await agent.analyze("RELIANCE")

    assert isinstance(res, FundamentalOutput)
    assert res.symbol == "RELIANCE"
    assert res.valuation_verdict == "UNDERVALUED"
    assert "Solid promoter holding" in res.valuation_commentary
    assert res.pe_ratio == 15.4
    assert res.promoter_holding_pct == 54.5
    assert res.confidence == 0.75
