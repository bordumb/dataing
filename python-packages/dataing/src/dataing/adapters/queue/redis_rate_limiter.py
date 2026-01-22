"""Redis-backed rate limiter using sliding window algorithm.

This module provides per-team rate limiting with:
- Sliding window rate limiting
- Configurable limits per team
- Token bucket for burst handling
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

import structlog
from redis.asyncio import Redis

from dataing.services.policy import QueueConfig

logger = structlog.get_logger()

# Lua script for atomic sliding window rate limiting
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_size = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local tokens = tonumber(ARGV[4])

-- Remove old entries outside the window
local window_start = now - window_size
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- Count current requests in window
local current = redis.call('ZCARD', key)

if current + tokens <= limit then
    -- Add the new request(s)
    for i = 1, tokens do
        redis.call('ZADD', key, now, now .. ':' .. i .. ':' .. math.random(1000000))
    end
    -- Set expiry on the key
    redis.call('EXPIRE', key, window_size + 1)
    return {1, limit - current - tokens}  -- allowed, remaining
else
    return {0, 0}  -- denied, remaining
end
"""


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    limit: int
    retry_after: float | None = None


class RedisRateLimiter:
    """Redis-backed rate limiter with sliding window algorithm."""

    def __init__(
        self,
        redis: Redis,
        key_prefix: str = "dataing:rate_limit",
    ) -> None:
        """Initialize the rate limiter."""
        self.redis = redis
        self.key_prefix = key_prefix
        self._script_sha: str | None = None

    async def _get_script_sha(self) -> str:
        """Get or load the Lua script SHA."""
        if self._script_sha is None:
            self._script_sha = await self.redis.script_load(RATE_LIMIT_SCRIPT)
        return self._script_sha

    def _team_key(self, team_id: UUID) -> str:
        """Get the rate limit key for a team."""
        return f"{self.key_prefix}:team:{team_id}"

    async def check_and_consume(
        self,
        team_id: UUID,
        config: QueueConfig,
        tokens: int = 1,
    ) -> RateLimitResult:
        """Check rate limit and consume tokens if allowed.

        Args:
            team_id: Team to check rate limit for.
            config: Queue configuration with rate limits.
            tokens: Number of tokens to consume (default 1).

        Returns:
            RateLimitResult indicating if the request is allowed.
        """
        key = self._team_key(team_id)
        now = time.time()
        window_size = 60  # 1 minute window
        limit = config.rate_limit_per_minute

        try:
            script_sha = await self._get_script_sha()
            result = await self.redis.evalsha(  # type: ignore[misc]
                script_sha,
                1,  # number of keys
                key,  # KEYS[1]
                str(now),  # ARGV[1]
                str(window_size),  # ARGV[2]
                str(limit),  # ARGV[3]
                str(tokens),  # ARGV[4]
            )

            allowed = bool(result[0])
            remaining = int(result[1])

            if not allowed:
                # Calculate retry_after based on oldest entry in window
                oldest = await self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = oldest[0][1]
                    retry_after = window_size - (now - oldest_time)
                else:
                    retry_after = window_size

                logger.debug(
                    "rate_limit_exceeded",
                    team_id=str(team_id),
                    limit=limit,
                    retry_after=retry_after,
                )

                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    limit=limit,
                    retry_after=max(0, retry_after),
                )

            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                limit=limit,
            )

        except Exception as e:
            # On Redis errors, allow the request (fail open)
            logger.warning(
                "rate_limit_check_failed",
                team_id=str(team_id),
                error=str(e),
            )
            return RateLimitResult(
                allowed=True,
                remaining=limit,
                limit=limit,
            )

    async def get_remaining(self, team_id: UUID, config: QueueConfig) -> int:
        """Get remaining rate limit tokens for a team."""
        key = self._team_key(team_id)
        now = time.time()
        window_size = 60
        window_start = now - window_size

        # Count current requests in window
        current: int = await self.redis.zcount(key, window_start, now)
        return max(0, config.rate_limit_per_minute - current)

    async def reset(self, team_id: UUID) -> None:
        """Reset rate limit for a team."""
        key = self._team_key(team_id)
        await self.redis.delete(key)
        logger.debug("rate_limit_reset", team_id=str(team_id))
