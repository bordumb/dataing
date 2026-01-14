"""Redis queue configuration and helpers for durable job execution.

This module provides the interface between the FastAPI application and
the Arq job queue. It supports both URL-based and component-based
Redis configuration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default queue name for investigation jobs
INVESTIGATIONS_QUEUE = "investigations"


def get_redis_settings() -> RedisSettings:
    """Get Redis connection settings from environment.

    Supports both URL-based configuration (REDIS_URL) and component-based
    configuration (REDIS_HOST, REDIS_PORT, etc.). URL takes precedence.

    Returns:
        RedisSettings configured from environment variables.
    """
    # Import here to avoid circular imports
    from dataing.entrypoints.api.deps import settings

    # URL-based config takes precedence
    if settings.redis_url:
        parsed = urlparse(settings.redis_url)
        return RedisSettings(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password or None,
            database=int(parsed.path.lstrip("/") or "0") if parsed.path else 0,
        )

    # Component-based config
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        database=settings.redis_db,
    )


async def get_queue() -> ArqRedis:
    """Get an Arq Redis connection pool.

    Creates a new connection pool using the configured Redis settings.
    The caller is responsible for closing the pool when done.

    Returns:
        ArqRedis connection pool.
    """
    redis_settings = get_redis_settings()
    return await create_pool(redis_settings)


async def enqueue_investigation(
    investigation_id: str,
    tenant_id: str,
    datasource_id: str | None = None,
    priority: int = 0,
) -> str:
    """Enqueue an investigation job for processing.

    Args:
        investigation_id: UUID of the investigation to process.
        tenant_id: UUID of the tenant owning the investigation.
        datasource_id: Optional specific datasource ID to use.
        priority: Job priority (higher = more important). Defaults to 0.

    Returns:
        The Arq job ID for tracking.
    """
    queue = await get_queue()
    try:
        job = await queue.enqueue_job(
            "run_investigation",
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            _queue_name=INVESTIGATIONS_QUEUE,
        )
        if job is None:
            raise RuntimeError("Failed to enqueue investigation job")
        logger.info(
            f"Investigation enqueued: investigation_id={investigation_id}, "
            f"tenant_id={tenant_id}, job_id={job.job_id}"
        )
        return job.job_id
    finally:
        await queue.close()
