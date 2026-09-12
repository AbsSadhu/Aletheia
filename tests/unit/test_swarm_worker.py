"""Regression test for a real bug: SwarmWorker.execute() filtered its tool
registry with `worker_registry.register(tool.__class__)` instead of
`register(tool)`, registering the class instead of the instance. Every call
to ToolRegistry.get_definitions() then called `tool.get_definition()`
unbound, raising "BaseTool.get_definition() missing 1 required positional
argument: 'self'" before the LLM was ever reached — undetected because
nothing in the codebase called SwarmWorker.execute() until the swarm API
router was added.
"""

from aletheia.core.swarm.worker import SwarmWorker
from aletheia.core.tools.registry import build_registry


class _FailingLLM:
    async def chat(self, messages, tools):
        raise RuntimeError("injected failure — LLM was reached")


async def test_execute_builds_tool_definitions_without_error() -> None:
    registry = build_registry()
    tool_names = [t.name for t in registry.list_tools()]
    assert tool_names, "test needs at least one real registered tool"

    worker = SwarmWorker(
        name="Test Analyst",
        role_description="a test worker",
        llm=_FailingLLM(),
        tool_registry=registry,
        allowed_tools=tool_names[:1],
    )

    events = [event async for event in worker.execute("test prompt")]

    # Getting the injected RuntimeError back (surfaced as an "error" event by
    # ReActLoop) proves get_definitions() succeeded and the LLM was actually
    # reached — the bug this guards against never got that far.
    assert events
    assert events[0].event_type == "error"
    assert "injected failure" in events[0].data["message"]


async def test_execute_with_no_allowed_tools_registers_all() -> None:
    registry = build_registry()
    worker = SwarmWorker(
        name="Test Analyst",
        role_description="a test worker",
        llm=_FailingLLM(),
        tool_registry=registry,
        allowed_tools=None,
    )

    events = [event async for event in worker.execute("test prompt")]

    assert events
    assert "injected failure" in events[0].data["message"]
