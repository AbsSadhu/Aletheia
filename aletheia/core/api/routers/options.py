"""Options pricing (Black-Scholes + Greeks).

GET /options/price?spot=&strike=&days=&rate_pct=&vol_pct=&kind=call|put
GET /options/surface?...&metric=price|delta|gamma|theta|vega   (grid over spot x days to expiry)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from aletheia.core.compute.client import ComputeClient

router = APIRouter(prefix="/api/v1")


@router.get("/options/price")
async def price_option(
    spot: float = Query(..., gt=0),
    strike: float = Query(..., gt=0),
    days: float = Query(..., ge=0, le=3650, description="Calendar days to expiry"),
    rate_pct: float = Query(7.0, ge=0, le=100, description="Risk-free rate, % p.a."),
    vol_pct: float = Query(..., gt=0, le=500, description="Implied volatility, % p.a."),
    kind: Literal["call", "put"] = "call",
) -> dict:
    g = ComputeClient().options_pricing(
        spot, strike, days / 365.0, rate_pct / 100.0, vol_pct / 100.0, kind == "call"
    )
    return {
        "kind": kind,
        "price": round(g["price"], 4),
        "delta": round(g["delta"], 4),
        "gamma": round(g["gamma"], 6),
        "theta_per_day": round(g["theta"] / 365.0, 4),
        "vega_per_vol_point": round(g["vega"] / 100.0, 4),
        "intrinsic": round(
            max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0), 4
        ),
    }


Metric = Literal["price", "delta", "gamma", "theta", "vega"]

# Same unit conventions as /options/price: theta per calendar day, vega per vol point.
_METRIC_SCALE = {"price": 1.0, "delta": 1.0, "gamma": 1.0, "theta": 1 / 365.0, "vega": 1 / 100.0}
_METRIC_KEY = {
    "price": "price",
    "delta": "delta",
    "gamma": "gamma",
    "theta": "theta",
    "vega": "vega",
}


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


@router.get("/options/surface")
async def option_surface(
    spot: float = Query(..., gt=0),
    strike: float = Query(..., gt=0),
    rate_pct: float = Query(7.0, ge=0, le=100),
    vol_pct: float = Query(..., gt=0, le=500),
    kind: Literal["call", "put"] = "call",
    metric: Metric = "price",
    max_days: float = Query(90.0, ge=2, le=730, description="Furthest expiry on the grid"),
    spot_range_pct: float = Query(40.0, gt=0, lt=95, description="Spot span, +/- % around spot"),
    spot_points: int = Query(41, ge=5, le=101),
    day_points: int = Query(31, ge=5, le=101),
) -> dict:
    """A metric over a grid of spot price x days to expiry, from the same pricer as /options/price.

    `values[i][j]` is the metric at `days[i]` and `spots[j]`.
    """
    client = ComputeClient()
    spots = _linspace(
        spot * (1 - spot_range_pct / 100), spot * (1 + spot_range_pct / 100), spot_points
    )
    days = _linspace(1.0, max_days, day_points)
    key, scale = _METRIC_KEY[metric], _METRIC_SCALE[metric]
    is_call = kind == "call"
    rate, vol = rate_pct / 100.0, vol_pct / 100.0
    values = [
        [
            round(client.options_pricing(s, strike, d / 365.0, rate, vol, is_call)[key] * scale, 6)
            for s in spots
        ]
        for d in days
    ]
    flat = [v for row in values for v in row]
    return {
        "metric": metric,
        "kind": kind,
        "strike": strike,
        "spots": [round(x, 4) for x in spots],
        "days": [round(x, 3) for x in days],
        "values": values,
        "min": min(flat),
        "max": max(flat),
    }
