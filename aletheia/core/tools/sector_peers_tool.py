from typing import Any, ClassVar
from aletheia.core.tools.registry import BaseTool


class SectorPeersTool(BaseTool):
    """Finds sector peers for a given symbol."""

    name: ClassVar[str] = "sector_peers"
    is_stub: ClassVar[bool] = True  # returns placeholder data; hidden from the chat agent
    description: ClassVar[str] = "Find and compare sector peers for a given ticker symbol."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "The stock ticker symbol.",
            }
        },
        "required": ["symbol"],
    }

    async def execute(self, symbol: str, **kwargs) -> Any:
        return {"symbol": symbol, "status": "mock", "peers": ["MOCK_PEER_1", "MOCK_PEER_2"]}
