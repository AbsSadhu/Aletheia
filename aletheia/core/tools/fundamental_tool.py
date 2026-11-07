import asyncio
from typing import Any, ClassVar

import yfinance as yf

from aletheia.core.tools.market_data_tool import resolve_candidates
from aletheia.core.tools.registry import BaseTool

_FIELDS = [
    ("market_cap", "marketCap", "money"),
    ("trailing_pe", "trailingPE", "ratio"),
    ("forward_pe", "forwardPE", "ratio"),
    ("eps", "trailingEps", "money"),
    ("dividend_yield", "dividendYield", "pct_points"),
    ("profit_margin", "profitMargins", "pct_fraction"),
    ("operating_margin", "operatingMargins", "pct_fraction"),
    ("return_on_equity", "returnOnEquity", "pct_fraction"),
    ("debt_to_equity", "debtToEquity", "ratio"),
    ("52_week_high", "fiftyTwoWeekHigh", "money"),
    ("52_week_low", "fiftyTwoWeekLow", "money"),
]
_LABELS = {
    "market_cap": "Market cap",
    "trailing_pe": "P/E (trailing)",
    "forward_pe": "P/E (forward)",
    "eps": "EPS (trailing)",
    "dividend_yield": "Dividend yield",
    "profit_margin": "Profit margin",
    "operating_margin": "Operating margin",
    "return_on_equity": "Return on equity",
    "debt_to_equity": "Debt / equity",
    "52_week_high": "52-week high",
    "52_week_low": "52-week low",
}


def _fmt(value: Any, kind: str, currency: str) -> str:
    if value is None:
        return "n/a"
    if kind == "pct_fraction":
        return f"{value * 100:.1f}%"
    if kind == "pct_points":  # Yahoo reports dividendYield as percent points in recent versions
        return f"{value:.2f}%"
    if kind == "ratio":
        return f"{value:.2f}"
    if abs(value) >= 1e7 and currency == "INR":
        return f"₹{value / 1e7:,.0f} Cr"
    if abs(value) >= 1e9:
        return f"{currency} {value / 1e9:,.1f}B"
    return f"{currency} {value:,.2f}"


def _fetch(symbol: str, exchange: str) -> dict[str, Any]:
    tried = []
    for candidate in resolve_candidates(symbol, exchange):
        tried.append(candidate)
        info = yf.Ticker(candidate).info or {}
        # An unknown ticker still returns a stub dict, so require a real market snapshot.
        if not (info.get("marketCap") or info.get("trailingPE") or info.get("regularMarketPrice")):
            continue
        currency = info.get("financialCurrency") or info.get("currency") or "USD"
        values = {key: info.get(src) for key, src, _ in _FIELDS}
        kinds = {key: kind for key, _, kind in _FIELDS}
        return {
            "symbol": symbol.upper(),
            "resolved_symbol": candidate,
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "currency": currency,
            **values,
            "_display": {
                "type": "table",
                "title": f"{info.get('shortName') or candidate} ({candidate}) fundamentals",
                "rows": [[_LABELS[k], _fmt(values[k], kinds[k], currency)] for k in values],
                "note": "Source: Yahoo Finance; may be delayed or incomplete.",
            },
        }
    return {
        "error": f"No fundamentals found for '{symbol}' (tried {', '.join(tried)}). "
        "For a non-Indian stock pass exchange='US'."
    }


class FundamentalDataTool(BaseTool):
    """Fetches fundamental data for a given ticker symbol."""

    name: ClassVar[str] = "fundamental_data"
    description: ClassVar[str] = (
        "Fetch fundamentals (market cap, P/E, EPS, margins, ROE, debt/equity, 52-week range) "
        "for a ticker. A table is shown to the user automatically. Bare tickers are NSE stocks."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Ticker, e.g. RELIANCE, TCS.NS, or AAPL with exchange=US.",
            },
            "exchange": {
                "type": "string",
                "enum": ["NSE", "BSE", "US"],
                "description": "Where a bare ticker is listed. Default NSE.",
            },
        },
        "required": ["symbol"],
    }

    async def execute(self, symbol: str, exchange: str = "NSE", **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(_fetch, symbol, exchange)
        except Exception as e:
            return {"error": str(e)}
