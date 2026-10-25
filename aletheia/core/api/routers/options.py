"""Options pricing (Black-Scholes + Greeks).

GET /options/price?spot=&strike=&days=&rate_pct=&vol_pct=&kind=call|put
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
