"""Paper-trading execution and live-gate state endpoints.

POST /execution/paper-order
GET  /execution/paper-trades
GET  /execution/positions
GET  /execution/state
POST /execution/mode
POST /execution/pause
POST /execution/resume
POST /execution/paper-trades/{trade_id}/settle
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aletheia.core.api.dependencies import get_live_gate, get_paper_trader
from aletheia.core.execution.models import ExecutionMode, OrderRequest

router = APIRouter(prefix="/api/v1")


class ExecutionModeRequest(BaseModel):
    mode: ExecutionMode
    confirm: bool = False
    paper_observation_days: int = 0


@router.post("/execution/paper-order")
async def submit_paper_order(order: OrderRequest, run_id: str | None = None) -> dict:
    gate = get_live_gate()
    gate.assert_order_allowed()
    trader = get_paper_trader()
    result = await trader.submit_order(order, run_id=run_id)
    return {"trade": result.model_dump(mode="json")}


@router.get("/execution/paper-trades")
async def list_paper_trades(limit: int = 50) -> dict:
    trader = get_paper_trader()
    return {"trades": [trade.model_dump(mode="json") for trade in trader.list_trades(limit=limit)]}


@router.get("/execution/positions")
async def list_paper_positions() -> dict:
    trader = get_paper_trader()
    return {"positions": [position.model_dump(mode="json") for position in trader.list_positions()]}


@router.get("/execution/state")
async def get_execution_state() -> dict:
    return {"state": get_live_gate().get_state().model_dump(mode="json")}


@router.post("/execution/mode")
async def set_execution_mode(request: ExecutionModeRequest) -> dict:
    state = get_live_gate().set_mode(
        request.mode,
        confirm=request.confirm,
        paper_observation_days=request.paper_observation_days,
    )
    return {"state": state.model_dump(mode="json")}


@router.post("/execution/pause")
async def pause_execution() -> dict:
    return {"state": get_live_gate().pause().model_dump(mode="json")}


@router.post("/execution/resume")
async def resume_execution() -> dict:
    return {"state": get_live_gate().resume().model_dump(mode="json")}


@router.post("/execution/paper-trades/{trade_id}/settle")
async def settle_paper_trade(
    trade_id: str,
    actual_close: float,
) -> dict:
    """Settle a specific paper trade with an actual closing price."""
    trader = get_paper_trader()
    result = await trader.settle_trade(trade_id, actual_close)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    return {"trade": result.model_dump(mode="json")}
