from typing import Any, ClassVar
from aletheia.core.tools.registry import BaseTool

class WebReaderTool(BaseTool):
    """Fetches text content from a URL."""

    name: ClassVar[str] = "web_reader"
    description: ClassVar[str] = "Fetch and extract text content from a given URL."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to read.",
            }
        },
        "required": ["url"],
    }

    async def execute(self, url: str, **kwargs) -> Any:
        return {
            "url": url,
            "status": "mock",
            "text": "Simulated extracted text content from URL."
        }
