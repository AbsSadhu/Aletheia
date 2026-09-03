"""Streaming ReAct chat endpoint.

POST /chat/stream
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from aletheia.core.agent.context import AgentContext
from aletheia.core.agent.loop import ReActLoop
from aletheia.core.llm.chat_llm import build_llm_router
from aletheia.core.tools.registry import build_registry

router = APIRouter(prefix="/api/v1")


@router.post("/chat/stream")
async def chat_stream(request: Request) -> StreamingResponse:
    """
    Stream a ReAct agent response via SSE.
    Uses the multi-provider LLM router (Ollama → OpenAI → Anthropic).
    """
    data = await request.json()
    prompt = data.get("prompt", "")
    portfolio_data = data.get("portfolio")

    async def event_generator():
        llm = build_llm_router()
        registry = build_registry()
        loop = ReActLoop(llm=llm, tool_registry=registry)
        context = AgentContext()

        if portfolio_data:
            from aletheia.core.models import Portfolio

            try:
                portfolio = Portfolio(**portfolio_data)
                context.portfolio = portfolio
            except Exception:
                pass

        async for event in loop.run(prompt, context):
            yield event.to_sse()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
