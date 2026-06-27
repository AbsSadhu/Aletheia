import pytest
from unittest.mock import AsyncMock, MagicMock
from aletheia.extensions.agents.options_flow_agent import OptionsFlowAgent
from aletheia.core.models import OptionsFlowOutput


@pytest.mark.asyncio
async def test_options_flow_agent_skip_non_nse():
    agent = OptionsFlowAgent()
    # Non-NSE symbol (e.g. crypto or NYSE) should yield a skipped output
    res = await agent.analyze("BTCUSDT")
    assert isinstance(res, OptionsFlowOutput)
    assert res.symbol == "BTCUSDT"
    assert res.signal_hint == "SKIP"
    assert res.confidence == 0.0


@pytest.mark.asyncio
async def test_options_flow_agent_compute():
    compute = MagicMock()
    compute.options_flow = AsyncMock(
        return_value={
            "put_call_ratio": 0.6,
            "iv_rank": 25.0,
            "oi_concentration": "BULLISH_OI",
            "iv_signal": "NEUTRAL",
        }
    )

    agent = OptionsFlowAgent(compute_client=compute)
    # Mock _fetch_options_chain to return synthetic chain data
    agent._fetch_options_chain = AsyncMock(
        return_value={
            "filtered": {
                "data": [
                    {
                        "strikePrice": 2500,
                        "CE": {"openInterest": 1000, "impliedVolatility": 18},
                        "PE": {"openInterest": 600, "impliedVolatility": 20},
                    }
                ]
            }
        }
    )

    res = await agent.analyze("RELIANCE")

    assert isinstance(res, OptionsFlowOutput)
    assert res.symbol == "RELIANCE"
    assert res.put_call_ratio == 0.6
    assert res.iv_rank == 25.0
    assert res.oi_concentration == "BULLISH_OI"
    assert res.signal_hint == "BULLISH"
    assert res.confidence == 0.7


@pytest.mark.asyncio
async def test_options_flow_agent_python_fallback():
    # If compute client is None, it should use python fallback compute
    agent = OptionsFlowAgent(compute_client=None)
    agent._fetch_options_chain = AsyncMock(
        return_value={
            "records": {
                "data": [
                    {
                        "strikePrice": 2500,
                        "CE": {"openInterest": 1000, "impliedVolatility": 15},
                        "PE": {"openInterest": 1500, "impliedVolatility": 17},
                    }
                ]
            }
        }
    )

    res = await agent.analyze("INFY")

    assert isinstance(res, OptionsFlowOutput)
    assert res.symbol == "INFY"
    # Python fallback compute: PCR = 1500 / 1000 = 1.5
    assert res.put_call_ratio == 1.5
    assert res.oi_concentration == "BEARISH_OI"
    assert res.signal_hint == "BEARISH"
