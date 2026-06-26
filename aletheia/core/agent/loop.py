import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
from aletheia.core.llm.chat_llm import ChatLLM
from aletheia.core.tools.registry import ToolRegistry
from aletheia.core.agent.context import AgentContext
from aletheia.core.agent.streaming import StreamEvent

logger = logging.getLogger(__name__)

try:
    from langsmith import traceable
except ImportError:
    # Dummy decorator if langsmith is not installed
    def traceable(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper

class ReActLoop:
    """Core Reasoning + Acting Loop."""
    
    def __init__(
        self, 
        llm: ChatLLM, 
        tool_registry: ToolRegistry,
        max_iterations: int = 15
    ):
        self.llm = llm
        self.registry = tool_registry
        self.max_iterations = max_iterations

    @traceable(name="AletheiaReActLoop")
    async def run(
        self, 
        user_prompt: str, 
        context: AgentContext
    ) -> AsyncGenerator[StreamEvent, None]:
        
        system_prompt = context.build_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        tools = self.registry.get_definitions()
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            
            logger.info(f"ReAct Loop Iteration {iteration}")
            
            try:
                response = await self.llm.chat(messages=messages, tools=tools)
            except Exception as e:
                logger.error(f"LLM Chat Error: {e}")
                yield StreamEvent("error", {"message": f"LLM Error: {str(e)}"})
                break
            
            msg = response.message
            
            # If the LLM returned text content, yield it as a thought or final answer
            if msg.content:
                if msg.tool_calls:
                    yield StreamEvent("thought", {"content": msg.content})
                else:
                    yield StreamEvent("final_answer", {"content": msg.content})
                    break
            
            # If there are tool calls, execute them
            if msg.tool_calls:
                # Add assistant message with tool calls to history
                assistant_msg = {"role": "assistant", "content": msg.content or "", "tool_calls": []}
                for tc in msg.tool_calls:
                    assistant_msg["tool_calls"].append({
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    })
                messages.append(assistant_msg)
                
                # Execute tools sequentially
                for tc in msg.tool_calls:
                    tool_name = tc.name
                    args = tc.arguments
                    
                    yield StreamEvent("tool_call", {"tool": tool_name, "arguments": args})
                    
                    tool = self.registry.get(tool_name)
                    if not tool:
                        result = f"Error: Tool '{tool_name}' not found."
                    else:
                        try:
                            # Using synchronous call for simplicity if not awaiting? 
                            # BaseTool.execute is async
                            result = await tool.execute(**args)
                        except Exception as e:
                            result = f"Error executing tool: {str(e)}"
                    
                    yield StreamEvent("tool_result", {"tool": tool_name, "result": result})
                    
                    # Add tool response to history
                    messages.append({
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(result)
                    })
            else:
                # No tool calls and no content? Break.
                if not msg.content:
                    logger.warning("Empty response from LLM without tool calls.")
                    yield StreamEvent("error", {"message": "Received empty response from LLM."})
                break
                
        if iteration >= self.max_iterations:
            yield StreamEvent("error", {"message": f"Max iterations ({self.max_iterations}) reached without a final answer."})
