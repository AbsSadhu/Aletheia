"""
Momentum factors: RSI, MACD, Momentum Score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aletheia.factors._base import Factor, FactorOutput


class RSIFactor(Factor):
    name = "rsi"
    category = "momentum"
    lookback_periods = 14
    expected_sign = "neutral"
    description = "Relative Strength Index — measures overbought/oversold conditions"

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        closes = ohlcv["close"].astype(float)
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0).rolling(self.lookback_periods).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(self.lookback_periods).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1])

        # RSI: 0=oversold(buy), 100=overbought(sell)
        normalized = self._normalize(rsi, 0, 100)
        # Invert: low RSI = buy signal
        buy_norm = 1.0 - normalized

        # Classic thresholds: RSI < 30 → BUY, RSI > 70 → SELL
        if rsi < 30:
            signal = "BUY"
            conf = 0.75
        elif rsi > 70:
            signal = "SELL"
            conf = 0.75
        elif 30 <= rsi <= 45:
            signal = "BUY"
            conf = 0.5
        elif 55 <= rsi <= 70:
            signal = "SELL"
            conf = 0.5
        else:
            signal = "HOLD"
            conf = 0.4

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(rsi, 2),
            normalized=round(buy_norm, 4),
            signal=signal,
            confidence=conf,
            description=f"RSI({self.lookback_periods})={rsi:.1f}",
        )


class MACDFactor(Factor):
    name = "macd"
    category = "momentum"
    lookback_periods = 26
    expected_sign = "positive"
    description = "MACD histogram crossover — trend direction signal"
    fast: int = 12
    slow: int = 26
    signal_period: int = 9

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        closes = ohlcv["close"].astype(float)
        ema_fast = closes.ewm(span=self.fast, adjust=False).mean()
        ema_slow = closes.ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        hist_val = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-2]) if len(histogram) > 1 else 0.0

        # Normalize based on rolling std of histogram
        hist_std = float(histogram.rolling(20).std().iloc[-1]) or 1.0
        norm = self._normalize(hist_val, -2 * hist_std, 2 * hist_std)

        if hist_val > 0 and hist_val > hist_prev:
            signal = "BUY"
            conf = min(0.8, 0.5 + abs(hist_val) / (hist_std * 2))
        elif hist_val < 0 and hist_val < hist_prev:
            signal = "SELL"
            conf = min(0.8, 0.5 + abs(hist_val) / (hist_std * 2))
        else:
            signal = "HOLD"
            conf = 0.35

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(hist_val, 4),
            normalized=round(norm, 4),
            signal=signal,
            confidence=round(conf, 3),
            description=f"MACD hist={hist_val:.4f} (prev={hist_prev:.4f})",
        )


class MomentumScoreFactor(Factor):
    name = "momentum_score"
    category = "momentum"
    lookback_periods = 20
    expected_sign = "positive"
    description = "Rate of change (ROC) momentum score — 20-bar price momentum"

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        closes = ohlcv["close"].astype(float)
        roc = (closes.iloc[-1] - closes.iloc[-self.lookback_periods]) / closes.iloc[-self.lookback_periods] * 100
        norm = self._normalize(roc, -20, 20)
        signal = self._signal_from_normalized(norm)
        conf = min(0.85, 0.4 + abs(roc) / 20 * 0.45)

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(float(roc), 3),
            normalized=round(norm, 4),
            signal=signal,
            confidence=round(conf, 3),
            description=f"20-bar ROC={roc:.2f}%",
        )
