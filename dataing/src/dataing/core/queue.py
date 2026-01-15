"""Redis queue configuration and helpers for durable job execution.

This module provides the interface between the FastAPI application and
the Arq job queue. It supports both URL-based and component-based
Redis configuration.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from opentelemetry.trace import SpanKind

from dataing.telemetry import get_tracer, serialize_trace_context

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
    parent_job_id: str | None = None,
    branch_spec: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> str:
    """Enqueue an investigation job for processing with trace context propagation.

    Args:
        investigation_id: UUID of the investigation to process.
        tenant_id: UUID of the tenant owning the investigation.
        datasource_id: Optional specific datasource ID to use.
        priority: Job priority (higher = more important). Defaults to 0.
        parent_job_id: Optional parent job ID for branched execution.
        branch_spec: Optional serialized BranchSpec for branched execution.
        correlation_id: Optional correlation ID for log correlation.

    Returns:
        The Arq job ID for tracking.
    """
    tracer = get_tracer("dataing.queue")

    # Create producer span (links API trace to queue)
    with tracer.start_as_current_span(
        "investigation.enqueue",
        kind=SpanKind.PRODUCER,
        attributes={
            "investigation.id": investigation_id,
            "tenant.id": tenant_id,
            "messaging.system": "redis",
            "messaging.destination": INVESTIGATIONS_QUEUE,
        },
    ):
        # Serialize current trace context (includes traceparent, tracestate)
        trace_context = serialize_trace_context()
        enqueued_at = datetime.now(UTC).isoformat()

        queue = await get_queue()
        try:
            job = await queue.enqueue_job(
                "run_investigation",
                investigation_id=investigation_id,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                parent_job_id=parent_job_id,
                branch_spec=branch_spec,
                # NEW: Full trace context payload
                trace_context={
                    "traceparent": trace_context.get("traceparent"),
                    "tracestate": trace_context.get("tracestate"),
                    "correlation_id": correlation_id,
                    "enqueued_at": enqueued_at,
                },
                _queue_name=INVESTIGATIONS_QUEUE,
            )
            if job is None:
                raise RuntimeError("Failed to enqueue investigation job")
            job_id: str = job.job_id
            logger.info(
                f"Investigation enqueued: investigation_id={investigation_id}, "
                f"tenant_id={tenant_id}, job_id={job_id}, "
                f"traceparent={trace_context.get('traceparent')}, "
                f"correlation_id={correlation_id}"
            )
            return job_id
        finally:
            await queue.close()


async def enqueue_branch_jobs(
    investigation_id: str,
    tenant_id: str,
    parent_job_id: str,
    datasource_id: str | None,
    branch_specs: list[dict[str, Any]],
    correlation_id: str | None = None,
) -> list[str]:
    """Enqueue multiple child jobs for branched execution.

    Used when a workflow emits Signal.BRANCH to create parallel
    execution paths. Each branch becomes its own job.

    Args:
        investigation_id: UUID of the investigation.
        tenant_id: UUID of the tenant.
        parent_job_id: UUID of the parent job creating the branches.
        datasource_id: Optional datasource ID.
        branch_specs: List of serialized BranchSpec dictionaries.
        correlation_id: Optional correlation ID for log correlation.

    Returns:
        List of Arq job IDs for the created branch jobs.
    """
    job_ids = []
    for spec in branch_specs:
        job_id = await enqueue_investigation(
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            parent_job_id=parent_job_id,
            branch_spec=spec,
            correlation_id=correlation_id,
        )
        job_ids.append(job_id)
    logger.info(
        f"Branch jobs enqueued: investigation_id={investigation_id}, "
        f"parent_job_id={parent_job_id}, count={len(job_ids)}"
    )
    return job_ids
