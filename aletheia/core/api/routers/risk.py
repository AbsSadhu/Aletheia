"""Extended portfolio risk metrics endpoint.

GET /risk/metrics
"""

from __future__ import annotations

from fastapi import APIRouter

from aletheia.core.api.dependencies import get_run_service
from aletheia.core.models import RunStatus

router = APIRouter(prefix="/api/v1")


@router.get("/risk/metrics")
async def get_portfolio_risk_metrics(
    run_id: str | None = None,
) -> dict:
    """
    Return extended risk metrics for the most recent backtest or current portfolio.
    """
    from aletheia.core.risk.metrics import compute_full_risk_metrics
    import pandas as pd

    service = get_run_service()

    # Try to get returns from the most recent completed run's backtest
    runs = service.list_runs(limit=10)
    completed = [r for r in runs if r.status == RunStatus.COMPLETED]

    if not completed:
        return {"metrics": None, "message": "No completed runs found to compute risk metrics."}

    target_run = completed[0]
    run_result = service.get_run(target_run.run_id)

    # Placeholder: generate synthetic returns from equity curve if available
    # In production, this would come from the backtest equity curve
    if run_result and hasattr(run_result, "equity_curve") and run_result.equity_curve:
        equity = pd.Series(run_result.equity_curve)
        returns = equity.pct_change().dropna()
    else:
        # Return empty metrics rather than fake data
        return {"metrics": None, "message": "No equity curve available. Run a backtest first."}

    metrics = compute_full_risk_metrics(returns)
    return {"metrics": metrics.model_dump(), "run_id": target_run.run_id}
