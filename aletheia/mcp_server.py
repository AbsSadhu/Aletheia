import json
import logging
from fastmcp import FastMCP
from aletheia.core.tools.registry import build_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Aletheia MCP Server",
    description="Aletheia Financial Intelligence multi-agent framework tools",
    dependencies=["fastmcp"],
)

registry = build_registry()


def _register_tools():
    for tool_def in registry.get_definitions():
        func_name = tool_def["function"]["name"]
        func_desc = tool_def["function"]["description"]

        # We need to create a wrapper function for FastMCP.
        # This is a bit tricky dynamically, but we can do it using closures.
        def make_wrapper(t_name):
            async def wrapper(**kwargs):
                tool = registry.get(t_name)
                try:
                    result = await tool.execute(**kwargs)
                    if isinstance(result, (dict, list)):
                        return json.dumps(result, indent=2)
                    return str(result)
                except Exception as e:
                    return f"Error executing tool {t_name}: {str(e)}"

            # FastMCP uses the function docstring and name
            wrapper.__name__ = t_name
            wrapper.__doc__ = func_desc
            return wrapper

        mcp.add_tool(make_wrapper(func_name))


# Register all tools dynamically
_register_tools()

if __name__ == "__main__":
    logger.info("Starting Aletheia MCP Server...")
    mcp.run()
