"""Unit tests for RedisRateLimitMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from dataing.entrypoints.api.middleware.redis_rate_limit import (
    RedisRateLimitConfig,
    RedisRateLimitMiddleware,
)


class TestRedisRateLimitConfig:
    """Tests for RedisRateLimitConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = RedisRateLimitConfig()

        assert config.requests_per_minute == 60
        assert config.burst_size == 10
        assert config.key_prefix == "dataing:api_rate_limit"
        assert config.window_seconds == 60

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = RedisRateLimitConfig(
            requests_per_minute=100,
            burst_size=20,
            key_prefix="custom:prefix",
            window_seconds=120,
        )

        assert config.requests_per_minute == 100
        assert config.burst_size == 20
        assert config.key_prefix == "custom:prefix"
        assert config.window_seconds == 120


class TestRedisRateLimitMiddleware:
    """Tests for RedisRateLimitMiddleware."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.script_load = AsyncMock(return_value="script-sha-123")
        mock.evalsha = AsyncMock(return_value=[1, 59])  # allowed, remaining
        mock.zrange = AsyncMock(return_value=[])
        mock.delete = AsyncMock()
        mock.scan = AsyncMock(return_value=(0, []))
        return mock

    def test_middleware_disabled(self) -> None:
        """Test that disabled middleware passes requests through."""

        async def homepage(request: Request) -> Response:
            return JSONResponse({"status": "ok"})

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(RedisRateLimitMiddleware, redis=None, enabled=False)

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_middleware_no_redis_allows_all(self) -> None:
        """Test that middleware without Redis allows all requests."""

        async def homepage(request: Request) -> Response:
            return JSONResponse({"status": "ok"})

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(RedisRateLimitMiddleware, redis=None, enabled=True)

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers

    def test_health_check_not_rate_limited(self) -> None:
        """Test that health check endpoints are not rate limited."""

        async def health(request: Request) -> Response:
            return JSONResponse({"status": "healthy"})

        app = Starlette(routes=[Route("/health", health)])
        # Use a mock that would reject requests
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[0, 0])  # denied
        app.add_middleware(RedisRateLimitMiddleware, redis=mock_redis, enabled=True)

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200

    def test_get_identifier_from_tenant(self, mock_redis: AsyncMock) -> None:
        """Test identifier extraction from tenant context."""
        middleware = RedisRateLimitMiddleware(
            app=MagicMock(),
            redis=mock_redis,
        )

        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.auth_context = MagicMock()
        request.state.auth_context.tenant_id = "tenant-123"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        identifier = middleware._get_identifier(request)

        assert identifier == "tenant:tenant-123"

    def test_get_identifier_from_api_key(self, mock_redis: AsyncMock) -> None:
        """Test identifier extraction from API key."""
        middleware = RedisRateLimitMiddleware(
            app=MagicMock(),
            redis=mock_redis,
        )

        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.auth_context = None
        request.headers = {"x-api-key": "abcd1234xyz"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        identifier = middleware._get_identifier(request)

        assert identifier == "key:abcd1234"

    def test_get_identifier_from_ip(self, mock_redis: AsyncMock) -> None:
        """Test identifier extraction from IP address."""
        middleware = RedisRateLimitMiddleware(
            app=MagicMock(),
            redis=mock_redis,
        )

        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.auth_context = None
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        identifier = middleware._get_identifier(request)

        assert identifier == "ip:192.168.1.1"

    async def test_check_rate_limit_allowed(self, mock_redis: AsyncMock) -> None:
        """Test rate limit check when allowed."""
        mock_redis.evalsha.return_value = [1, 55]  # allowed, 55 remaining

        middleware = RedisRateLimitMiddleware(
            app=MagicMock(),
            redis=mock_redis,
        )

        allowed, remaining, retry_after = await middleware._check_rate_limit("tenant:test")

        assert allowed is True
        assert remaining == 55
        assert retry_after is None

    async def test_check_rate_limit_denied(self, mock_redis: AsyncMock) -> None:
        """Test rate limit check when denied."""
        mock_redis.evalsha.return_value = [0, 0]  # denied
        mock_redis.zrange.return_value = []

        middleware = RedisRateLimitMiddleware(
            app=MagicMock(),
            redis=mock_redis,
        )

        allowed, remaining, retry_after = await middleware._check_rate_limit("tenant:test")

        assert allowed is False
        assert remaining == 0
        assert retry_after is not None
        assert retry_after >= 0

    async def test_check_rate_limit_redis_error_fails_open(self, mock_redis: AsyncMock) -> None:
        """Test that rate limiter fails open on Redis errors."""
        mock_redis.evalsha.side_effect = Exception("Redis connection error")

        middleware = RedisRateLimitMiddleware(
            app=MagicMock(),
            redis=mock_redis,
        )

        allowed, remaining, retry_after = await middleware._check_rate_limit("tenant:test")

        assert allowed is True  # Fail open
        assert remaining == 60  # Default limit

    async def test_reset_specific_identifier(self, mock_redis: AsyncMock) -> None:
        """Test resetting rate limit for specific identifier."""
        middleware = RedisRateLimitMiddleware(
            app=MagicMock(),
            redis=mock_redis,
        )

        await middleware.reset("tenant:test")

        mock_redis.delete.assert_called_once()

    async def test_reset_all(self, mock_redis: AsyncMock) -> None:
        """Test resetting all rate limits."""
        mock_redis.scan.return_value = (0, [b"key1", b"key2"])

        middleware = RedisRateLimitMiddleware(
            app=MagicMock(),
            redis=mock_redis,
        )

        await middleware.reset(None)

        mock_redis.scan.assert_called()


class TestRateLimitIntegration:
    """Integration tests for rate limiting."""

    def test_rate_limit_exceeded_returns_429(self) -> None:
        """Test that exceeding rate limit returns 429."""

        async def homepage(request: Request) -> Response:
            return JSONResponse({"status": "ok"})

        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[0, 0])  # denied
        mock_redis.zrange = AsyncMock(return_value=[])

        app = Starlette(routes=[Route("/api/test", homepage)])
        app.add_middleware(RedisRateLimitMiddleware, redis=mock_redis, enabled=True)

        client = TestClient(app)
        response = client.get("/api/test")

        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]
        assert "Retry-After" in response.headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

    def test_successful_request_includes_headers(self) -> None:
        """Test that successful requests include rate limit headers."""

        async def homepage(request: Request) -> Response:
            return JSONResponse({"status": "ok"})

        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[1, 50])  # allowed, 50 remaining

        app = Starlette(routes=[Route("/api/test", homepage)])
        app.add_middleware(RedisRateLimitMiddleware, redis=mock_redis, enabled=True)

        client = TestClient(app)
        response = client.get("/api/test")

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "60"
        assert response.headers["X-RateLimit-Remaining"] == "50"

    def test_options_request_not_rate_limited(self) -> None:
        """Test that OPTIONS requests are not rate limited."""

        async def homepage(request: Request) -> Response:
            return Response(status_code=200)

        # Use a mock that would reject requests
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[0, 0])  # denied

        app = Starlette(routes=[Route("/api/test", homepage, methods=["GET", "OPTIONS"])])
        app.add_middleware(RedisRateLimitMiddleware, redis=mock_redis, enabled=True)

        client = TestClient(app)
        response = client.options("/api/test")

        # OPTIONS should pass through without rate limiting
        assert response.status_code == 200
