from typing import Any, ClassVar
from aletheia.core.tools.registry import BaseTool

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None


class WebSearchTool(BaseTool):
    """Searches the web for recent information."""

    name: ClassVar[str] = "web_search"
    description: ClassVar[str] = (
        "Search the web for up-to-date information, news, or general queries."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return.",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> Any:
        if DDGS is None:
            return {"error": "duckduckgo_search package is not installed."}

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            return {"query": query, "results": results}
        except Exception as e:
            return {"error": str(e)}
