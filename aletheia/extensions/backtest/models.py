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
    strategy_name: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    metrics: Dict[str, float]
    orders: List[Order]
    equity_curve: List[Dict[str, Any]]
