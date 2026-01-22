"""Unit tests for RedisRateLimiter."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from dataing.adapters.queue.redis_rate_limiter import RateLimitResult, RedisRateLimiter
from dataing.services.policy import QueueConfig


class TestRateLimitResult:
    """Tests for RateLimitResult."""

    def test_allowed_result(self) -> None:
        """Test allowed rate limit result."""
        result = RateLimitResult(
            allowed=True,
            remaining=50,
            limit=60,
        )

        assert result.allowed is True
        assert result.remaining == 50
        assert result.limit == 60
        assert result.retry_after is None

    def test_denied_result(self) -> None:
        """Test denied rate limit result."""
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=60,
            retry_after=30.0,
        )

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 30.0


class TestRedisRateLimiter:
    """Tests for RedisRateLimiter."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.script_load = AsyncMock(return_value="script-sha-123")
        mock.evalsha = AsyncMock(return_value=[1, 59])  # allowed, remaining
        mock.zrange = AsyncMock(return_value=[])
        mock.zcount = AsyncMock(return_value=0)
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def rate_limiter(self, mock_redis: AsyncMock) -> RedisRateLimiter:
        """Create a rate limiter with mock Redis."""
        return RedisRateLimiter(mock_redis)

    @pytest.fixture
    def queue_config(self) -> QueueConfig:
        """Create a queue configuration."""
        return QueueConfig(
            rate_limit_per_minute=60,
            burst_size=10,
            max_concurrent=5,
            batch_size=5,
        )

    async def test_check_and_consume_allowed(
        self,
        rate_limiter: RedisRateLimiter,
        mock_redis: AsyncMock,
        queue_config: QueueConfig,
    ) -> None:
        """Test rate limit check when allowed."""
        mock_redis.evalsha.return_value = [1, 55]  # allowed, 55 remaining
        team_id = uuid.uuid4()

        result = await rate_limiter.check_and_consume(team_id, queue_config, tokens=5)

        assert result.allowed is True
        assert result.remaining == 55
        assert result.limit == 60

    async def test_check_and_consume_denied(
        self,
        rate_limiter: RedisRateLimiter,
        mock_redis: AsyncMock,
        queue_config: QueueConfig,
    ) -> None:
        """Test rate limit check when denied."""
        mock_redis.evalsha.return_value = [0, 0]  # denied
        mock_redis.zrange.return_value = []
        team_id = uuid.uuid4()

        result = await rate_limiter.check_and_consume(team_id, queue_config, tokens=5)

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None
        assert result.retry_after >= 0

    async def test_check_and_consume_loads_script(
        self,
        rate_limiter: RedisRateLimiter,
        mock_redis: AsyncMock,
        queue_config: QueueConfig,
    ) -> None:
        """Test that rate limiter loads Lua script."""
        team_id = uuid.uuid4()

        await rate_limiter.check_and_consume(team_id, queue_config)

        mock_redis.script_load.assert_called_once()

    async def test_check_and_consume_reuses_script(
        self,
        rate_limiter: RedisRateLimiter,
        mock_redis: AsyncMock,
        queue_config: QueueConfig,
    ) -> None:
        """Test that rate limiter reuses loaded script."""
        team_id = uuid.uuid4()

        # First call loads script
        await rate_limiter.check_and_consume(team_id, queue_config)
        # Second call should reuse
        await rate_limiter.check_and_consume(team_id, queue_config)

        # Script should only be loaded once
        assert mock_redis.script_load.call_count == 1

    async def test_check_and_consume_fails_open(
        self,
        rate_limiter: RedisRateLimiter,
        mock_redis: AsyncMock,
        queue_config: QueueConfig,
    ) -> None:
        """Test that rate limiter fails open on Redis errors."""
        mock_redis.evalsha.side_effect = Exception("Redis error")
        team_id = uuid.uuid4()

        result = await rate_limiter.check_and_consume(team_id, queue_config)

        # Should allow request when Redis fails
        assert result.allowed is True
        assert result.remaining == queue_config.rate_limit_per_minute

    async def test_get_remaining(
        self,
        rate_limiter: RedisRateLimiter,
        mock_redis: AsyncMock,
        queue_config: QueueConfig,
    ) -> None:
        """Test getting remaining tokens."""
        mock_redis.zcount.return_value = 10  # 10 requests in window
        team_id = uuid.uuid4()

        remaining = await rate_limiter.get_remaining(team_id, queue_config)

        assert remaining == 50  # 60 - 10

    async def test_get_remaining_at_limit(
        self,
        rate_limiter: RedisRateLimiter,
        mock_redis: AsyncMock,
        queue_config: QueueConfig,
    ) -> None:
        """Test getting remaining when at limit."""
        mock_redis.zcount.return_value = 70  # Over limit
        team_id = uuid.uuid4()

        remaining = await rate_limiter.get_remaining(team_id, queue_config)

        assert remaining == 0  # Can't go negative

    async def test_reset(
        self,
        rate_limiter: RedisRateLimiter,
        mock_redis: AsyncMock,
    ) -> None:
        """Test resetting rate limit for a team."""
        team_id = uuid.uuid4()

        await rate_limiter.reset(team_id)

        mock_redis.delete.assert_called_once()

    async def test_team_key_format(
        self,
        rate_limiter: RedisRateLimiter,
    ) -> None:
        """Test that team keys are formatted correctly."""
        team_id = uuid.uuid4()

        key = rate_limiter._team_key(team_id)

        assert str(team_id) in key
        assert "rate_limit" in key
