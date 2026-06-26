import yfinance as yf
from typing import Any, ClassVar
from aletheia.core.tools.registry import BaseTool


class MarketDataTool(BaseTool):
    """Fetches market quotes and historical OHLCV data for a ticker symbol."""

    name: ClassVar[str] = "market_data"
    description: ClassVar[str] = (
        "Fetch market quotes and historical OHLCV data for a given ticker symbol."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "The stock ticker symbol (e.g., AAPL, RELIANCE.NS).",
            },
            "period": {
                "type": "string",
                "description": "The time period to fetch (e.g., 1d, 5d, 1mo, 1y). Default is 1mo.",
                "default": "1mo",
            },
        },
        "required": ["symbol"],
    }

    async def execute(self, symbol: str, period: str = "1mo", **kwargs) -> Any:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            if hist.empty:
                return {"error": f"No market data found for symbol: {symbol}"}

            # Convert to a simple dict list
            records = []
            for date, row in hist.iterrows():
                records.append(
                    {
                        "date": date.strftime("%Y-%m-%d"),
                        "open": round(row["Open"], 2),
                        "high": round(row["High"], 2),
                        "low": round(row["Low"], 2),
                        "close": round(row["Close"], 2),
                        "volume": int(row["Volume"]),
                    }
                )

            info = ticker.info
            current_price = info.get("currentPrice", records[-1]["close"])

            return {
                "symbol": symbol,
                "current_price": current_price,
                "period": period,
                "history": records,
            }
        except Exception as e:
            return {"error": str(e)}
