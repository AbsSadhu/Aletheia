"""
Factor base class and output model.

All factors inherit from Factor and implement compute(ohlcv).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field


class FactorOutput(BaseModel):
    """Standardized output from any factor computation."""

    name: str
    category: str
    value: float = Field(..., description="Raw factor value (e.g. RSI=65.2)")
    normalized: float = Field(
        0.5, ge=0.0, le=1.0, description="Normalized 0–1 value (0=extreme sell, 1=extreme buy)"
    )
    signal: Literal["BUY", "HOLD", "SELL"] = "HOLD"
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    description: str = ""


class Factor(ABC):
    """Abstract base class for all alpha factors."""

    name: str
    category: str
    lookback_periods: int
    expected_sign: Literal["positive", "negative", "neutral"] = "neutral"
    description: str = ""

    @abstractmethod
    def compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        """
        Compute the factor from OHLCV data.

        Parameters
        ----------
        ohlcv : pd.DataFrame
            DataFrame with columns: open, high, low, close, volume
            Index should be DatetimeIndex, sorted ascending.

        Returns
        -------
        FactorOutput
        """
        ...

    def safe_compute(self, ohlcv: pd.DataFrame) -> FactorOutput:
        """Wrapper that catches errors and returns HOLD/0.5 on failure."""
        try:
            if ohlcv is None or len(ohlcv) < self.lookback_periods:
                return FactorOutput(
                    name=self.name,
                    category=self.category,
                    value=float("nan"),
                    normalized=0.5,
                    signal="HOLD",
                    confidence=0.0,
                    description=f"Insufficient data (need {self.lookback_periods} bars)",
                )
            return self.compute(ohlcv)
        except Exception as exc:  # noqa: BLE001
            return FactorOutput(
                name=self.name,
                category=self.category,
                value=float("nan"),
                normalized=0.5,
                signal="HOLD",
                confidence=0.0,
                description=f"Computation error: {exc}",
            )

    @staticmethod
    def _normalize(value: float, low: float, high: float) -> float:
        """Map value from [low, high] → [0, 1] with clamping."""
        if high == low:
            return 0.5
        return max(0.0, min(1.0, (value - low) / (high - low)))

    @staticmethod
    def _signal_from_normalized(
        norm: float, buy_thresh: float = 0.65, sell_thresh: float = 0.35
    ) -> Literal["BUY", "HOLD", "SELL"]:
        if norm >= buy_thresh:
            return "BUY"
        if norm <= sell_thresh:
            return "SELL"
        return "HOLD"
