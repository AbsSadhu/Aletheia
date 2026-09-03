"""Shadow account (signal-driven virtual trading sandbox) endpoints.

GET  /shadow/positions
GET  /shadow/orders
POST /shadow/orders
GET  /shadow/performance
POST /shadow/scan
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aletheia.core.api.dependencies import (
    get_entry_exit_scanner,
    get_run_service,
    get_shadow_account,
)

router = APIRouter(prefix="/api/v1")


class ShadowOrderRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    action: str
    quantity: float = Field(default=1.0, gt=0)


@router.get("/shadow/positions")
async def shadow_positions() -> dict:
    account = get_shadow_account()
    return {"positions": [p.model_dump(mode="json") for p in account.list_positions()]}


@router.get("/shadow/orders")
async def shadow_orders(limit: int = 100) -> dict:
    account = get_shadow_account()
    return {"orders": [o.model_dump(mode="json") for o in account.list_orders(limit=limit)]}


@router.post("/shadow/orders")
async def submit_shadow_order(order: ShadowOrderRequest) -> dict:
    account = get_shadow_account()
    trade = await account.execute_virtual_order(
        order.symbol, order.exchange, order.action, order.quantity
    )
    return {"trade": trade.model_dump(mode="json")}


@router.get("/shadow/performance")
async def shadow_performance(limit: int = 200) -> dict:
    account = get_shadow_account()
    curve = account.equity_curve(limit=limit)
    return {
        "equity_curve": [s.model_dump(mode="json") for s in curve],
        "latest": curve[-1].model_dump(mode="json") if curve else None,
    }


@router.post("/shadow/scan")
async def shadow_scan(run_id: str) -> dict:
    run_service = get_run_service()
    run = run_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    scanner = get_entry_exit_scanner()
    executed = await scanner.scan(run.oracle_output)
    return {"executed": executed}
