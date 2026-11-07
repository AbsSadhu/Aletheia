"""Market data for the agent: a compact summary for the model, full bars for the chart.

The model only ever sees the summary (a year of daily bars would flood a small context window and
tempt it to quote numbers from memory). The bars travel in `_display` to the chat UI, which draws
them as a candlestick chart straight from the data.
"""

import asyncio
from typing import Any, ClassVar

import pandas as pd
import yfinance as yf

from aletheia.core.marketdata.candles import IST_OFFSET_SECS, frame_to_candles
from aletheia.core.marketdata.symbols import apply_rename, yahoo_symbol
from aletheia.core.tools.registry import BaseTool

PERIODS = ("5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max")
INTERVALS = ("1d", "1wk", "1h", "15m", "5m")
MAX_BARS = 1500


def resolve_candidates(symbol: str, exchange: str) -> list[str]:
    """Yahoo symbols to try, in order.

    A bare ticker is read as Indian by default (this app is India-first): `INFY` means
    `INFY.NS`, not the US-listed ADR, and the bare ticker is kept as a second try. Symbols that
    already name their market (suffix, index caret, coin pair) get one candidate. Renamed
    listings and hyphenated NSE tickers resolve as everywhere else (`marketdata.symbols`).
    Use exchange="US" for US tickers.
    """
    s = symbol.strip().upper()
    ex = exchange.strip().upper()
    if ex == "US" and "/" not in s:
        return [s]
    primary = yahoo_symbol(s, ex)
    if "/" in s or primary == s:
        return [primary]
    return [primary, apply_rename(s)]


def load_bars(symbol: str, exchange: str, period: str, interval: str) -> dict[str, Any]:
    """Blocking. {"symbol", "currency", "bars", "daily", "tz_offset_secs"} or {"error"}.

    `bars` are candle dicts (time, open, high, low, close, volume), oldest first.
    """
    tried: list[str] = []
    for candidate in resolve_candidates(symbol, exchange):
        tried.append(candidate)
        ticker = yf.Ticker(candidate)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            continue
        daily = interval in ("1d", "1wk")
        bars = frame_to_candles(df, daily)[-MAX_BARS:]
        if not bars:
            continue
        indian = candidate.endswith((".NS", ".BO"))
        try:
            currency = ticker.fast_info.get("currency")
        except Exception:
            currency = None
        return {
            "symbol": candidate,
            "currency": currency or ("INR" if indian else "USD"),
            "bars": bars,
            "daily": daily,
            "tz_offset_secs": IST_OFFSET_SECS if (indian and not daily) else 0,
        }
    return {
        "error": f"No market data found for '{symbol}' (tried {', '.join(tried)}). "
        "For a non-Indian stock pass exchange='US'."
    }


def bars_to_rows(bars: list[dict[str, Any]]) -> list[list[float]]:
    return [[b["time"], b["open"], b["high"], b["low"], b["close"], b["volume"]] for b in bars]


def _fetch(symbol: str, exchange: str, period: str, interval: str) -> dict[str, Any]:
    loaded = load_bars(symbol, exchange, period, interval)
    if "error" in loaded:
        return loaded
    candidate, currency, bars = loaded["symbol"], loaded["currency"], loaded["bars"]
    first, last = bars[0], bars[-1]
    summary: dict[str, Any] = {
        "symbol": symbol.upper(),
        "resolved_symbol": candidate,
        "currency": currency,
        "period": period,
        "interval": interval,
        "bars": len(bars),
        "first_bar": pd.Timestamp(first["time"], unit="s").strftime("%Y-%m-%d"),
        "last_bar": pd.Timestamp(last["time"], unit="s").strftime("%Y-%m-%d"),
        "last_close": last["close"],
        "previous_close": bars[-2]["close"] if len(bars) > 1 else None,
        "period_start_close": first["close"],
        "period_change_pct": round((last["close"] / first["close"] - 1) * 100, 2),
        "period_high": max(b["high"] for b in bars),
        "period_low": min(b["low"] for b in bars),
        "average_volume": round(sum(b["volume"] for b in bars) / len(bars)),
        "note": "A price chart of these bars is shown to the user automatically.",
    }
    if candidate != symbol.upper():
        summary["note"] += f" '{symbol}' was resolved to {candidate}."
    summary["_display"] = {
        "type": "ohlcv",
        "symbol": candidate,
        "currency": currency,
        "interval": interval,
        "tz_offset_secs": loaded["tz_offset_secs"],
        "bars": bars_to_rows(bars),
    }
    return summary


class MarketDataTool(BaseTool):
    """Fetches historical OHLCV data for a ticker symbol."""

    name: ClassVar[str] = "market_data"
    description: ClassVar[str] = (
        "Fetch price history (OHLCV) for a ticker and return a summary: last close, period "
        "change, high/low, average volume. A candlestick chart is shown to the user "
        "automatically. Bare tickers are treated as NSE stocks (INFY -> INFY.NS)."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Ticker, e.g. RELIANCE, TCS.NS, ^NSEI, BTC/USDT, or AAPL with exchange=US.",
            },
            "period": {
                "type": "string",
                "enum": list(PERIODS),
                "description": "How far back to fetch. Default 1mo.",
            },
            "interval": {
                "type": "string",
                "enum": list(INTERVALS),
                "description": "Bar size. Default 1d. Intraday sizes only work for short periods.",
            },
            "exchange": {
                "type": "string",
                "enum": ["NSE", "BSE", "US"],
                "description": "Where a bare ticker is listed. Default NSE.",
            },
        },
        "required": ["symbol"],
    }

    async def execute(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> Any:
        if period not in PERIODS:
            return {"error": f"period must be one of {', '.join(PERIODS)}"}
        if interval not in INTERVALS:
            return {"error": f"interval must be one of {', '.join(INTERVALS)}"}
        try:
            return await asyncio.to_thread(_fetch, symbol, exchange, period, interval)
        except Exception as e:
            return {"error": str(e)}
