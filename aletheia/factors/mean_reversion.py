"""
Mean-reversion factors: Bollinger Bands, Z-Score.
"""

from __future__ import annotations

import pandas as pd

from aletheia.factors._base import Factor, FactorOutput


class BollingerBandFactor(Factor):
    name = "bollinger_band"
    category = "mean_reversion"
    lookback_periods = 20
    expected_sign = "negative"
    description = "Bollinger %B — position within bands (0=lower band, 1=upper band)"
    num_std: float = 2.0

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        closes = ohlcv["close"].astype(float)
        sma = closes.rolling(self.lookback_periods).mean()
        std = closes.rolling(self.lookback_periods).std()
        upper = sma + self.num_std * std
        lower = sma - self.num_std * std

        last_close = float(closes.iloc[-1])
        last_upper = float(upper.iloc[-1])
        last_lower = float(lower.iloc[-1])

        band_width = last_upper - last_lower
        pct_b = (last_close - last_lower) / band_width if band_width > 0 else 0.5

        # %B < 0 = below lower band (buy), %B > 1 = above upper band (sell)
        # Normalize within [-0.5, 1.5] range
        normalized_buy = 1.0 - self._normalize(pct_b, -0.5, 1.5)

        if pct_b < 0.0:
            signal = "BUY"
            conf = 0.8
        elif pct_b < 0.2:
            signal = "BUY"
            conf = 0.55
        elif pct_b > 1.0:
            signal = "SELL"
            conf = 0.8
        elif pct_b > 0.8:
            signal = "SELL"
            conf = 0.55
        else:
            signal = "HOLD"
            conf = 0.3

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(pct_b, 4),
            normalized=round(normalized_buy, 4),
            signal=signal,
            confidence=conf,
            description=f"%B={pct_b:.3f} (lower={last_lower:.2f}, upper={last_upper:.2f})",
        )


class ZScoreFactor(Factor):
    name = "zscore"
    category = "mean_reversion"
    lookback_periods = 20
    expected_sign = "negative"
    description = "Z-score of price from rolling mean — statistical deviation measure"

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        closes = ohlcv["close"].astype(float)
        rolling_mean = closes.rolling(self.lookback_periods).mean()
        rolling_std = closes.rolling(self.lookback_periods).std()

        last_close = float(closes.iloc[-1])
        mean_val = float(rolling_mean.iloc[-1])
        std_val = float(rolling_std.iloc[-1])

        if std_val == 0:
            zscore = 0.0
        else:
            zscore = (last_close - mean_val) / std_val

        # Z-score: negative = below mean (buy), positive = above mean (sell)
        # Map z in [-3, 3] to [0, 1], then invert for buy signal
        norm = self._normalize(zscore, -3.0, 3.0)
        buy_norm = 1.0 - norm

        if zscore < -2.0:
            signal = "BUY"
            conf = 0.8
        elif zscore < -1.0:
            signal = "BUY"
            conf = 0.6
        elif zscore > 2.0:
            signal = "SELL"
            conf = 0.8
        elif zscore > 1.0:
            signal = "SELL"
            conf = 0.6
        else:
            signal = "HOLD"
            conf = 0.3

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(zscore, 4),
            normalized=round(buy_norm, 4),
            signal=signal,
            confidence=conf,
            description=f"Z-score={zscore:.3f} (mean={mean_val:.2f}, std={std_val:.2f})",
        )
