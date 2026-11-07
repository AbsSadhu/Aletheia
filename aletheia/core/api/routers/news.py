"""Market news and sentiment.

GET /news/headlines   recent scored headlines (optional symbol / label filter)
GET /news/symbol      one symbol's headlines, 24h tone, flip state and alerts (?symbol=INFY)
GET /news/pulse       market mood, mood history, per-symbol tracker, movers with their headlines, and sentiment-flip alerts

Feeds are public RSS, fetched on demand and cached for ~20 seconds (the app polls every 30s). Scoring is a lexicon, not a model.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from aletheia.core.api.dependencies import get_feed_manager, get_news_service, get_watchlist_store

router = APIRouter(prefix="/api/v1")


def _watch_symbols() -> list[str]:
    return [symbol for symbol, _exchange in get_watchlist_store().items()]


@router.get("/news/headlines")
async def news_headlines(
    limit: int = Query(60, ge=1, le=200),
    symbol: str | None = None,
    label: Literal["bullish", "bearish", "neutral"] | None = None,
) -> dict:
    service = get_news_service()
    await service.ensure_fresh(_watch_symbols())
    return {"headlines": service.headlines(limit=limit, symbol=symbol, label=label)}


@router.get("/news/pulse")
async def news_pulse() -> dict:
    service = get_news_service()
    watch = _watch_symbols()
    await service.ensure_fresh(watch)
    return service.pulse(watch, get_feed_manager().snapshot())


@router.get("/news/symbol")
async def news_symbol(symbol: str = Query(..., min_length=1, max_length=24)) -> dict:
    service = get_news_service()
    await service.ensure_fresh([*_watch_symbols(), symbol])
    return service.symbol_view(symbol)
