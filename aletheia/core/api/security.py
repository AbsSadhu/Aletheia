from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging

logger = logging.getLogger(__name__)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# In a real app, load this from secure storage or settings
VALID_API_KEYS = {"dev_key_123", "aletheia_prod_999"}

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

async def verify_api_key(request: Request):
    api_key = request.headers.get(API_KEY_NAME)
    # Require API key only in production or if explicitly configured
    # For now, we simulate basic auth
    if api_key and api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )
    return api_key
