import importlib
import logging
import pkgutil
from collections import deque
from pathlib import Path
from typing import Any, ClassVar


logger = logging.getLogger(__name__)


class BaseTool:
    """Base class for all tools."""

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    parameters: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    @classmethod
    def check_available(cls) -> bool:
        """Check if the tool's dependencies are available."""
        return True

    async def execute(self, **kwargs) -> Any:
        """Execute the tool with the given parameters."""
        raise NotImplementedError

    def get_definition(self) -> dict[str, Any]:
        """Get the OpenAI function calling definition for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry for managing and discovering tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} is already registered. Overwriting.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_definitions(self) -> list[dict[str, Any]]:
        return [tool.get_definition() for tool in self._tools.values()]


_SUBCLASSES_CACHE: list[type[BaseTool]] | None = None


def _discover_subclasses() -> list[type[BaseTool]]:
    """Import all modules in this package, then collect BaseTool subclasses."""
    global _SUBCLASSES_CACHE
    if _SUBCLASSES_CACHE is not None:
        return _SUBCLASSES_CACHE

    pkg_dir = str(Path(__file__).parent)
    for _, module_name, _ in pkgutil.iter_modules([pkg_dir]):
        if module_name.startswith("_"):
            continue
        try:
            importlib.import_module(f"aletheia.core.tools.{module_name}")
        except Exception as exc:
            logger.warning("Skipped aletheia.core.tools.%s: %s", module_name, exc)

    classes: list[type[BaseTool]] = []
    queue = deque(BaseTool.__subclasses__())
    while queue:
        cls = queue.popleft()
        if cls.name:
            classes.append(cls)
        queue.extend(cls.__subclasses__())

    _SUBCLASSES_CACHE = classes
    return classes


def build_registry() -> ToolRegistry:
    """Build the tool registry via auto-discovery."""
    registry = ToolRegistry()
    for cls in _discover_subclasses():
        try:
            if not cls.check_available():
                logger.info("Tool %s unavailable, skipping", cls.name)
                continue
            registry.register(cls())
        except Exception as exc:
            logger.warning("Failed to register tool %s: %s", cls.name, exc)

    return registry
