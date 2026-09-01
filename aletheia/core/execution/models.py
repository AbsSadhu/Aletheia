from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    SIMULATION = "simulation"
    PAPER = "paper"
    LIVE = "live"


class OrderRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    side: str
    quantity: float = Field(..., gt=0)
    order_type: str = "MARKET"
    limit_price: float | None = None


class PaperTradeResult(BaseModel):
    trade_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str | None = None
    symbol: str
    exchange: str
    side: str
    recommendation: str
    simulated_qty: float
    simulated_fill_price: float
    simulated_pnl: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "filled"


class PaperPosition(BaseModel):
    symbol: str
    exchange: str
    quantity: float
    average_price: float
    realized_pnl: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionState(BaseModel):
    mode: ExecutionMode = ExecutionMode.SIMULATION
    paused: bool = False
    observation_days_required: int = 7
    live_approved_at: datetime | None = None
