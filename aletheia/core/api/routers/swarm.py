"""Multi-agent swarm endpoints.

GET  /swarm/presets
POST /swarm/run

Both preset teams (`aletheia.core.swarm.presets`) and the runtime that
executes them (`aletheia.core.swarm.runtime.SwarmRuntime`) existed before
this router — nothing anywhere called either one. This is what makes them
actually runnable, mirroring `/chat/stream`'s SSE pattern.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from aletheia.core.swarm.presets import available_presets, get_preset
from aletheia.core.swarm.runtime import SwarmRuntime

router = APIRouter(prefix="/api/v1")


@router.get("/swarm/presets")
async def list_swarm_presets() -> dict:
    return {"presets": available_presets()}


@router.post("/swarm/run")
async def run_swarm(request: Request) -> StreamingResponse:
    data = await request.json()
    preset_name = data.get("preset", "")
    prompt = data.get("prompt", "")
    portfolio_data = data.get("portfolio")

    try:
        workers = get_preset(preset_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    portfolio = None
    if portfolio_data:
        from aletheia.core.models import Portfolio

        try:
            portfolio = Portfolio(**portfolio_data)
        except Exception:
            portfolio = None

    async def event_generator() -> AsyncGenerator[str, None]:
        runtime = SwarmRuntime(workers)
        async for event in runtime.execute_parallel(prompt, portfolio):
            yield event.to_sse()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
