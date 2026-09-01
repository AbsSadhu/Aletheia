"""Alpha factor computation endpoints.

  GET /factors/{ticker}
  GET /factors/{ticker}/ic-scores
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aletheia.core.api.dependencies import get_market_data_engine
from aletheia.core.marketdata.models import MarketDataRequest

router = APIRouter(prefix="/api/v1")


@router.get("/factors/{ticker}")
async def compute_factors(
    ticker: str,
    exchange: str = "NSE",
    start: str = "",
    end: str = "",
) -> dict:
    """
    Compute all registered alpha factors for a ticker.
    Fetches OHLCV history and runs the full factor registry.
    """
    from aletheia.factors.registry import get_registry
    import pandas as pd

    engine = get_market_data_engine()

    # Default: last 90 trading days
    if not start or not end:
        from datetime import date, timedelta
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=130)).isoformat()

    try:
        candles = await engine.get_historical(
            MarketDataRequest(symbol=ticker.upper(), exchange=exchange),
            start=start,
            end=end,
            interval="1d",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch OHLCV data: {exc}")

    if not candles:
        raise HTTPException(status_code=404, detail=f"No OHLCV data found for {ticker}")

    # Build OHLCV DataFrame
    df = pd.DataFrame([
        {
            "date": c.date,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ])
    df = df.sort_values("date").reset_index(drop=True)

    registry = get_registry()
    results = registry.compute_all(df)
    composite = registry.composite_signal(results)

    return {
        "ticker": ticker.upper(),
        "exchange": exchange,
        "bars": len(df),
        "from": start,
        "to": end,
        "factors": {name: output.model_dump() for name, output in results.items()},
        "composite": composite,
    }


@router.get("/factors/{ticker}/ic-scores")
async def get_factor_ic_scores(ticker: str) -> dict:
    """Return IC scores for all factors (from historical IC scorer DB)."""
    from aletheia.factors.ic_scorer import ICScorer
    scorer = ICScorer()
    return {"ticker": ticker.upper(), "ic_scores": scorer.list_scores_as_dicts()}
