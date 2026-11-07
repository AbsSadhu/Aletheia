import pytest
from unittest.mock import AsyncMock, MagicMock
from aletheia.extensions.agents.fundamental_agent import FundamentalAgent
from aletheia.core.models import FundamentalOutput


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pe", "sector_pe", "verdict"),
    [(15.4, 22.1, "UNDERVALUED"), (22.0, 22.0, "FAIR"), (40.0, 22.0, "OVERVALUED")],
)
async def test_valuation_verdict_and_commentary_come_from_the_numbers(pe, sector_pe, verdict):
    agent = FundamentalAgent()
    # Mock _fetch_fundamentals directly to avoid Yahoo Finance/NSE fetches in unit tests
    agent._fetch_fundamentals = AsyncMock(
        return_value={"pe_ratio": pe, "sector_pe": sector_pe, "promoter_holding_pct": 54.5}
    )

    res = await agent.analyze("RELIANCE")

    assert isinstance(res, FundamentalOutput)
    assert res.symbol == "RELIANCE"
    assert res.valuation_verdict == verdict
    assert res.valuation_commentary == f"P/E {pe:.1f}x vs sector {sector_pe:.1f}x \u2192 {verdict}"
    assert res.pe_ratio == pe
    assert res.promoter_holding_pct == 54.5
    assert res.confidence == 0.75


@pytest.mark.asyncio
async def test_missing_pe_gives_a_fair_verdict_with_low_confidence():
    agent = FundamentalAgent()
    agent._fetch_fundamentals = AsyncMock(return_value={"promoter_holding_pct": 40.0})

    res = await agent.analyze("RELIANCE")

    assert res.valuation_verdict == "FAIR"
    assert res.valuation_commentary == "Valuation data incomplete."
    assert res.confidence == 0.4


def test_yfinance_fundamentals_treats_genuine_zero_as_real_data(monkeypatch):
    """Regression guard: `if info.get(field):` treated a real 0 (debt-free
    company, zero insider holding, flat growth) as "missing" and silently
    dropped it. Must use `is not None` so a genuine 0 is kept."""
    agent = FundamentalAgent()

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
    agent = FundamentalAgent()

    fake_ticker = MagicMock()
    fake_ticker.info = {}  # nothing reported by yfinance for this symbol

    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_yf)

    result = agent._yfinance_fundamentals("UNKNOWNTICKER")

    assert "pe_ratio" not in result
    assert "promoter_holding_pct" not in result
