import yfinance as yf
from typing import Any, ClassVar
from aletheia.core.tools.registry import BaseTool


class FundamentalDataTool(BaseTool):
    """Fetches fundamental data for a given ticker symbol."""

    name: ClassVar[str] = "fundamental_data"
    description: ClassVar[str] = (
        "Fetch fundamental financial data (P/E, EPS, Market Cap, etc.) for a given ticker symbol."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "The stock ticker symbol (e.g., AAPL, RELIANCE.NS).",
            }
        },
        "required": ["symbol"],
    }

    async def execute(self, symbol: str, **kwargs) -> Any:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "market_cap": info.get("marketCap"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "eps": info.get("trailingEps"),
                "dividend_yield": info.get("dividendYield"),
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "return_on_equity": info.get("returnOnEquity"),
                "debt_to_equity": info.get("debtToEquity"),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow"),
            }
        except Exception as e:
            return {"error": str(e)}
