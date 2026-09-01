"""Run lifecycle, tracing, export, and compliance-log endpoints.

POST /runs
GET  /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/events
GET  /runs/{run_id}/trace
GET  /runs/{run_id}/export
GET  /runs/{run_id}/calibration
POST /portfolio-analysis
GET  /compliance/log
GET  /compliance/verify
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from aletheia.core.api.dependencies import get_run_service
from aletheia.core.api.security import portfolio_analysis_limiter, submit_run_limiter
from aletheia.core.models import Portfolio, RunRequest, RunStatus, RunSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.post("/runs", dependencies=[Depends(submit_run_limiter)])
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


@router.post("/portfolio-analysis", dependencies=[Depends(portfolio_analysis_limiter)])
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


@router.get("/runs/{run_id}/trace")
async def get_run_trace(run_id: str) -> dict:
    service = get_run_service()
    events = service.get_events(run_id)
    run_res = service.get_run(run_id)
    spans = run_res.traces if run_res else []
    return {
        "run_id": run_id,
        "trace": [event.model_dump(mode="json") for event in events],
        "spans": spans,
    }


@router.get("/runs/{run_id}/export")
async def export_run(run_id: str, format: str = "pdf") -> StreamingResponse:
    """
    Export an agent run as PDF or Excel.
    Query params:
        format=pdf   → returns application/pdf
        format=excel → returns application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
    """
    from aletheia.core.reporting.exporter import export_pdf, export_excel

    service = get_run_service()
    run_result = service.get_run(run_id)
    if run_result is None:
        raise HTTPException(status_code=404, detail="Run not found")

    run_dict = run_result.model_dump(mode="json")

    fmt = format.lower().strip()
    if fmt == "excel" or fmt == "xlsx":
        try:
            data = export_excel(run_dict)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Excel export failed: {exc}") from exc
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"aletheia_run_{run_id[:8]}.xlsx"
    else:
        # Default to PDF
        try:
            data = export_pdf(run_dict)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF export failed: {exc}") from exc
        # If WeasyPrint falls back to HTML, still serve it gracefully
        media_type = "application/pdf"
        filename = f"aletheia_run_{run_id[:8]}.pdf"

    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/calibration")
async def get_run_calibration(run_id: str) -> dict:
    service = get_run_service()
    with service.sqlite_store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM confidence_calibration WHERE run_id = ?", (run_id,)
        ).fetchall()
    return {"calibration": [dict(r) for r in rows]}


@router.get("/compliance/log")
async def get_compliance_log(
    from_date: str | None = None, to_date: str | None = None, limit: int = 100
) -> dict:
    service = get_run_service()
    log = service.sqlite_store.get_compliance_log(from_date=from_date, to_date=to_date, limit=limit)
    return {"log": log}


@router.get("/compliance/verify")
async def verify_compliance_log() -> dict:
    """Recompute and verify the compliance log's hash chain end-to-end."""
    service = get_run_service()
    return service.sqlite_store.verify_compliance_chain()
