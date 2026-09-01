"""
Volume factors: VWAP deviation, Volume Ratio, OBV Trend.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aletheia.factors._base import Factor, FactorOutput


class VWAPDeviationFactor(Factor):
    name = "vwap_deviation"
    category = "volume"
    lookback_periods = 20
    expected_sign = "negative"
    description = "Deviation of current price from VWAP — mean reversion signal via volume-weighted price"

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        closes = ohlcv["close"].astype(float)
        volumes = ohlcv["volume"].astype(float)

        # Rolling VWAP over lookback_periods
        typical_price = (ohlcv["high"].astype(float) + ohlcv["low"].astype(float) + closes) / 3
        vwap = (typical_price * volumes).rolling(self.lookback_periods).sum() / \
               volumes.rolling(self.lookback_periods).sum()

        last_close = float(closes.iloc[-1])
        last_vwap = float(vwap.iloc[-1])

        if last_vwap == 0:
            deviation_pct = 0.0
        else:
            deviation_pct = (last_close - last_vwap) / last_vwap * 100

        # Negative deviation = price below VWAP = buy signal
        norm = self._normalize(deviation_pct, -5.0, 5.0)
        buy_norm = 1.0 - norm

        if deviation_pct < -3.0:
            signal = "BUY"
            conf = 0.75
        elif deviation_pct < -1.0:
            signal = "BUY"
            conf = 0.55
        elif deviation_pct > 3.0:
            signal = "SELL"
            conf = 0.75
        elif deviation_pct > 1.0:
            signal = "SELL"
            conf = 0.55
        else:
            signal = "HOLD"
            conf = 0.35

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(deviation_pct, 3),
            normalized=round(buy_norm, 4),
            signal=signal,
            confidence=conf,
            description=f"VWAP={last_vwap:.2f}, Price={last_close:.2f}, Dev={deviation_pct:.2f}%",
        )


class VolumeRatioFactor(Factor):
    name = "volume_ratio"
    category = "volume"
    lookback_periods = 20
    expected_sign = "positive"
    description = "Current volume vs 20-bar average — detects unusual volume spikes"

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        volumes = ohlcv["volume"].astype(float)
        avg_volume = volumes.rolling(self.lookback_periods).mean()

        last_vol = float(volumes.iloc[-1])
        avg_vol = float(avg_volume.iloc[-1])

        ratio = last_vol / avg_vol if avg_vol > 0 else 1.0
        norm = self._normalize(ratio, 0.0, 4.0)

        # High volume = directional confirmation (not itself a buy/sell signal)
        # Use HOLD unless volume is extreme (signal = "HOLD" with high conf = strong trend)
        if ratio > 2.5:
            signal = "BUY"  # breakout confirmation
            conf = 0.7
        elif ratio < 0.3:
            signal = "SELL"  # low volume sell-off
            conf = 0.5
        else:
            signal = "HOLD"
            conf = 0.4

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(ratio, 3),
            normalized=round(norm, 4),
            signal=signal,
            confidence=conf,
            description=f"Volume ratio={ratio:.2f}x (cur={last_vol:.0f}, avg={avg_vol:.0f})",
        )


class OBVTrendFactor(Factor):
    name = "obv_trend"
    category = "volume"
    lookback_periods = 14
    expected_sign = "positive"
    description = "On-Balance Volume trend slope — smart money accumulation/distribution"

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        closes = ohlcv["close"].astype(float)
        volumes = ohlcv["volume"].astype(float)

        # Compute OBV
        direction = closes.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (direction * volumes).cumsum()

        # Slope of OBV over lookback
        obv_tail = obv.iloc[-self.lookback_periods:]
        if len(obv_tail) < 2:
            slope = 0.0
        else:
            x = np.arange(len(obv_tail))
            coeffs = np.polyfit(x, obv_tail.values, 1)
            slope = float(coeffs[0])

        # Normalize slope
        obv_std = float(obv.rolling(self.lookback_periods * 2).std().iloc[-1]) or 1.0
        norm_slope = slope / obv_std if obv_std > 0 else 0.0
        norm = self._normalize(norm_slope, -3.0, 3.0)

        signal = self._signal_from_normalized(norm)
        conf = min(0.8, 0.4 + abs(norm_slope) / 3.0 * 0.4)

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(slope, 2),
            normalized=round(norm, 4),
            signal=signal,
            confidence=round(conf, 3),
            description=f"OBV slope={slope:.0f}/bar (normalized={norm_slope:.2f}σ)",
        )
