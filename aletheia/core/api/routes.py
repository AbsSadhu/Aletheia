"""
FastAPI routes for the Aletheia API v1.

Endpoints:
  Core:
    GET  /health
    GET  /health/ready
    POST /runs
    GET  /runs
    GET  /runs/{run_id}
    GET  /runs/{run_id}/events
    WS   /ws/runs/{run_id}
    POST /portfolio-analysis

  Portfolios:
    GET    /portfolios
    GET    /portfolios/{name}
    POST   /portfolios
    DELETE /portfolios/{name}

  Backtest:
    POST /backtest
    GET  /backtest/{backtest_id}

  Hypotheses:
    GET   /hypotheses
    POST  /hypotheses
    GET   /hypotheses/{id}
    PATCH /hypotheses/{id}/transition
    POST  /hypotheses/{id}/evidence

  Memory:
    GET  /memory/search

  Chat:
    POST /chat/stream
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Request,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aletheia.core.api.dependencies import get_run_service
from aletheia.core.config.settings import get_settings
from aletheia.core.models import HealthResponse, Portfolio, RunRequest, RunStatus, RunSummary
from aletheia.core.agent.loop import ReActLoop
from aletheia.core.agent.context import AgentContext
from aletheia.core.llm.chat_llm import build_llm_router
from aletheia.core.tools.registry import build_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Portfolios
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    strategy: str = "oracle_signals"
    initial_capital: float = 100_000.0


@router.post("/backtest")
async def run_backtest(request: BacktestRequest) -> dict:
    """
    Fetch historical data and run an event-driven backtest.
    Returns BacktestResult with metrics and equity curve.
    """
    from aletheia.extensions.backtest.data_feed import HistoricalDataFeed
    from aletheia.extensions.backtest.runner import BacktestRunner

    settings = get_settings()
    feed = HistoricalDataFeed(duckdb_path=settings.duckdb_path)
    runner = BacktestRunner(initial_capital=request.initial_capital)

    # Fetch data for all symbols
    fetch_tasks = [
        feed.fetch_and_store(sym, request.start_date, request.end_date)
        for sym in request.symbols
    ]
    try:
        await asyncio.gather(*fetch_tasks)
    except Exception as exc:
        logger.error("Backtest data fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}")

    # Build per-date market snapshot and drive backtest
    all_candles: dict[str, Any] = {}
    for sym in request.symbols:
        candles = feed.get_candles(sym, request.start_date, request.end_date)
        all_candles[sym] = candles

    # Drive event loop: for each trading day across all symbols
    date_set: set[str] = set()
    for candles in all_candles.values():
        for c in candles:
            date_set.add(c.date)

    for trading_date in sorted(date_set):
        day_data: dict[str, dict] = {}
        for sym, candles in all_candles.items():
            candle = next((c for c in candles if c.date == trading_date), None)
            if candle:
                day_data[sym] = {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
        runner.execute_orders(day_data)
        runner.update_equity(day_data)

    result = runner.generate_report(
        strategy_name=request.strategy,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------

class ProposeHypothesisRequest(BaseModel):
    title: str
    description: str
    test_criteria: str


class TransitionRequest(BaseModel):
    new_status: str


class AddEvidenceRequest(BaseModel):
    source: str
    summary: str
    supports: bool


def _get_hypothesis_registry():
    settings = get_settings()
    from aletheia.extensions.hypotheses.registry import HypothesisRegistry
    return HypothesisRegistry(db_path=str(settings.data_dir / "hypotheses.db"))


@router.get("/hypotheses")
async def list_hypotheses(status: str | None = None) -> dict:
    reg = _get_hypothesis_registry()
    items = reg.list_all(status=status)
    return {"hypotheses": [h.model_dump(mode="json") for h in items]}


@router.post("/hypotheses", status_code=201)
async def propose_hypothesis(request: ProposeHypothesisRequest) -> dict:
    reg = _get_hypothesis_registry()
    hypo = reg.propose(
        title=request.title,
        description=request.description,
        test_criteria=request.test_criteria,
    )
    return hypo.model_dump(mode="json")


@router.get("/hypotheses/{hypo_id}")
async def get_hypothesis(hypo_id: str) -> dict:
    reg = _get_hypothesis_registry()
    hypo = reg.get(hypo_id)
    if hypo is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return hypo.model_dump(mode="json")


@router.patch("/hypotheses/{hypo_id}/transition")
async def transition_hypothesis(hypo_id: str, request: TransitionRequest) -> dict:
    reg = _get_hypothesis_registry()
    try:
        hypo = reg.transition(hypo_id, request.new_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return hypo.model_dump(mode="json")


@router.post("/hypotheses/{hypo_id}/evidence")
async def add_hypothesis_evidence(hypo_id: str, request: AddEvidenceRequest) -> dict:
    reg = _get_hypothesis_registry()
    try:
        hypo = reg.add_evidence(
            hypo_id=hypo_id,
            source=request.source,
            summary=request.summary,
            supports=request.supports,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return hypo.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Memory Search
# ---------------------------------------------------------------------------

@router.get("/memory/search")
async def memory_search(q: str, limit: int = 8) -> dict:
    """
    Semantic search over episodic run history and semantic memory files.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query 'q' is required")

    settings = get_settings()
    from aletheia.core.memory.persistent import PersistentMemory
    memory = PersistentMemory(memory_dir=settings.memory_dir)
    results = memory.search(q, limit=limit)
    return results


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Chat Stream (upgraded to use LLM router)
# ---------------------------------------------------------------------------

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
