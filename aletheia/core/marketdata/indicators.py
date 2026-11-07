"""Technical indicators on a close/high/low series, with the conventional definitions.

- RSI uses Wilder smoothing seeded with a simple average of the first `period` changes, the way
  charting packages do (a plain rolling mean, or an EMA seeded from the first value, gives
  different numbers for the first stretch).
- MACD is EMA(12) - EMA(26), signal EMA(9) of that, all with `adjust=False`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def _wilder(values: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: seed with the mean of the first `period` values, then
    avg = (prev * (period - 1) + value) / period. Leading values are NaN."""
    out = np.full(len(values), np.nan)
    arr = values.to_numpy(dtype=float)
    if len(arr) < period:
        return pd.Series(out, index=values.index)
    out[period - 1] = arr[:period].mean()
    for i in range(period, len(arr)):
        out[i] = (out[i - 1] * (period - 1) + arr[i]) / period
    return pd.Series(out, index=values.index)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).iloc[1:]
    loss = (-delta.clip(upper=0)).iloc[1:]
    avg_gain = _wilder(gain, period).reindex(close.index)
    avg_loss = _wilder(loss, period).reindex(close.index)
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # No losses at all in the window is RSI 100, not NaN.
    out[(avg_loss == 0) & avg_gain.notna()] = 100.0
    return out


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def bollinger(
    close: pd.Series, period: int = 20, width: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    return mid - width * sd, mid, mid + width * sd


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    return _wilder(tr, period)
