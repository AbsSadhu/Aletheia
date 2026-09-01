"""
Execution Cost Realism for backtesting.

Models slippage, bid-ask spread, and latency to give realistic fills
instead of using last-bar close prices naively.
"""

from __future__ import annotations


from pydantic import BaseModel, Field


class ExecutionCosts(BaseModel):
    """Realistic execution cost model for a specific asset class."""
    asset_class: str = "equity_nse"
    slippage_bps: float = Field(3.0, ge=0.0, description="Slippage in basis points")
    bid_ask_spread_bps: float = Field(1.0, ge=0.0, description="Half-spread in basis points")
    latency_ms: float = Field(50.0, ge=0.0, description="Order submission latency in milliseconds")
    commission_bps: float = Field(2.0, ge=0.0, description="Broker commission in basis points")

    @classmethod
    def for_asset_class(cls, asset_class: str) -> "ExecutionCosts":
        """Factory method with realistic presets per asset class."""
        presets = {
            "equity_nse": cls(
                asset_class="equity_nse",
                slippage_bps=3.0,
                bid_ask_spread_bps=1.0,
                latency_ms=50.0,
                commission_bps=2.0,
            ),
            "equity_bse": cls(
                asset_class="equity_bse",
                slippage_bps=4.0,
                bid_ask_spread_bps=2.0,
                latency_ms=80.0,
                commission_bps=2.0,
            ),
            "fno": cls(
                asset_class="fno",
                slippage_bps=5.0,
                bid_ask_spread_bps=1.5,
                latency_ms=30.0,
                commission_bps=1.0,
            ),
            "crypto": cls(
                asset_class="crypto",
                slippage_bps=10.0,
                bid_ask_spread_bps=5.0,
                latency_ms=200.0,
                commission_bps=10.0,  # 0.1% typical maker/taker
            ),
            "us_equity": cls(
                asset_class="us_equity",
                slippage_bps=2.0,
                bid_ask_spread_bps=0.5,
                latency_ms=10.0,
                commission_bps=0.5,
            ),
        }
        return presets.get(asset_class, presets["equity_nse"])

    def apply_to_buy(self, close_price: float) -> float:
        """Compute realistic fill price for a BUY order."""
        total_bps = self.slippage_bps + self.bid_ask_spread_bps + self.commission_bps
        return close_price * (1 + total_bps / 10_000)

    def apply_to_sell(self, close_price: float) -> float:
        """Compute realistic fill price for a SELL order."""
        total_bps = self.slippage_bps + self.bid_ask_spread_bps + self.commission_bps
        return close_price * (1 - total_bps / 10_000)

    def total_round_trip_cost_bps(self) -> float:
        """Total cost for a buy + sell round trip in basis points."""
        return 2 * (self.slippage_bps + self.bid_ask_spread_bps + self.commission_bps)

    def latency_bars_delay(self, bar_duration_seconds: float = 86400.0) -> int:
        """
        How many bars to delay fill after signal.
        For daily bars, latency_ms < 1 day → 0 bar delay (next open fill).
        """
        latency_secs = self.latency_ms / 1000
        return int(latency_secs // bar_duration_seconds)
