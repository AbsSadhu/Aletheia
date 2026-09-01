"""Market data quote/history/replay endpoints.

  GET /market-data/quote
  GET /market-data/history
  GET /market-data/replay
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aletheia.core.api.dependencies import get_market_data_engine
from aletheia.core.marketdata.models import MarketDataRequest

router = APIRouter(prefix="/api/v1")


@router.get("/market-data/quote")
async def get_market_quote(
    symbol: str,
    exchange: str = "NSE",
    provider: str | None = None,
) -> dict:
    engine = get_market_data_engine()
    quote = await engine.get_quote(
        MarketDataRequest(symbol=symbol, exchange=exchange, provider=provider)
    )
    return {"quote": quote.model_dump(mode="json")}


@router.get("/market-data/history")
async def get_market_history(
    symbol: str,
    exchange: str = "NSE",
    start: str = "",
    end: str = "",
    interval: str = "1d",
    provider: str | None = None,
) -> dict:
    if not start or not end:
        raise HTTPException(status_code=400, detail="Both start and end are required")
    engine = get_market_data_engine()
    candles = await engine.get_historical(
        MarketDataRequest(symbol=symbol, exchange=exchange, provider=provider),
        start=start,
        end=end,
        interval=interval,
    )
    return {"candles": [candle.model_dump(mode="json") for candle in candles]}


@router.get("/market-data/replay")
async def replay_market_history(
    symbol: str,
    exchange: str = "NSE",
    start: str = "",
    end: str = "",
    timeframe: str = "1d",
) -> dict:
    if not start or not end:
        raise HTTPException(status_code=400, detail="Both start and end are required")
    engine = get_market_data_engine()
    candles = []
    async for candle in engine.replay_candles(symbol, exchange, start, end, timeframe, speed=0.0):
        candles.append(candle.model_dump(mode="json"))
    return {"candles": candles}
