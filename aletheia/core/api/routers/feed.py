"""Live feed control: the watchlist and the feed's health.

GET /watchlist
PUT /watchlist                   replace the list; the live stream follows immediately
GET /marketdata/feed-status      mode (stream/polling), market hours, stream health, setup hints
GET /marketdata/snapshot         latest known quote per symbol
GET /marketdata/candles          OHLCV history for the chart (1m/5m/15m/1h/1d)
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aletheia.core.api.dependencies import get_feed_manager, get_watchlist_store
from aletheia.core.marketdata import candles as candle_source
from aletheia.core.marketdata.watchlist import WatchItem

router = APIRouter(prefix="/api/v1")


class WatchlistUpdate(BaseModel):
    items: list[WatchItem]


@router.get("/watchlist")
async def read_watchlist() -> dict:
    return {
        "items": [{"symbol": s, "exchange": e} for s, e in get_watchlist_store().items()],
    }


@router.put("/watchlist")
async def update_watchlist(body: WatchlistUpdate) -> dict:
    try:
        saved = get_watchlist_store().save(body.items)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    manager = get_feed_manager()
    await manager.apply_watchlist()
    return {
        "items": [{"symbol": s, "exchange": e} for s, e in saved],
        "unresolved_symbols": manager.unresolved_symbols(),
    }


@router.get("/marketdata/feed-status")
async def feed_status() -> dict:
    return get_feed_manager().status()


@router.get("/marketdata/snapshot")
async def feed_snapshot() -> dict:
    return {"quotes": get_feed_manager().snapshot()}


@router.get("/marketdata/candles")
async def candles(symbol: str, exchange: str = "NSE", interval: str = "5m") -> dict:
    try:
        item = WatchItem(
            symbol=symbol, exchange=exchange
        )  # same symbol/exchange rules as the watchlist
        payload = await asyncio.to_thread(
            candle_source.fetch_candles, item.symbol, item.exchange, interval
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch candles: {exc}") from exc
    if not payload["candles"]:
        raise HTTPException(status_code=404, detail=f"No {interval} data for {item.symbol}.")
    return payload
