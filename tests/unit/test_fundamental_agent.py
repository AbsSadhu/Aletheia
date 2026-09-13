import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from aletheia.extensions.agents.fundamental_agent import FundamentalAgent
from aletheia.core.models import FundamentalOutput


@pytest.mark.asyncio
async def test_fundamental_agent_basic():
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=json.dumps(
            {
                "valuation_verdict": "UNDERVALUED",
                "valuation_commentary": "Solid promoter holding, low P/E compared to sector.",
            }
        )
    )

    agent = FundamentalAgent(llm_client=llm)

    # Mock _fetch_fundamentals directly to avoid Yahoo Finance/NSE fetches in unit tests
    agent._fetch_fundamentals = AsyncMock(
        return_value={
            "pe_ratio": 15.4,
            "sector_pe": 22.1,
            "promoter_holding_pct": 54.5,
            "market_cap": 250000000000.0,
        }
    )

    res = await agent.analyze("RELIANCE")

    assert isinstance(res, FundamentalOutput)
    assert res.symbol == "RELIANCE"
    assert res.valuation_verdict == "UNDERVALUED"
    assert "Solid promoter holding" in res.valuation_commentary
    assert res.pe_ratio == 15.4
    assert res.promoter_holding_pct == 54.5
    assert res.confidence == 0.75


def test_yfinance_fundamentals_treats_genuine_zero_as_real_data(monkeypatch):
    """Regression guard: `if info.get(field):` treated a real 0 (debt-free
    company, zero insider holding, flat growth) as "missing" and silently
    dropped it. Must use `is not None` so a genuine 0 is kept."""
    agent = FundamentalAgent(llm_client=None)

    fake_info = {
        "trailingPE": 0,
        "debtToEquity": 0,
        "heldPercentInsiders": 0,
        "earningsGrowth": 0,
        "revenueGrowth": 0,
    }
    fake_ticker = MagicMock()
    fake_ticker.info = fake_info

    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_yf)

    result = agent._yfinance_fundamentals("RELIANCE")

    assert result["pe_ratio"] == 0.0
    assert result["debt_to_equity"] == 0.0
    assert result["promoter_holding_pct"] == 0.0
    assert result["eps_growth_pct"] == 0.0
    assert result["revenue_growth_pct"] == 0.0


def test_yfinance_fundamentals_omits_genuinely_missing_fields(monkeypatch):
    agent = FundamentalAgent(llm_client=None)

    fake_ticker = MagicMock()
    fake_ticker.info = {}  # nothing reported by yfinance for this symbol

    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_yf)

    result = agent._yfinance_fundamentals("UNKNOWNTICKER")

    assert "pe_ratio" not in result
    assert "promoter_holding_pct" not in result
