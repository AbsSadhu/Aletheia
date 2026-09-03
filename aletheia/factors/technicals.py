"""
Technical factors: MA crossovers, Pivot-based support/resistance.
"""

from __future__ import annotations

import pandas as pd

from aletheia.factors._base import Factor, FactorOutput


class MACrossFactor(Factor):
    name = "ma_cross"
    category = "technicals"
    lookback_periods = 50
    expected_sign = "positive"
    description = "Fast/Slow SMA crossover — golden cross / death cross signal"
    fast_period: int = 20
    slow_period: int = 50

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        closes = ohlcv["close"].astype(float)
        sma_fast = closes.rolling(self.fast_period).mean()
        sma_slow = closes.rolling(self.slow_period).mean()

        last_fast = float(sma_fast.iloc[-1])
        last_slow = float(sma_slow.iloc[-1])
        prev_fast = float(sma_fast.iloc[-2]) if len(sma_fast) > 1 else last_fast
        prev_slow = float(sma_slow.iloc[-2]) if len(sma_slow) > 1 else last_slow

        spread_pct = (last_fast - last_slow) / last_slow * 100 if last_slow != 0 else 0.0
        norm = self._normalize(spread_pct, -5.0, 5.0)

        # Golden cross: fast crosses above slow
        just_crossed_up = prev_fast <= prev_slow and last_fast > last_slow
        just_crossed_down = prev_fast >= prev_slow and last_fast < last_slow

        if just_crossed_up:
            signal = "BUY"
            conf = 0.85
        elif just_crossed_down:
            signal = "SELL"
            conf = 0.85
        elif last_fast > last_slow:
            signal = "BUY"
            conf = 0.5 + min(0.3, abs(spread_pct) / 5 * 0.3)
        elif last_fast < last_slow:
            signal = "SELL"
            conf = 0.5 + min(0.3, abs(spread_pct) / 5 * 0.3)
        else:
            signal = "HOLD"
            conf = 0.3

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(spread_pct, 3),
            normalized=round(norm, 4),
            signal=signal,
            confidence=round(conf, 3),
            description=f"SMA{self.fast_period}={last_fast:.2f} vs SMA{self.slow_period}={last_slow:.2f} "
            f"(spread={spread_pct:+.2f}%)"
            + (
                " [GOLDEN CROSS]"
                if just_crossed_up
                else " [DEATH CROSS]"
                if just_crossed_down
                else ""
            ),
        )


class PivotSupportFactor(Factor):
    name = "pivot_support"
    category = "technicals"
    lookback_periods = 1
    expected_sign = "neutral"
    description = "Classic pivot point analysis — support/resistance proximity"

    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        # Use previous bar for pivot calculation
        if len(ohlcv) < 2:
            return FactorOutput(
                name=self.name,
                category=self.category,
                value=0.0,
                normalized=0.5,
                signal="HOLD",
                confidence=0.0,
                description="Insufficient data for pivot calculation",
            )

        prev = ohlcv.iloc[-2]
        high = float(prev["high"])
        low = float(prev["low"])
        close_prev = float(prev["close"])

        pivot = (high + low + close_prev) / 3
        r1 = 2 * pivot - low
        s1 = 2 * pivot - high

        last_close = float(ohlcv["close"].iloc[-1])

        # Position relative to pivot/S1/R1
        if last_close < s1:
            # Below S1 — possible bounce or breakdown
            pct_from_s1 = (s1 - last_close) / s1 * 100
            signal = "BUY"
            conf = min(0.75, 0.5 + pct_from_s1 / 2 * 0.25)
            norm = self._normalize(-pct_from_s1, -5, 0)
            desc = f"Below S1={s1:.2f} ({pct_from_s1:.2f}% below)"
        elif last_close > r1:
            # Above R1 — breakout or mean reversion
            pct_from_r1 = (last_close - r1) / r1 * 100
            signal = "SELL"
            conf = min(0.75, 0.5 + pct_from_r1 / 2 * 0.25)
            norm = self._normalize(pct_from_r1, 0, 5)
            norm = 1.0 - norm
            desc = f"Above R1={r1:.2f} ({pct_from_r1:.2f}% above)"
        else:
            signal = "HOLD"
            conf = 0.3
            norm = 0.5
            desc = f"Between S1={s1:.2f} and R1={r1:.2f} (pivot={pivot:.2f})"

        return FactorOutput(
            name=self.name,
            category=self.category,
            value=round(pivot, 2),
            normalized=round(norm, 4),
            signal=signal,
            confidence=round(conf, 3),
            description=desc,
        )
