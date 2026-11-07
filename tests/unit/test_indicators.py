"""Indicators checked against published reference values, not against themselves."""

import math

import pandas as pd
import pytest

from aletheia.core.marketdata import indicators as ind

# The classic Wilder RSI worked example (StockCharts "RSI" article): 14-period closes and the
# RSI values it publishes for the first bars after the seed window.
CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61,
    46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45, 45.78, 45.35,
    44.03, 44.18, 44.22, 44.57, 43.42, 42.66, 43.13,
]  # fmt: skip
PUBLISHED_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38]


def test_rsi_matches_published_wilder_example() -> None:
    out = ind.rsi(pd.Series(CLOSES), 14)
    assert out.iloc[:14].isna().all()
    for got, want in zip(out.iloc[14:24], PUBLISHED_RSI):
        assert got == pytest.approx(want, abs=0.15)


def test_rsi_all_gains_is_100_and_short_series_is_nan() -> None:
    assert ind.rsi(pd.Series(range(1, 40)), 14).iloc[-1] == 100.0
    assert ind.rsi(pd.Series([1.0, 2.0, 3.0]), 14).isna().all()


def test_macd_follows_its_definition() -> None:
    close = pd.Series([10 + 0.3 * i + (i % 5) for i in range(80)], dtype=float)
    line, sig, hist = ind.macd(close)
    manual = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    assert line.iloc[-1] == pytest.approx(manual.iloc[-1])
    assert sig.iloc[-1] == pytest.approx(manual.ewm(span=9, adjust=False).mean().iloc[-1])
    assert hist.iloc[-1] == pytest.approx(line.iloc[-1] - sig.iloc[-1])


def test_sma_and_bollinger() -> None:
    close = pd.Series([float(i) for i in range(1, 31)])
    assert ind.sma(close, 20).iloc[-1] == pytest.approx(sum(range(11, 31)) / 20)
    lo, mid, hi = ind.bollinger(close, 20, 2)
    sd = math.sqrt(sum((x - 20.5) ** 2 for x in range(11, 31)) / 20)  # population sd
    assert hi.iloc[-1] - mid.iloc[-1] == pytest.approx(2 * sd)
    assert mid.iloc[-1] - lo.iloc[-1] == pytest.approx(2 * sd)


def test_atr_constant_range() -> None:
    high = pd.Series([11.0] * 30)
    low = pd.Series([9.0] * 30)
    close = pd.Series([10.0] * 30)
    assert ind.atr(high, low, close, 14).iloc[-1] == pytest.approx(2.0)
