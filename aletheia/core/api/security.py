from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
from typing import Any

from aletheia.core.config.settings import get_settings

logger = logging.getLogger(__name__)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

_warned_open_auth = False


class PyO3RateLimiter:
    """FastAPI dependency for rate limiting using aletheia_rust.RateLimiter."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.limiters: dict[str, Any] = {}

    def get_limiter(self, ip: str) -> Any:
        try:
            import aletheia_rust

            if ip not in self.limiters:
                self.limiters[ip] = aletheia_rust.RateLimiter(self.rate, self.capacity)
            return self.limiters[ip]
        except ImportError:
            return None

    async def __call__(self, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        limiter = self.get_limiter(client_ip)
        if limiter is not None:
            if not limiter.consume(1.0):
                logger.warning(f"Rate limit exceeded for IP {client_ip}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too Many Requests"
                )
        else:
            # Fallback simple rate limiting if aletheia_rust is not built
            logger.debug("aletheia_rust not importable, bypassing RateLimiter")


# Initialize rate limiters for run, portfolio and analysis endpoints
submit_run_limiter = PyO3RateLimiter(rate=2.0, capacity=5.0)
submit_portfolio_limiter = PyO3RateLimiter(rate=2.0, capacity=5.0)
portfolio_analysis_limiter = PyO3RateLimiter(rate=2.0, capacity=5.0)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_counts = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        current_time = time.time()

        # Clean up old entries
        self.request_counts = {
            ip: [t for t in times if current_time - t < self.window_seconds]
            for ip, times in self.request_counts.items()
        }

        # Check rate limit
        times = self.request_counts.get(client_ip, [])
        if len(times) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for IP {client_ip}")
            raise HTTPException(status_code=429, detail="Too Many Requests")

        times.append(current_time)
        self.request_counts[client_ip] = times

        response = await call_next(request)
        return response


def _auth_disabled_warning() -> None:
    global _warned_open_auth
    if not _warned_open_auth:
        logger.warning(
            "ALETHEIA_API_KEYS is not configured — API auth is DISABLED. "
            "Set ALETHEIA_API_KEYS to require an API key on every request."
        )
        _warned_open_auth = True


def is_authorized(supplied_key: str | None) -> bool:
    """Transport-agnostic key check shared by the HTTP dependency and the
    WebSocket handler (which can't rely on custom headers from a browser)."""
    api_keys = get_settings().api_keys
    if not api_keys:
        _auth_disabled_warning()
        return True
    return supplied_key is not None and supplied_key in api_keys


async def verify_api_key(request: Request):
    # Health checks must stay reachable without a key (Docker/k8s probes don't send headers).
    if request.url.path.startswith("/api/v1/health"):
        return None

    api_key = request.headers.get(API_KEY_NAME)
    if not is_authorized(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
        )
    return api_key
