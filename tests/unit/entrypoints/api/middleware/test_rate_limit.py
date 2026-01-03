"""Unit tests for rate limit middleware."""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing.entrypoints.api.middleware.rate_limit import (
    RateLimitBucket,
    RateLimitConfig,
    RateLimitMiddleware,
)


class TestRateLimitBucket:
    """Tests for RateLimitBucket."""

    def test_create_bucket(self) -> None:
        """Test creating a rate limit bucket."""
        bucket = RateLimitBucket(
            tokens=10.0,
            last_update=time.time(),
            max_tokens=10,
            refill_rate=1.0,
        )

        assert bucket.tokens == 10.0
        assert bucket.max_tokens == 10

    def test_consume_success(self) -> None:
        """Test successful token consumption."""
        bucket = RateLimitBucket(
            tokens=10.0,
            last_update=time.time(),
            max_tokens=10,
            refill_rate=1.0,
        )

        result = bucket.consume(1)

        assert result is True
        assert bucket.tokens < 10

    def test_consume_failure(self) -> None:
        """Test failed token consumption when empty."""
        bucket = RateLimitBucket(
            tokens=0.0,
            last_update=time.time(),
            max_tokens=10,
            refill_rate=1.0,
        )

        result = bucket.consume(1)

        assert result is False

    def test_consume_refills_over_time(self) -> None:
        """Test that tokens refill over time."""
        past_time = time.time() - 5  # 5 seconds ago
        bucket = RateLimitBucket(
            tokens=0.0,
            last_update=past_time,
            max_tokens=10,
            refill_rate=1.0,  # 1 token per second
        )

        result = bucket.consume(1)

        # Should have refilled some tokens
        assert result is True

    def test_consume_caps_at_max(self) -> None:
        """Test that refill doesn't exceed max."""
        past_time = time.time() - 100  # Long ago
        bucket = RateLimitBucket(
            tokens=0.0,
            last_update=past_time,
            max_tokens=10,
            refill_rate=1.0,
        )

        bucket.consume(0)  # Just trigger refill

        assert bucket.tokens <= bucket.max_tokens

    def test_consume_multiple(self) -> None:
        """Test consuming multiple tokens."""
        bucket = RateLimitBucket(
            tokens=10.0,
            last_update=time.time(),
            max_tokens=10,
            refill_rate=1.0,
        )

        result = bucket.consume(5)

        assert result is True
        assert bucket.tokens < 6


class TestRateLimitConfig:
    """Tests for RateLimitConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = RateLimitConfig()

        assert config.requests_per_minute == 60
        assert config.requests_per_hour == 1000
        assert config.burst_size == 10

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = RateLimitConfig(
            requests_per_minute=30,
            requests_per_hour=500,
            burst_size=5,
        )

        assert config.requests_per_minute == 30
        assert config.burst_size == 5


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    @pytest.fixture
    def mock_app(self) -> MagicMock:
        """Return a mock app."""
        return MagicMock()

    @pytest.fixture
    def middleware(self, mock_app: MagicMock) -> RateLimitMiddleware:
        """Return a rate limit middleware."""
        return RateLimitMiddleware(mock_app)

    @pytest.fixture
    def strict_middleware(self, mock_app: MagicMock) -> RateLimitMiddleware:
        """Return a strict rate limit middleware."""
        return RateLimitMiddleware(
            mock_app,
            config=RateLimitConfig(
                requests_per_minute=2,
                burst_size=2,
            ),
        )

    def test_create_bucket(self, middleware: RateLimitMiddleware) -> None:
        """Test bucket creation."""
        bucket = middleware._create_bucket()

        assert bucket.max_tokens == middleware.config.burst_size
        assert bucket.refill_rate == middleware.config.requests_per_minute / 60.0

    def test_get_identifier_with_auth(
        self,
        middleware: RateLimitMiddleware,
    ) -> None:
        """Test identifier extraction with auth context."""
        request = MagicMock()
        request.state.auth_context = MagicMock()
        request.state.auth_context.tenant_id = uuid.uuid4()

        identifier = middleware._get_identifier(request)

        assert identifier.startswith("tenant:")

    def test_get_identifier_without_auth(
        self,
        middleware: RateLimitMiddleware,
    ) -> None:
        """Test identifier extraction without auth context."""
        request = MagicMock()
        request.state = MagicMock(spec=[])  # No auth_context
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        identifier = middleware._get_identifier(request)

        assert identifier == "ip:192.168.1.1"

    def test_get_identifier_no_client(
        self,
        middleware: RateLimitMiddleware,
    ) -> None:
        """Test identifier extraction without client info."""
        request = MagicMock()
        request.state = MagicMock(spec=[])
        request.client = None

        identifier = middleware._get_identifier(request)

        assert identifier == "ip:unknown"

    async def test_dispatch_passes_when_not_limited(
        self,
        middleware: RateLimitMiddleware,
    ) -> None:
        """Test dispatch passes request through when not limited."""
        request = MagicMock()
        request.state = MagicMock(spec=[])
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.url.path = "/api/test"

        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert "X-RateLimit-Limit" in result.headers

    async def test_dispatch_skips_health_checks(
        self,
        middleware: RateLimitMiddleware,
    ) -> None:
        """Test dispatch skips health check endpoints."""
        request = MagicMock()
        request.url.path = "/health"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once()

    async def test_dispatch_disabled(
        self,
        mock_app: MagicMock,
    ) -> None:
        """Test dispatch when middleware is disabled."""
        middleware = RateLimitMiddleware(mock_app, enabled=False)
        request = MagicMock()
        request.url.path = "/api/test"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once()

    async def test_dispatch_returns_429_when_limited(
        self,
        strict_middleware: RateLimitMiddleware,
    ) -> None:
        """Test dispatch returns 429 when rate limited."""
        request = MagicMock()
        request.state = MagicMock(spec=[])
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.url.path = "/api/test"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        # Exhaust the bucket
        identifier = strict_middleware._get_identifier(request)
        bucket = strict_middleware.buckets[identifier]
        bucket.tokens = 0.0
        bucket.last_update = time.time()

        result = await strict_middleware.dispatch(request, call_next)

        assert result.status_code == 429
        call_next.assert_not_called()

    def test_reset_identifier(self, middleware: RateLimitMiddleware) -> None:
        """Test resetting a specific identifier."""
        identifier = "test:id"
        middleware.buckets[identifier] = middleware._create_bucket()

        middleware.reset(identifier)

        assert identifier not in middleware.buckets

    def test_reset_all(self, middleware: RateLimitMiddleware) -> None:
        """Test resetting all identifiers."""
        middleware.buckets["id1"] = middleware._create_bucket()
        middleware.buckets["id2"] = middleware._create_bucket()

        middleware.reset()

        assert len(middleware.buckets) == 0
