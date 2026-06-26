from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Request,
)
from fastapi.responses import StreamingResponse

from aletheia.core.api.dependencies import get_run_service
from aletheia.core.config.settings import get_settings
from aletheia.core.models import HealthResponse, Portfolio, RunRequest, RunStatus, RunSummary
from aletheia.core.agent.loop import ReActLoop
from aletheia.core.agent.context import AgentContext
from aletheia.core.llm.chat_llm import OllamaChatLLM
from aletheia.core.tools.registry import build_registry

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        sqlite_path=str(settings.sqlite_path),
        duckdb_path=str(settings.duckdb_path),
    )


@router.get("/health/ready")
async def ready() -> dict[str, bool]:
    return {"ready": True}


@router.post("/runs")
async def create_run(
    request: RunRequest, background_tasks: BackgroundTasks, background: bool = False
) -> dict:
    service = get_run_service()
    if background:
        summary = RunSummary(prompt=request.prompt, status=RunStatus.PENDING)
        service.sqlite_store.upsert_run(summary)
        background_tasks.add_task(service.execute_run, summary, request)
        return {"summary": summary.model_dump(mode="json")}
    else:
        result = await service.create_run(request)
        return result.model_dump(mode="json")


@router.post("/portfolio-analysis")
async def portfolio_analysis(portfolio: Portfolio) -> dict:
    service = get_run_service()
    result = await service.create_run(
        RunRequest(
            prompt=f"Analyze portfolio {portfolio.name}",
            portfolio=portfolio,
        )
    )
    return result.model_dump(mode="json")


@router.get("/runs")
async def list_runs(limit: int = 20) -> dict:
    service = get_run_service()
    runs = service.list_runs(limit=limit)
    return {"runs": [run.model_dump(mode="json") for run in runs]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    service = get_run_service()
    result = service.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result.model_dump(mode="json")


@router.get("/runs/{run_id}/events")
async def get_run_events(run_id: str) -> dict:
    service = get_run_service()
    events = service.get_events(run_id)
    return {"events": [event.model_dump(mode="json") for event in events]}


@router.get("/portfolios")
async def list_portfolios() -> dict:
    service = get_run_service()
    portfolios = service.sqlite_store.list_portfolios()
    return {"portfolios": [p.model_dump(mode="json") for p in portfolios]}


@router.get("/portfolios/{name}")
async def get_portfolio(name: str) -> dict:
    service = get_run_service()
    portfolio = service.sqlite_store.get_portfolio(name)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio.model_dump(mode="json")


@router.post("/portfolios")
async def save_portfolio(portfolio: Portfolio) -> dict:
    service = get_run_service()
    service.sqlite_store.save_portfolio(portfolio)
    return portfolio.model_dump(mode="json")


@router.delete("/portfolios/{name}")
async def delete_portfolio(name: str) -> dict:
    service = get_run_service()
    deleted = service.sqlite_store.delete_portfolio(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return {"status": "success", "message": f"Portfolio {name} deleted"}


@router.websocket("/ws/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: str) -> None:
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


@router.post("/chat/stream")
async def chat_stream(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")

    async def event_generator():
        llm = OllamaChatLLM()
        registry = build_registry()
        loop = ReActLoop(llm=llm, tool_registry=registry)
        context = AgentContext()

        async for event in loop.run(prompt, context):
            yield event.to_sse()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
