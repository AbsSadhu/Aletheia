from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse, Response
import sqlite3
import duckdb
import os
import sys
import httpx
import logging

from aletheia.core.api.routes import router, ws_router
from aletheia.core.api.security import verify_api_key
from aletheia.core.api.dependencies import get_container
from aletheia.core.config.settings import get_settings
from aletheia.core.infrastructure.logging import configure_logging

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
        REGISTRY as _DEFAULT_REGISTRY,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)


def run_preflight_checks(settings) -> None:
    # Skip preflight checks during tests or when explicitly bypassed
    if os.getenv("ALETHEIA_SKIP_PREFLIGHT") == "true" or "pytest" in sys.modules:
        return

    # 1. Verify SQLite is reachable
    try:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(settings.sqlite_path) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        raise RuntimeError(
            f"Preflight Check Failed: SQLite database is not reachable at {settings.sqlite_path}. "
            f"Error: {exc}"
        ) from exc

    # 2. Verify DuckDB is reachable
    try:
        settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        config = {}
        if settings.db_encryption_key:
            config["encryption_key"] = settings.db_encryption_key
        with duckdb.connect(str(settings.duckdb_path), config=config) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        raise RuntimeError(
            f"Preflight Check Failed: DuckDB database is not reachable at {settings.duckdb_path}. "
            f"Error: {exc}"
        ) from exc

    # 3. Verify Rust/PyO3 extension is built and importable
    try:
        import aletheia_rust  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Preflight Check Failed: The Rust PyO3 extension 'aletheia_rust' is not built or importable. "
            "Please compile the extension by running 'maturin develop' in the workspace."
        ) from exc

    # 4. Verify Ollama model is pulled (if Ollama is active)
    if settings.default_llm_provider == "ollama":
        try:
            r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP status {r.status_code}")

            data = r.json()
            models = data.get("models", [])
            model_names = [m["name"] for m in models]
            target_model = settings.default_llm_model

            found = False
            for name in model_names:
                if name == target_model or name.split(":")[0] == target_model.split(":")[0]:
                    found = True
                    break

            if not found:
                raise RuntimeError(
                    f"Model '{target_model}' is not pulled in Ollama. "
                    f"Please pull it by running 'ollama pull {target_model}' in your terminal."
                )
        except Exception as exc:
            raise RuntimeError(
                f"Preflight Check Failed: Ollama is unreachable at {settings.ollama_base_url} or "
                f"model verification failed. Error: {exc}"
            ) from exc


def register_exception_handlers(app: FastAPI, settings) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail if isinstance(exc.detail, str) else "HTTP Exception",
                "detail": exc.detail if not isinstance(exc.detail, str) else None,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Input validation failed",
                "detail": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.exception("Centralized Exception Middleware caught unhandled error:")

        detail = str(exc) if settings.debug else None
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred during execution",
                "detail": detail,
            },
        )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_dir, settings.log_level)
    container = get_container()

    # Run fail-fast startup preflight checks
    run_preflight_checks(settings)

    # Run automatic pruning if enabled
    if settings.retention_days is not None and settings.retention_days > 0:
        try:
            from aletheia.core.db.sqlite_store import SQLiteStore
            from aletheia.core.db.duckdb_store import DuckDBStore

            sqlite_store = SQLiteStore(settings.sqlite_path)
            duckdb_store = DuckDBStore(settings.duckdb_path)

            deleted_events = sqlite_store.prune_old_events(settings.retention_days)
            deleted_quotes = duckdb_store.prune_old_quotes(settings.retention_days)
            logger.info(
                "Data retention policy applied: pruned %d old SQLite events and %d old DuckDB quotes (> %d days).",
                deleted_events,
                deleted_quotes,
                settings.retention_days,
            )
        except Exception as exc:
            logger.warning("Failed to apply database retention policy on startup: %s", exc)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        plugins = container.resolve("plugins")
        scheduler = container.resolve("scheduler")
        metrics = container.resolve("metrics")
        plugins.load_all()
        await scheduler.start()
        metrics.increment("app.startups")
        try:
            yield
        finally:
            await scheduler.stop()
            metrics.increment("app.shutdowns")

    app = FastAPI(
        title="ALETHEIA",
        version="0.1.0",
        description="India-first multi-agent financial intelligence platform",
        lifespan=lifespan,
    )

    register_exception_handlers(app, settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, dependencies=[Depends(verify_api_key)])
    app.include_router(ws_router)

    health_registry = container.resolve("health")
    health_registry.register(
        "sqlite",
        lambda: {"ok": settings.sqlite_path.parent.exists(), "path": str(settings.sqlite_path)},
    )
    health_registry.register(
        "duckdb",
        lambda: {"ok": settings.duckdb_path.parent.exists(), "path": str(settings.duckdb_path)},
    )
    health_registry.register("event_bus", lambda: {"ok": True})

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "service": "ALETHEIA",
            "version": "0.1.0",
            "docs": "/docs",
        }

    # ------------------------------------------------------------------
    # Prometheus /metrics scraping endpoint
    # ------------------------------------------------------------------
    if _PROMETHEUS_AVAILABLE:
        # Define application-level metrics (idempotent — no-op if already registered)
        def _safe_counter(name: str, doc: str, labels: list[str] | None = None) -> "Counter":
            try:
                return Counter(name, doc, labels or [])
            except Exception:
                return _DEFAULT_REGISTRY._names_to_collectors.get(name)  # type: ignore[return-value]

        def _safe_histogram(name: str, doc: str, labels: list[str] | None = None) -> "Histogram":
            try:
                return Histogram(name, doc, labels or [])
            except Exception:
                return _DEFAULT_REGISTRY._names_to_collectors.get(name)  # type: ignore[return-value]

        def _safe_gauge(name: str, doc: str) -> "Gauge":
            try:
                return Gauge(name, doc)
            except Exception:
                return _DEFAULT_REGISTRY._names_to_collectors.get(name)  # type: ignore[return-value]

        _runs_total = _safe_counter(
            "aletheia_runs_total",
            "Total number of agent pipeline runs",
            ["status"],
        )
        _request_latency = _safe_histogram(
            "aletheia_http_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "endpoint"],
        )
        _active_runs = _safe_gauge("aletheia_active_runs", "Currently executing agent runs")

        import time as _time
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request as StarletteRequest

        class PrometheusMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: StarletteRequest, call_next):  # type: ignore[override]
                start = _time.perf_counter()
                response = await call_next(request)
                elapsed = _time.perf_counter() - start
                endpoint = request.url.path
                if _request_latency is not None:
                    _request_latency.labels(  # type: ignore[union-attr]
                        method=request.method, endpoint=endpoint
                    ).observe(elapsed)
                return response

        app.add_middleware(PrometheusMiddleware)

        @app.get("/metrics", include_in_schema=False)
        async def prometheus_metrics() -> Response:
            """Prometheus scraping endpoint."""
            data = generate_latest()
            return Response(content=data, media_type=CONTENT_TYPE_LATEST)

        logger.info("Prometheus /metrics endpoint registered.")
    else:
        logger.warning(
            "prometheus-client not installed — /metrics endpoint unavailable. "
            "Install with: pip install prometheus-client"
        )

    return app


app = create_app()
