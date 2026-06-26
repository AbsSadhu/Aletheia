from typing import Any, ClassVar
from aletheia.core.tools.registry import BaseTool


class BacktestTool(BaseTool):
    """Runs a backtest for a strategy."""

    name: ClassVar[str] = "backtest"
    description: ClassVar[str] = "Run a strategy backtest against historical data."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "strategy_name": {
                "type": "string",
                "description": "Name of the strategy.",
            },
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Symbols to test against.",
            },
        },
        "required": ["strategy_name", "symbols"],
    }

    async def execute(self, strategy_name: str, symbols: list[str], **kwargs) -> Any:
        return {
            "strategy_name": strategy_name,
            "status": "mock",
            "message": "Backtest runner pending implementation.",
        }
