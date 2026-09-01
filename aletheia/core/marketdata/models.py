from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from aletheia.core.models import MarketQuote


class MarketDataRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    provider: str | None = None


class Tick(BaseModel):
    symbol: str
    exchange: str
    price: float
    size: float = 0.0
    side: str = "unknown"
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str


class Candle(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    provider: str

    @classmethod
    def from_quote(cls, quote: MarketQuote, timeframe: str = "1d") -> "Candle":
        return cls(
            symbol=quote.symbol,
            exchange=quote.exchange,
            timeframe=timeframe,
            ts=quote.as_of,
            open=quote.open if quote.open is not None else quote.close,
            high=quote.high if quote.high is not None else quote.close,
            low=quote.low if quote.low is not None else quote.close,
            close=quote.close,
            volume=quote.volume or 0.0,
            provider=quote.provider,
        )


class OrderBookLevel(BaseModel):
    price: float
    size: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    exchange: str
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
