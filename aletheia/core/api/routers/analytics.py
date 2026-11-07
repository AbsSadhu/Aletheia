"""Cross-asset analytics.

GET /analytics/correlation   correlation matrix and the correlation-regime timeline for a set of symbols
                             (?symbols=NSE:INFY,NSE:TCS,BINANCE:BTC/USDT; defaults to your watchlist)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from aletheia.core.analytics.regime import MAX_ASSETS, MIN_ASSETS, compute
from aletheia.core.api.dependencies import get_watchlist_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


def _parse_items(symbols: str | None) -> list[tuple[str, str]]:
    if not symbols:
        return [(s, e) for s, e in get_watchlist_store().items()]
    items: list[tuple[str, str]] = []
    for part in symbols.split(","):
        part = part.strip()
        if not part:
            continue
        exchange, _, symbol = part.partition(":")
        if not symbol:  # a bare ticker means NSE
            exchange, symbol = "NSE", exchange
        items.append((symbol.strip().upper(), exchange.strip().upper()))
    return items


@router.get("/analytics/correlation")
async def correlation(
    symbols: str | None = Query(
        None, description="Comma-separated EXCHANGE:SYMBOL pairs; defaults to the watchlist"
    ),
    days: int = Query(180, ge=30, le=365, description="Timeline length in trading days"),
    corr_window: int = Query(60, ge=10, le=250),
    edge_threshold: float = Query(
        0.5, gt=0, lt=1, description="|correlation| at which a pair counts as an edge"
    ),
    smooth_window: int = Query(5, ge=1, le=60),
    enter_threshold: float = Query(0.65, gt=0, lt=1),
    exit_threshold: float = Query(0.45, gt=0, lt=1),
) -> dict:
    items = list(dict.fromkeys(_parse_items(symbols)))
    if len(items) < MIN_ASSETS:
        raise HTTPException(
            status_code=422,
            detail=f"Pick at least {MIN_ASSETS} symbols (your watchlist has {len(items)}).",
        )
    if len(items) > MAX_ASSETS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_ASSETS} symbols at once.")
    if exit_threshold >= enter_threshold:
        raise HTTPException(status_code=422, detail="exit_threshold must be below enter_threshold")
    try:
        return await compute(
            items,
            days=days,
            corr_window=corr_window,
            edge_threshold=edge_threshold,
            smooth_window=smooth_window,
            enter_threshold=enter_threshold,
            exit_threshold=exit_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("correlation analytics failed")
        raise HTTPException(
            status_code=502, detail="Could not compute correlations right now."
        ) from exc
