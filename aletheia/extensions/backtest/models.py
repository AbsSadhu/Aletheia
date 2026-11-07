from datetime import datetime, UTC
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class Order(BaseModel):
    id: str
    symbol: str
    order_type: str  # market, limit, stop
    action: str  # buy, sell
    quantity: float
    price: Optional[float] = None
    status: str = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    filled_at: Optional[datetime] = None
    filled_price: Optional[float] = None


class Position(BaseModel):
    symbol: str
    quantity: float
    average_entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0


class BacktestResult(BaseModel):
    run_id: str
    strategy_name: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    # None means undefined (profit factor with no losing trade), never infinity: JSON cannot carry it.
    metrics: Dict[str, Optional[float]]
    orders: List[Order]
    equity_curve: List[Dict[str, Any]]
    # Honesty fields: what the run assumed and what it could not see.
    costs_paid: float = 0.0
    cost_model: Optional[str] = None
    data_as_of: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    # Earlier vs later part of the run, so a result that only holds in one stretch shows up.
    segments: List[Dict[str, Any]] = Field(default_factory=list)
