"""Health and metrics endpoints.

  GET /health
  GET /health/ready
  GET /health/details
  GET /metrics
"""

from __future__ import annotations

from fastapi import APIRouter

from aletheia.core.api.dependencies import get_container
from aletheia.core.config.settings import get_settings
from aletheia.core.models import HealthResponse

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
    health_registry = get_container().resolve("health")
    results = await health_registry.run_checks()
    return {"ready": all(item.ok for item in results)}


@router.get("/health/details")
async def health_details() -> dict:
    health_registry = get_container().resolve("health")
    results = await health_registry.run_checks()
    return {
        "checks": [
            {
                "name": item.name,
                "ok": item.ok,
                "details": item.details,
                "checked_at": item.checked_at,
            }
            for item in results
        ]
    }


@router.get("/metrics")
async def metrics_snapshot() -> dict:
    return get_container().resolve("metrics").snapshot()
