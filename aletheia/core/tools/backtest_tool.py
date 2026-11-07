"""Run the app's real event-driven backtest from chat (same code path as the Backtest page)."""

import asyncio
from datetime import date
from typing import Any, ClassVar

from fastapi import HTTPException

from aletheia.core.marketdata.symbols import yahoo_symbol
from aletheia.core.tools.registry import BaseTool

TIMEOUT_SECS = 150
MAX_SYMBOLS = 10


def _yahoo(symbol: str) -> str:
    """The data feed stores Yahoo symbols; a bare ticker means the NSE listing."""
    return yahoo_symbol(symbol.strip(), "NSE")


def _curve_points(curve: list[dict[str, Any]]) -> list[list[float]]:
    """[[trading_day_number, equity]]. The runner records values per step, with no dates."""
    return [
        [int(row["step"]), round(float(row["value"]), 2)]
        for row in curve
        if "step" in row and "value" in row
    ]


class BacktestTool(BaseTool):
    """Runs a backtest for a strategy."""

    name: ClassVar[str] = "backtest"
    description: ClassVar[str] = (
        "Run a historical backtest of a built-in strategy on NSE symbols and return return, "
        "Sharpe, drawdown and trade metrics. An equity-curve chart is shown to the user. "
        "This simulates past data only; it says nothing certain about future returns."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "strategy_name": {
                "type": "string",
                "description": "A built-in strategy, e.g. sma_crossover.",
            },
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "NSE symbols without suffix, e.g. [RELIANCE, TCS].",
            },
            "start_date": {"type": "string", "description": "YYYY-MM-DD."},
            "end_date": {"type": "string", "description": "YYYY-MM-DD."},
            "initial_capital": {"type": "number", "description": "Default 100000."},
        },
        "required": ["strategy_name", "symbols", "start_date", "end_date"],
    }

    async def execute(
        self,
        strategy_name: str,
        symbols: list[str],
        start_date: str,
        end_date: str,
        initial_capital: float = 100_000.0,
        **kwargs: Any,
    ) -> Any:
        from aletheia.core.api.routers.backtest import BacktestRequest, run_backtest
        from aletheia.extensions.backtest.strategies import available_strategies

        if strategy_name not in available_strategies():
            return {"error": f"Unknown strategy. Available: {', '.join(available_strategies())}"}
        if not symbols or len(symbols) > MAX_SYMBOLS:
            return {"error": f"Give between 1 and {MAX_SYMBOLS} symbols."}
        try:
            date.fromisoformat(start_date)
            date.fromisoformat(end_date)
        except ValueError:
            return {"error": "Dates must be YYYY-MM-DD."}

        request = BacktestRequest(
            symbols=[_yahoo(s) for s in symbols],
            start_date=start_date,
            end_date=end_date,
            strategy=strategy_name,
            initial_capital=initial_capital,
        )
        try:
            result = await asyncio.wait_for(run_backtest(request), TIMEOUT_SECS)
        except HTTPException as exc:
            return {"error": str(exc.detail)}
        except asyncio.TimeoutError:
            return {"error": f"The backtest took longer than {TIMEOUT_SECS}s; try a shorter range."}

        points = _curve_points(result.get("equity_curve", []))
        summary: dict[str, Any] = {
            "run_id": result["run_id"],
            "strategy": result["strategy_name"],
            "symbols": request.symbols,
            "period": f"{result['start_date']} to {result['end_date']}",
            "initial_capital": result["initial_capital"],
            "final_capital": round(result["final_capital"], 2),
            "total_return_pct": round(result["total_return"] * 100, 2),
            "metrics": result.get("metrics", {}),
            "orders": len(result.get("orders", [])),
            "caveat": "Past performance in a simulation; not a forecast or advice.",
        }
        if not summary["orders"]:
            summary["warning"] = (
                "The strategy placed no trades, so these figures are empty, not a result. "
                "Either it never signalled in this window or no price data was found."
            )
        if points:
            summary["_display"] = {
                "type": "line",
                "title": f"{result['strategy_name']} equity (simulated)",
                "x_label": "Trading day",
                "baseline": result["initial_capital"],
                "points": points,
            }
        return summary
