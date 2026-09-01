"""Live run-event WebSocket stream.

  WS /ws/runs/{run_id}

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
