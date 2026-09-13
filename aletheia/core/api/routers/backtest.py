"""Event-driven backtest endpoint.

POST /backtest
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aletheia.core.config.settings import get_settings
from aletheia.core.execution.position_sizing import PositionSizer
from aletheia.extensions.backtest.runner import BacktestRunner
from aletheia.extensions.backtest.strategy import StrategySignal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


class BacktestRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    strategy: str = "sma_crossover"
    initial_capital: float = 100_000.0


def resolve_signal_quantity(
    signal: StrategySignal, price: float, runner: BacktestRunner
) -> float:
    """StrategySignal.quantity=None means "caller sizes the position" (see
    strategy.py) -- a strategy that follows that documented contract must
    not have its signal silently dropped."""
    quantity = signal.quantity
    if quantity and quantity > 0:
        return quantity
    if signal.action == "buy":
        return PositionSizer.compute_shares(
            runner.current_capital, price, portfolio_value=runner.current_capital
        )
    if signal.action == "sell":
        held = runner.positions.get(signal.symbol)
        return held.quantity if held else 0
    return 0


@router.post("/backtest")
async def run_backtest(request: BacktestRequest) -> dict:
    """
    Fetch historical data and run an event-driven backtest.
    Returns BacktestResult with metrics and equity curve.
    """
    from aletheia.extensions.backtest.data_feed import HistoricalDataFeed
    from aletheia.extensions.backtest.strategies import get_strategy

    try:
        strategy = get_strategy(request.strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    settings = get_settings()
    feed = HistoricalDataFeed(duckdb_path=settings.duckdb_path)
    runner = BacktestRunner(initial_capital=request.initial_capital)

    # Fetch data for all symbols
    fetch_tasks = [
        feed.fetch_and_store(sym, request.start_date, request.end_date) for sym in request.symbols
    ]
    try:
        await asyncio.gather(*fetch_tasks)
    except Exception as exc:
        logger.error("Backtest data fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    # Build per-date market snapshot and drive backtest
    all_candles: dict[str, Any] = {}
    for sym in request.symbols:
        candles = feed.get_candles(sym, request.start_date, request.end_date)
        all_candles[sym] = candles

    # Drive event loop: for each trading day across all symbols
    date_set: set[str] = set()
    for candles in all_candles.values():
        for c in candles:
            date_set.add(c.date)

    for trading_date in sorted(date_set):
        day_data: dict[str, dict] = {}
        for sym, candles in all_candles.items():
            candle = next((c for c in candles if c.date == trading_date), None)
            if candle:
                day_data[sym] = {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
        for signal in strategy.on_bar(trading_date, day_data, runner.positions, runner.current_capital):
            price = day_data.get(signal.symbol, {}).get("close")
            if price is None:
                continue

            quantity = resolve_signal_quantity(signal, price, runner)
            if not quantity or quantity <= 0:
                continue

            runner.submit_order(signal.symbol, "market", signal.action, quantity, price=price)
        runner.execute_orders(day_data)
        runner.update_equity(day_data)

    result = runner.generate_report(
        strategy_name=request.strategy,
        start_date=request.start_date,
        end_date=request.end_date,
    )

    from aletheia.extensions.backtest.storage import BacktestResultStore

    BacktestResultStore(str(settings.data_dir / "backtest_results.db")).save(result)

    return result.model_dump(mode="json")
