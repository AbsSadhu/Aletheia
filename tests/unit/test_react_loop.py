"""ReActLoop had zero test coverage before this file."""

from aletheia.core.agent.context import AgentContext
from aletheia.core.agent.loop import ReActLoop
from aletheia.core.llm.chat_llm import ChatMessage, ChatResponse, ToolCall
from aletheia.core.tools.registry import BaseTool, ToolRegistry


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes back its input."
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def execute(self, text: str) -> str:
        return f"echo: {text}"


class _ScriptedLLM:
    """Returns each response in `responses` in order, one per .chat() call."""

    def __init__(self, responses: list[ChatResponse]) -> None:
        self._responses = list(responses)

    async def chat(self, messages, tools):
        return self._responses.pop(0)


def _final_answer(text: str) -> ChatResponse:
    return ChatResponse(message=ChatMessage(role="assistant", content=text), finish_reason="stop")


def _tool_call_response(tool_name: str, arguments: dict) -> ChatResponse:
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="1", name=tool_name, arguments=arguments)],
        ),
        finish_reason="tool_calls",
    )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    return registry


async def test_loop_yields_final_answer_directly() -> None:
    llm = _ScriptedLLM([_final_answer("done")])
    loop = ReActLoop(llm=llm, tool_registry=_registry())

    events = [e async for e in loop.run("hello", AgentContext())]

    assert events[-1].event_type == "final_answer"
    assert events[-1].data["content"] == "done"


async def test_loop_executes_tool_call_then_final_answer() -> None:
    llm = _ScriptedLLM(
        [
            _tool_call_response("echo", {"text": "hi"}),
            _final_answer("wrapped up"),
        ]
    )
    loop = ReActLoop(llm=llm, tool_registry=_registry())

    events = [e async for e in loop.run("hello", AgentContext())]

    event_types = [e.event_type for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert event_types[-1] == "final_answer"

    tool_result = next(e for e in events if e.event_type == "tool_result")
    assert tool_result.data["result"] == "echo: hi"
    assert tool_result.data["latency_ms"] >= 0
    assert tool_result.data["result_size"] == len("echo: hi")


async def test_loop_reports_unknown_tool_without_crashing() -> None:
    llm = _ScriptedLLM(
        [
            _tool_call_response("does_not_exist", {}),
            _final_answer("recovered"),
        ]
    )
    loop = ReActLoop(llm=llm, tool_registry=_registry())

    events = [e async for e in loop.run("hello", AgentContext())]

    tool_result = next(e for e in events if e.event_type == "tool_result")
    assert "not found" in tool_result.data["result"]
    assert events[-1].event_type == "final_answer"


async def test_loop_emits_error_event_on_llm_exception() -> None:
    class _FailingLLM:
        async def chat(self, messages, tools):
            raise RuntimeError("connection refused")

    loop = ReActLoop(llm=_FailingLLM(), tool_registry=_registry())

    events = [e async for e in loop.run("hello", AgentContext())]

    assert len(events) == 1
    assert events[0].event_type == "error"
    assert "connection refused" in events[0].data["message"]
