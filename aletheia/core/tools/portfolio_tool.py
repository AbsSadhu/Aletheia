"""Risk and correlation analytics for an equal-weighted basket, from real price history."""

import asyncio
from typing import Any, ClassVar

import pandas as pd

from aletheia.core.risk.metrics import compute_full_risk_metrics
from aletheia.core.tools.market_data_tool import load_bars
from aletheia.core.tools.registry import BaseTool

MAX_SYMBOLS = 12


def _analyse(symbols: list[str], exchange: str, period: str) -> dict[str, Any]:
    closes: dict[str, pd.Series] = {}
    missing: list[str] = []
    for sym in symbols:
        loaded = load_bars(sym, exchange, period, "1d")
        if "error" in loaded:
            missing.append(sym)
            continue
        closes[loaded["symbol"]] = pd.Series(
            [b["close"] for b in loaded["bars"]],
            index=pd.to_datetime([b["time"] for b in loaded["bars"]], unit="s"),
        )
    if len(closes) < 2:
        return {"error": "Need price history for at least 2 symbols.", "no_data_for": missing}

    prices = pd.DataFrame(closes).dropna()
    if len(prices) < 30:
        return {"error": "Fewer than 30 shared trading days across these symbols."}
    returns = prices.pct_change().dropna()
    basket = returns.mean(axis=1)  # equal-weight, daily rebalanced
    m = compute_full_risk_metrics(basket)

    corr = returns.corr()
    names = list(corr.columns)
    per_symbol = [
        [
            n,
            f"{((prices[n].iloc[-1] / prices[n].iloc[0]) - 1) * 100:+.1f}%",
            f"{returns[n].std() * (252**0.5) * 100:.1f}%",
        ]
        for n in names
    ]
    avg_pair = (corr.values.sum() - len(names)) / (len(names) * (len(names) - 1))
    return {
        "symbols": names,
        "no_data_for": missing,
        "period": period,
        "trading_days": len(returns),
        "weighting": "equal, rebalanced daily",
        "metrics": {
            "sharpe": round(m.sharpe, 2),
            "sortino": round(m.sortino, 2),
            "max_drawdown": round(m.max_drawdown, 4),
            "var_95_daily": round(m.var_95, 4),
            "annualised_volatility_pct": round(float(basket.std() * (252**0.5) * 100), 2),
            "average_pairwise_correlation": round(float(avg_pair), 2),
        },
        "per_symbol": [
            {"symbol": r[0], "return": r[1], "annualised_volatility": r[2]} for r in per_symbol
        ],
        "_display": {
            "type": "table",
            "title": f"Equal-weight basket, {period}",
            "rows": [
                ["Sharpe", f"{m.sharpe:.2f}"],
                ["Sortino", f"{m.sortino:.2f}"],
                ["Max drawdown", f"{m.max_drawdown * 100:.1f}%"],
                ["Daily VaR 95%", f"{m.var_95 * 100:.2f}%"],
                ["Avg pairwise correlation", f"{avg_pair:.2f}"],
            ],
            "note": "From daily closes; Sharpe uses a 6.5% annual risk-free rate.",
            "matrix": {
                "title": "Pairwise correlation of daily returns",
                "labels": names,
                "values": [[round(float(v), 2) for v in row] for row in corr.values],
            },
        },
    }


class PortfolioAnalyticsTool(BaseTool):
    """Calculates portfolio analytics."""

    name: ClassVar[str] = "portfolio_analytics"
    description: ClassVar[str] = (
        "Risk analytics for an equal-weighted basket of 2+ symbols from their daily price history: "
        "Sharpe, Sortino, max drawdown, VaR, volatility and pairwise correlation."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tickers, e.g. [RELIANCE, TCS, INFY]. Bare tickers are NSE.",
            },
            "period": {
                "type": "string",
                "enum": ["6mo", "1y", "2y", "5y"],
                "description": "History window. Default 1y.",
            },
            "exchange": {
                "type": "string",
                "enum": ["NSE", "BSE", "US"],
                "description": "Default NSE.",
            },
        },
        "required": ["symbols"],
    }

    async def execute(
        self, symbols: list[str], period: str = "1y", exchange: str = "NSE", **kwargs: Any
    ) -> Any:
        if not 2 <= len(symbols) <= MAX_SYMBOLS:
            return {"error": f"Give between 2 and {MAX_SYMBOLS} symbols."}
        if period not in ("6mo", "1y", "2y", "5y"):
            return {"error": "period must be one of 6mo, 1y, 2y, 5y"}
        try:
            return await asyncio.to_thread(_analyse, symbols, exchange, period)
        except Exception as e:
            return {"error": str(e)}
