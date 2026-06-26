from typing import Any
from aletheia.core.tools.registry import BaseTool
from aletheia.core.memory.persistent import PersistentMemory


class RememberTool(BaseTool):
    """Tool to read from and write to persistent agent memory."""

    name = "remember"
    description = "Store or recall persistent knowledge across sessions. Use this to remember user preferences, important facts, or past analysis."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["store", "recall", "search"],
                "description": "The action to perform: 'store' to save new memory, 'recall' to fetch by ID, 'search' to find by keyword.",
            },
            "memory_type": {
                "type": "string",
                "description": "Category of memory (e.g., 'preference', 'fact', 'analysis_result'). Required for store/recall.",
            },
            "content": {
                "type": "string",
                "description": "The information to store. Required for 'store'.",
            },
            "query": {
                "type": "string",
                "description": "The keyword or search term. Required for 'search'.",
            },
            "memory_id": {
                "type": "string",
                "description": "The specific memory ID to recall. Required for 'recall'.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, memory: PersistentMemory | None = None):
        self.memory = memory or PersistentMemory()

    async def execute(
        self,
        action: str,
        memory_type: str = None,
        content: str = None,
        query: str = None,
        memory_id: str = None,
        **kwargs,
    ) -> Any:
        try:
            if action == "store":
                if not memory_type or not content:
                    return "Error: 'memory_type' and 'content' are required for 'store' action."
                new_id = self.memory.store(memory_type, content, memory_id)
                return f"Successfully stored memory. ID: {new_id}"

            elif action == "recall":
                if not memory_type or not memory_id:
                    return "Error: 'memory_type' and 'memory_id' are required for 'recall' action."
                result = self.memory.recall(memory_type, memory_id)
                if result:
                    return result
                return f"No memory found for ID {memory_id} of type {memory_type}."

            elif action == "search":
                if not query:
                    return "Error: 'query' is required for 'search' action."
                results = self.memory.search(query)
                if results:
                    return results
                return f"No memories found matching '{query}'."

            else:
                return f"Error: Invalid action '{action}'."
        except Exception as e:
            return f"Error in remember tool: {str(e)}"
