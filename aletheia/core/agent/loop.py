import json
import logging
import time
from typing import AsyncGenerator
from aletheia.core.llm.chat_llm import ChatLLM
from aletheia.core.tools.registry import ToolRegistry, split_display
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

    def __init__(self, llm: ChatLLM, tool_registry: ToolRegistry, max_iterations: int = 15):
        self.llm = llm
        self.registry = tool_registry
        self.max_iterations = max_iterations

    @traceable(name="AletheiaReActLoop")
    async def run(
        self,
        user_prompt: str,
        context: AgentContext,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """`history` is prior user/assistant text turns, oldest first, for multi-turn chat."""
        system_prompt = context.build_system_prompt()
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user_prompt})

        tools = self.registry.get_definitions()

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            logger.info(f"ReAct Loop Iteration {iteration}")

            response = None
            try:
                stream = getattr(self.llm, "chat_stream", None)
                if stream is None:
                    response = await self.llm.chat(messages=messages, tools=tools)
                else:
                    # Text arrives as `token` events; the complete response comes last.
                    async for part in stream(messages=messages, tools=tools):
                        if isinstance(part, str):
                            yield StreamEvent("token", {"content": part})
                        else:
                            response = part
            except Exception as e:
                logger.error(f"LLM Chat Error: {e}")
                yield StreamEvent("error", {"message": f"LLM Error: {str(e) or type(e).__name__}"})
                break
            if response is None:
                yield StreamEvent("error", {"message": "LLM returned no response."})
                break

            msg = response.message

            if msg.content:
                if msg.tool_calls:
                    yield StreamEvent("thought", {"content": msg.content})
                else:
                    yield StreamEvent("final_answer", {"content": msg.content})
                    break

            if msg.tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [],
                }
                for tc in msg.tool_calls:
                    assistant_msg["tool_calls"].append(
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                    )
                messages.append(assistant_msg)

                for tc in msg.tool_calls:
                    tool_name = tc.name
                    args = tc.arguments

                    yield StreamEvent(
                        "tool_call", {"id": tc.id, "tool": tool_name, "arguments": args}
                    )

                    tool_start = time.monotonic()
                    tool = self.registry.get(tool_name)
                    if not tool:
                        result = f"Error: Tool '{tool_name}' not found."
                    else:
                        try:
                            result = await tool.execute(**args)
                        except Exception as e:
                            result = f"Error executing tool: {str(e)}"
                    latency_ms = round((time.monotonic() - tool_start) * 1000, 2)
                    # A tool may attach a `_display` payload (e.g. OHLCV bars for a chart). It
                    # goes to the UI but never to the model, whose context it would flood.
                    result, display = split_display(result)

                    event_data = {
                        "id": tc.id,
                        "tool": tool_name,
                        "result": result,
                        "latency_ms": latency_ms,
                        "result_size": len(str(result)),
                    }
                    if display is not None:
                        event_data["display"] = display
                    yield StreamEvent("tool_result", event_data)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "content": json.dumps(result, default=str),
                        }
                    )
            else:
                if not msg.content:
                    logger.warning("Empty response from LLM without tool calls.")
                    yield StreamEvent("error", {"message": "Received empty response from LLM."})
                break

        else:  # the loop ran out of iterations without any `break`
            yield StreamEvent(
                "error",
                {
                    "message": f"Max iterations ({self.max_iterations}) reached without a final answer."
                },
            )
