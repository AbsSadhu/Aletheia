"""Extended portfolio risk metrics endpoint.

GET /risk/metrics
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/risk/metrics")
async def get_portfolio_risk_metrics(run_id: str | None = None) -> dict:
    """Runs do not store an equity curve, so there is nothing to compute risk metrics from.

    Backtests report their own metrics (`POST /backtest`); the Sentinel's VaR is on each run result.
    """
    return {"metrics": None, "message": "No equity curve available. Run a backtest first."}
