from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import List, Optional

class TradeEntry(BaseModel):
    id: str
    symbol: str
    action: str  # buy or sell
    quantity: float
    price: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class VirtualPosition(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0

class AccountSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_equity: float
    cash_balance: float
    positions: List[VirtualPosition]
