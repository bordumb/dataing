"""Rate limiting middleware."""

import time
from collections import defaultdict
from dataclasses import dataclass

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = structlog.get_logger()


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""

    tokens: float
    last_update: float
    max_tokens: int
    refill_rate: float  # tokens per second

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        now = time.time()

        # Refill tokens based on time elapsed
        elapsed = now - self.last_update
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using token bucket algorithm."""

    def __init__(
        self,
        app: ASGIApp,
        config: RateLimitConfig | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize rate limit middleware.

        Args:
            app: The ASGI application.
            config: Rate limiting configuration.
            enabled: Whether rate limiting is enabled.
        """
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.enabled = enabled

        # Per-tenant rate limit buckets
        self.buckets: dict[str, RateLimitBucket] = defaultdict(self._create_bucket)

    def _create_bucket(self) -> RateLimitBucket:
        """Create a new rate limit bucket."""
        return RateLimitBucket(
            tokens=float(self.config.burst_size),
            last_update=time.time(),
            max_tokens=self.config.burst_size,
            refill_rate=self.config.requests_per_minute / 60.0,
        )

    def _get_identifier(self, request: Request) -> str:
        """Get rate limit identifier from request."""
        # Try to get tenant ID from auth context
        auth_context = getattr(request.state, "auth_context", None)
        if auth_context:
            return f"tenant:{auth_context.tenant_id}"

        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request with rate limiting."""
        if not self.enabled:
            return await call_next(request)

        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/healthz", "/ready"]:
            return await call_next(request)

        # Get identifier after auth middleware has run
        # Note: This middleware should be added after auth
        identifier = self._get_identifier(request)
        bucket = self.buckets[identifier]

        if not bucket.consume():
            logger.warning("rate_limit_exceeded", identifier=identifier)

            retry_after = int(1.0 / bucket.refill_rate)

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.config.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.config.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))

        return response

    def reset(self, identifier: str | None = None) -> None:
        """Reset rate limit for an identifier or all."""
        if identifier:
            if identifier in self.buckets:
                del self.buckets[identifier]
        else:
            self.buckets.clear()
