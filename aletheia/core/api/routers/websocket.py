"""Live run-event and market-feed WebSocket streams.

  WS /ws/runs/{run_id}
  WS /ws/market

Included in main.py WITHOUT the router-level X-API-Key dependency, because
FastAPI resolves HTTP-typed dependencies against a WebSocket connection
incorrectly (the handler never even reaches the accept() call), and browsers
can't send custom headers on a WebSocket handshake anyway. Auth is checked
manually inside the handler via a `?api_key=` query param instead.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from aletheia.core.api.dependencies import get_run_service
from aletheia.core.api.security import is_authorized
from aletheia.core.events.bus import Event, Topics, get_event_bus
from aletheia.core.models import RunStatus

router = APIRouter(prefix="/api/v1")


@router.websocket("/ws/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    if not is_authorized(websocket.query_params.get("api_key")):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    service = get_run_service()

    # Send all cached events
    for event in service.get_events(run_id):
        await websocket.send_json(event.model_dump(mode="json"))

    # Check if already completed
    run = service.get_run(run_id)
    if run and run.summary.status in (RunStatus.COMPLETED, RunStatus.FAILED):
        await websocket.send_json({"run_id": run_id, "message": "stream_complete"})
        await websocket.close()
        return

    # Register for live broadcasts
    service.register_socket(run_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
    finally:
        service.unregister_socket(run_id, websocket)


@router.websocket("/ws/market")
async def market_feed(websocket: WebSocket) -> None:
    if not is_authorized(websocket.query_params.get("api_key")):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    bus = get_event_bus()

    async def forward(event: Event) -> None:
        try:
            await websocket.send_json(
                {
                    "topic": event.topic,
                    "payload": event.payload,
                    "timestamp": event.timestamp.isoformat(),
                }
            )
        except Exception:
            pass

    bus.subscribe(Topics.MARKET_QUOTE, forward)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
    finally:
        bus.unsubscribe(Topics.MARKET_QUOTE, forward)
