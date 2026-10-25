"""OHLCV candles for the chart (intraday and daily) from Yahoo Finance, with a short cache.

The chart's *last price* comes from the live feed; these candles are the history behind it.
NSE/BSE intraday on Yahoo can lag by up to ~15 minutes, which the API reports so the UI can say so.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

# our interval -> (yfinance interval, lookback period)
INTERVALS: dict[str, tuple[str, str]] = {
    "1m": ("1m", "5d"),
    "5m": ("5m", "30d"),
    "15m": ("15m", "30d"),
    "1h": ("60m", "90d"),
    "1d": ("1d", "2y"),
}
IST_OFFSET_SECS = 19_800
CACHE_TTL_SECS = 20.0
_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


def yahoo_symbol(symbol: str, exchange: str) -> str:
    s, e = symbol.upper(), exchange.upper()
    if "/" in s or e == "BINANCE":
        base, _, quote = s.partition("/")
        return f"{base}-{'USD' if quote in ('USDT', 'USD', '') else quote}"
    if s.startswith("^") or s.endswith((".NS", ".BO")):
        return s
    return f"{s}.{'BO' if e == 'BSE' else 'NS'}"


def frame_to_candles(df: pd.DataFrame, daily: bool) -> list[dict[str, float | int]]:
    """Rows -> [{time (epoch s), open, high, low, close, volume}], ascending, NaN rows dropped."""
    if df is None or df.empty:
        return []
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    out: list[dict[str, float | int]] = []
    for ts, row in df.iterrows():
        stamp = pd.Timestamp(ts)
        if daily:  # a date, not an instant: pin to UTC midnight so it never shifts a day
            epoch = int(pd.Timestamp(stamp.date(), tz="UTC").timestamp())
        else:
            epoch = int((stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp).timestamp())
        out.append(
            {
                "time": epoch,
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": float(row.get("Volume", 0) or 0),
            }
        )
    return out


def fetch_candles(symbol: str, exchange: str, interval: str) -> dict[str, Any]:
    """Blocking; call via asyncio.to_thread."""
    if interval not in INTERVALS:
        raise ValueError(f"interval must be one of {sorted(INTERVALS)}")
    key = (symbol.upper(), exchange.upper(), interval)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_SECS:
        return hit[1]

    import yfinance as yf

    yf_interval, period = INTERVALS[interval]
    df = yf.Ticker(yahoo_symbol(symbol, exchange)).history(
        period=period, interval=yf_interval, auto_adjust=True
    )
    daily = interval == "1d"
    indian = exchange.upper() in ("NSE", "BSE") and "/" not in symbol
    payload = {
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "interval": interval,
        "candles": frame_to_candles(df, daily),
        # Shift intraday timestamps so the chart's axis reads in IST clock time.
        "tz_offset_secs": IST_OFFSET_SECS if indian and not daily else 0,
        "source": "Yahoo Finance",
        "note": "Yahoo's NSE/BSE intraday data can lag by up to ~15 minutes; the live price comes from your feed."
        if indian
        else "Yahoo Finance data.",
    }
    _cache[key] = (time.time(), payload)
    return payload
