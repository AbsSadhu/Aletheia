from typing import Any, ClassVar
from aletheia.core.tools.registry import BaseTool

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

class NewsSearchTool(BaseTool):
    """Searches for recent news."""

    name: ClassVar[str] = "news_search"
    description: ClassVar[str] = "Search for recent financial news related to a company or query."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (e.g. 'Apple news', 'RELIANCE earnings').",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of news results to return.",
                "default": 5,
            }
        },
        "required": ["query"],
    }

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> Any:
        if DDGS is None:
            return {"error": "duckduckgo_search package is not installed."}
        
        try:
            with DDGS() as ddgs:
                results = list(ddgs.news(query, max_results=max_results))
            return {"query": query, "results": results}
        except Exception as e:
            return {"error": str(e)}
