import json
import logging
from typing import List, Dict, Any, AsyncGenerator
from aletheia.core.llm.chat_llm import ChatLLM
from aletheia.core.tools.registry import ToolRegistry
from aletheia.core.agent.loop import ReActLoop
from aletheia.core.agent.context import AgentContext
from aletheia.core.agent.streaming import StreamEvent

logger = logging.getLogger(__name__)

class SwarmWorker:
    """An individual agent in a multi-agent swarm."""
    
    def __init__(self, name: str, role_description: str, llm: ChatLLM, tool_registry: ToolRegistry, allowed_tools: List[str] = None):
        self.name = name
        self.role_description = role_description
        self.llm = llm
        self.tool_registry = tool_registry
        self.allowed_tools = allowed_tools

    async def execute(self, prompt: str, portfolio=None) -> AsyncGenerator[StreamEvent, None]:
        # Filter the registry based on allowed_tools
        worker_registry = ToolRegistry()
        for t_name in (self.allowed_tools or []):
            tool = self.tool_registry.get(t_name)
            if tool:
                worker_registry.register(tool.__class__)
                
        # If no allowed tools, register them all
        if not self.allowed_tools:
            for t_def in self.tool_registry.get_definitions():
                tool = self.tool_registry.get(t_def["function"]["name"])
                worker_registry.register(tool.__class__)
        
        loop = ReActLoop(llm=self.llm, tool_registry=worker_registry)
        
        context = AgentContext(portfolio=portfolio)
        base_prompt = context.build_system_prompt()
        
        # Override the system prompt with the worker's specific role
        system_prompt = f"You are {self.name}, {self.role_description}.\n\n" + base_prompt
        
        # We need to hack the context to return our custom system prompt
        context.build_system_prompt = lambda: system_prompt
        
        async for event in loop.run(prompt, context):
            # Annotate events with the worker name
            event.data["worker"] = self.name
            yield event
