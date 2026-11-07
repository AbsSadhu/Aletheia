"""Technical indicators computed from real price bars (no placeholder values)."""

import asyncio
from typing import Any, ClassVar

import pandas as pd

from aletheia.core.marketdata import indicators as ind
from aletheia.core.tools.market_data_tool import (
    INTERVALS,
    PERIODS,
    bars_to_rows,
    load_bars,
)
from aletheia.core.tools.registry import BaseTool


def _series_rows(times: pd.Series, values: pd.Series) -> list[list[float]]:
    """[[time, value]] without the warm-up NaNs, so the chart draws from where values exist."""
    return [[int(t), round(float(v), 4)] for t, v in zip(times, values) if pd.notna(v)]


def _last(values: pd.Series) -> float | None:
    v = values.iloc[-1]
    return round(float(v), 4) if pd.notna(v) else None


def _rsi_zone(value: float | None) -> str | None:
    if value is None:
        return None
    return "overbought (>70)" if value > 70 else "oversold (<30)" if value < 30 else "neutral"


def _above_below(price: float, level: float | None) -> str | None:
    if level is None:
        return None
    return "above" if price > level else "below"


def compute(symbol: str, exchange: str, period: str, interval: str) -> dict[str, Any]:
    """Blocking."""
    loaded = load_bars(symbol, exchange, period, interval)
    if "error" in loaded:
        return loaded
    bars = loaded["bars"]
    df = pd.DataFrame(bars)
    close, high, low = df["close"], df["high"], df["low"]

    sma20, sma50 = ind.sma(close, 20), ind.sma(close, 50)
    rsi14 = ind.rsi(close, 14)
    macd_line, macd_sig, macd_hist = ind.macd(close)
    bb_lo, _bb_mid, bb_hi = ind.bollinger(close)
    atr14 = ind.atr(high, low, close)

    last_close = float(close.iloc[-1])
    rsi_now = _last(rsi14)
    m, s = _last(macd_line), _last(macd_sig)
    latest: dict[str, Any] = {
        "last_close": round(last_close, 4),
        "sma_20": _last(sma20),
        "sma_50": _last(sma50),
        "rsi_14": rsi_now,
        "macd": m,
        "macd_signal": s,
        "macd_histogram": _last(macd_hist),
        "bollinger_lower": _last(bb_lo),
        "bollinger_upper": _last(bb_hi),
        "atr_14": _last(atr14),
    }
    readout = {
        "rsi_zone": _rsi_zone(rsi_now),
        "price_vs_sma_20": _above_below(last_close, latest["sma_20"]),
        "price_vs_sma_50": _above_below(last_close, latest["sma_50"]),
        "macd_vs_signal": None if m is None or s is None else ("above" if m > s else "below"),
    }
    times = df["time"]
    return {
        "symbol": symbol.upper(),
        "resolved_symbol": loaded["symbol"],
        "currency": loaded["currency"],
        "period": period,
        "interval": interval,
        "bars": len(bars),
        "latest": latest,
        "readout": readout,
        "not_enough_history_for": [k for k, v in latest.items() if v is None],
        "note": "Indicators are computed from price bars; a chart with them is shown to the user.",
        "_display": {
            "type": "ohlcv",
            "symbol": loaded["symbol"],
            "currency": loaded["currency"],
            "interval": interval,
            "tz_offset_secs": loaded["tz_offset_secs"],
            "bars": bars_to_rows(bars),
            "overlays": {
                "SMA 20": _series_rows(times, sma20),
                "SMA 50": _series_rows(times, sma50),
                "BB upper": _series_rows(times, bb_hi),
                "BB lower": _series_rows(times, bb_lo),
            },
            "panes": {
                "RSI 14": {
                    "kind": "line",
                    "levels": [30, 70],
                    "series": _series_rows(times, rsi14),
                },
                "MACD": {
                    "kind": "macd",
                    "macd": _series_rows(times, macd_line),
                    "signal": _series_rows(times, macd_sig),
                    "histogram": _series_rows(times, macd_hist),
                },
            },
        },
    }


class TechnicalAnalysisTool(BaseTool):
    """Calculates technical indicators for a given ticker symbol."""

    name: ClassVar[str] = "technical_analysis"
    description: ClassVar[str] = (
        "Compute RSI(14), MACD(12,26,9), SMA 20/50, Bollinger Bands and ATR for a ticker from its "
        "price history and return the latest values. A chart with the indicators is shown to the "
        "user automatically. Bare tickers are treated as NSE stocks."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker, e.g. RELIANCE, TCS.NS, ^NSEI."},
            "period": {
                "type": "string",
                "enum": list(PERIODS),
                "description": "History to compute over. Default 1y (SMA 50 needs 50+ bars).",
            },
            "interval": {"type": "string", "enum": list(INTERVALS), "description": "Default 1d."},
            "exchange": {
                "type": "string",
                "enum": ["NSE", "BSE", "US"],
                "description": "Default NSE.",
            },
        },
        "required": ["symbol"],
    }

    async def execute(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> Any:
        if period not in PERIODS:
            return {"error": f"period must be one of {', '.join(PERIODS)}"}
        if interval not in INTERVALS:
            return {"error": f"interval must be one of {', '.join(INTERVALS)}"}
        try:
            return await asyncio.to_thread(compute, symbol, exchange, period, interval)
        except Exception as e:
            return {"error": str(e)}
