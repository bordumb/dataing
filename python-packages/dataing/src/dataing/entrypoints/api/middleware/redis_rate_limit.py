"""Redis-backed rate limiting middleware.

Provides distributed rate limiting using Redis sliding window algorithm.
Falls back to in-memory limiting when Redis is unavailable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = structlog.get_logger()


# Lua script for sliding window rate limiting
# Returns [allowed (0/1), remaining_tokens]
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_size = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local tokens = tonumber(ARGV[4])

-- Remove expired entries
local window_start = now - window_size
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- Count current requests in window
local current = redis.call('ZCARD', key)

-- Check if we can allow this request
if current + tokens <= limit then
    -- Add new entries for each token consumed
    for i = 1, tokens do
        redis.call('ZADD', key, now, now .. ':' .. i .. ':' .. math.random(1000000))
    end
    -- Set expiry on the key
    redis.call('EXPIRE', key, window_size + 1)
    return {1, limit - current - tokens}
else
    return {0, 0}
end
"""


@dataclass
class RedisRateLimitConfig:
    """Configuration for Redis rate limiting."""

    requests_per_minute: int = 60
    burst_size: int = 10
    key_prefix: str = "dataing:api_rate_limit"
    window_seconds: int = 60


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis sliding window algorithm.

    Falls back to allowing requests if Redis is unavailable (fail-open).
    """

    def __init__(
        self,
        app: ASGIApp,
        redis: Redis | None = None,
        config: RedisRateLimitConfig | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize Redis rate limit middleware.

        Args:
            app: The ASGI application.
            redis: Optional Redis client. If None, rate limiting is disabled.
            config: Rate limiting configuration.
            enabled: Whether rate limiting is enabled.
        """
        super().__init__(app)
        self.redis = redis
        self.config = config or RedisRateLimitConfig()
        self.enabled = enabled
        self._script_sha: str | None = None

    async def _ensure_script_loaded(self) -> str | None:
        """Load the Lua script if not already loaded."""
        if self._script_sha is None and self.redis is not None:
            try:
                self._script_sha = await self.redis.script_load(RATE_LIMIT_SCRIPT)
            except Exception as e:
                logger.warning("rate_limit_script_load_failed", error=str(e))
                return None
        return self._script_sha

    def _get_identifier(self, request: Request) -> str:
        """Get rate limit identifier from request.

        Priority:
        1. Tenant ID from auth context
        2. API key (hashed)
        3. Client IP address
        """
        # Try to get tenant ID from auth context
        auth_context = getattr(request.state, "auth_context", None)
        if auth_context:
            tenant_id = getattr(auth_context, "tenant_id", None)
            if tenant_id:
                return f"tenant:{tenant_id}"

        # Try to get API key from header
        api_key = request.headers.get("x-api-key")
        if api_key:
            # Use first 8 chars of API key as identifier (don't store full key)
            return f"key:{api_key[:8]}"

        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def _get_key(self, identifier: str) -> str:
        """Build Redis key for identifier."""
        return f"{self.config.key_prefix}:{identifier}"

    async def _check_rate_limit(self, identifier: str) -> tuple[bool, int, float | None]:
        """Check rate limit for identifier.

        Returns:
            Tuple of (allowed, remaining, retry_after).
        """
        if self.redis is None:
            # No Redis = allow all (disabled)
            return True, self.config.requests_per_minute, None

        script_sha = await self._ensure_script_loaded()
        if script_sha is None:
            # Script load failed = fail open
            return True, self.config.requests_per_minute, None

        key = self._get_key(identifier)
        now = time.time()

        try:
            result = await self.redis.evalsha(  # type: ignore[misc]
                script_sha,
                1,  # number of keys
                key,
                str(now),
                str(self.config.window_seconds),
                str(self.config.requests_per_minute),
                "1",  # consume 1 token
            )

            allowed = bool(result[0])
            remaining = int(result[1])

            if not allowed:
                # Calculate retry_after based on oldest entry
                oldest = await self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = oldest[0][1]
                    retry_after = max(0, self.config.window_seconds - (now - oldest_time))
                else:
                    retry_after = float(self.config.window_seconds)
                return False, 0, retry_after

            return True, remaining, None

        except Exception as e:
            logger.warning("rate_limit_check_failed", error=str(e), identifier=identifier)
            # Fail open on Redis errors
            return True, self.config.requests_per_minute, None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request with rate limiting."""
        if not self.enabled:
            return await call_next(request)

        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/healthz", "/ready"]:
            return await call_next(request)

        # Skip rate limiting for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        identifier = self._get_identifier(request)
        allowed, remaining, retry_after = await self._check_rate_limit(identifier)

        if not allowed:
            logger.warning("api_rate_limit_exceeded", identifier=identifier)

            retry_after_int = int(retry_after) if retry_after else self.config.window_seconds

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": retry_after_int,
                },
                headers={
                    "Retry-After": str(retry_after_int),
                    "X-RateLimit-Limit": str(self.config.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after_int),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(self.config.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    async def reset(self, identifier: str | None = None) -> None:
        """Reset rate limit for an identifier or all.

        Args:
            identifier: Specific identifier to reset, or None for all.
        """
        if self.redis is None:
            return

        if identifier:
            key = self._get_key(identifier)
            await self.redis.delete(key)
        else:
            # Delete all rate limit keys (use with caution)
            pattern = f"{self.config.key_prefix}:*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
