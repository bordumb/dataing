"""Arq worker entrypoint for durable investigation execution.

This module provides the worker process that polls Redis for investigation
jobs and executes them with checkpoint-based crash recovery.

Usage:
    uv run python -m dataing.entrypoints.worker
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any
from uuid import UUID, uuid4

from arq import Worker

from dataing.adapters.datasource import create_adapter_for_datasource
from dataing.adapters.db.app_db import AppDatabase
from dataing.core.queue import INVESTIGATIONS_QUEUE, get_redis_settings

logger = logging.getLogger(__name__)

# Unique identifier for this worker instance
WORKER_ID = str(uuid4())

# Shutdown signal for graceful termination
shutdown_event = asyncio.Event()


async def run_investigation(
    ctx: dict[str, Any],
    investigation_id: str,
    tenant_id: str,
    datasource_id: str | None = None,
    parent_job_id: str | None = None,
    branch_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute an investigation workflow.

    This is the main job handler. Supports both root jobs and branch jobs
    (child jobs created from BRANCH signal).

    Args:
        ctx: Worker context containing database connection and other resources.
        investigation_id: UUID of the investigation to process.
        tenant_id: UUID of the tenant owning the investigation.
        datasource_id: Optional specific datasource ID to use.
        parent_job_id: Parent job ID if this is a branch job.
        branch_spec: BranchSpec data if this is a branch job.

    Returns:
        Dictionary with job result status and investigation_id.
    """
    is_branch = parent_job_id is not None
    logger.info(
        f"Processing investigation: investigation_id={investigation_id}, "
        f"tenant_id={tenant_id}, worker_id={WORKER_ID}, "
        f"is_branch={is_branch}, parent_job_id={parent_job_id}"
    )

    db: AppDatabase = ctx["db"]

    # Reconstruct adapter from stored datasource config if specified
    adapter = None
    if datasource_id:
        try:
            adapter = await create_adapter_for_datasource(
                db=db,
                tenant_id=UUID(tenant_id),
                datasource_id=UUID(datasource_id),
            )
            logger.info(f"Adapter reconstructed for datasource: {datasource_id}")
        except Exception as e:
            logger.error(f"Failed to reconstruct adapter: {e}")
            return {
                "status": "failed",
                "investigation_id": investigation_id,
                "worker_id": WORKER_ID,
                "error": str(e),
            }

    # TODO: Full workflow implementation
    # - Load/create job record
    # - Run workflow with checkpointing
    # - Handle BRANCH signal by creating child jobs
    # - Update job status

    # If this is a branch job, check if parent can merge after completion
    if is_branch and parent_job_id:
        await check_and_trigger_merge(db, UUID(parent_job_id))

    return {
        "status": "complete",
        "investigation_id": investigation_id,
        "worker_id": WORKER_ID,
        "adapter_type": type(adapter).__name__ if adapter else None,
        "is_branch": is_branch,
        "branch_spec": branch_spec,
    }


async def check_and_trigger_merge(db: AppDatabase, parent_job_id: UUID) -> bool:
    """Check if parent job can merge after child completes.

    When a child job completes, checks if all siblings are also complete.
    If so, marks the parent as ready to resume.

    Args:
        db: Database connection.
        parent_job_id: UUID of the parent job.

    Returns:
        True if merge was triggered, False otherwise.
    """
    pending = await db.get_pending_children_count(parent_job_id)

    if pending == 0:
        # All children complete, trigger merge
        logger.info(f"All children complete, triggering merge: parent_job_id={parent_job_id}")
        await db.update_job_status(
            job_id=parent_job_id,
            status="pending",  # Mark as pending to be picked up again
            current_step="merge",
        )
        return True

    logger.info(f"Waiting for children: parent_job_id={parent_job_id}, pending={pending}")
    return False


async def handle_branch_signal(
    db: AppDatabase,
    job_id: UUID,
    investigation_id: str,
    tenant_id: str,
    datasource_id: str | None,
    branch_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Handle BRANCH signal by creating child jobs.

    Creates child jobs in the database and enqueues them. Parent job
    is set to 'awaiting_merge' status.

    Args:
        db: Database connection.
        job_id: UUID of the parent job.
        investigation_id: UUID of the investigation.
        tenant_id: UUID of the tenant.
        datasource_id: Optional datasource ID.
        branch_specs: List of BranchSpec dictionaries.

    Returns:
        Dictionary with branched status and child count.
    """
    from dataing.core.queue import enqueue_branch_jobs

    logger.info(
        f"Handling BRANCH signal: job_id={job_id}, "
        f"investigation_id={investigation_id}, branches={len(branch_specs)}"
    )

    # Create child job records in database
    for spec in branch_specs:
        await db.create_child_job(
            parent_job_id=job_id,
            investigation_id=UUID(investigation_id),
            tenant_id=UUID(tenant_id),
            datasource_id=UUID(datasource_id) if datasource_id else None,
            branch_spec=spec,
        )

    # Set parent to awaiting_merge
    await db.set_job_awaiting_merge(job_id)

    # Enqueue child jobs
    await enqueue_branch_jobs(
        investigation_id=investigation_id,
        tenant_id=tenant_id,
        parent_job_id=str(job_id),
        datasource_id=datasource_id,
        branch_specs=branch_specs,
    )

    return {
        "status": "branched",
        "investigation_id": investigation_id,
        "worker_id": WORKER_ID,
        "children": len(branch_specs),
    }


async def check_cancellation(db: AppDatabase, job_id: UUID) -> bool:
    """Check if job should be cancelled.

    Called at step boundaries to detect user-initiated cancellation.

    Args:
        db: Database connection.
        job_id: UUID of the job to check.

    Returns:
        True if job status is 'cancelling', False otherwise.
    """
    status = await db.get_job_status(job_id)
    return status == "cancelling"


async def handle_cancellation(db: AppDatabase, job_id: UUID) -> dict[str, Any]:
    """Handle job cancellation gracefully.

    Marks the job as 'cancelled' and returns a cancellation result.

    Args:
        db: Database connection.
        job_id: UUID of the job being cancelled.

    Returns:
        Dictionary with cancelled status.
    """
    from dataing.core.investigation.flow import InvestigationCancelled

    await db.mark_job_cancelled(job_id)
    logger.info(f"Job cancelled: job_id={job_id}")
    raise InvestigationCancelled()


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize worker resources on startup.

    Sets up database connection and signal handlers for graceful shutdown.

    Args:
        ctx: Worker context dictionary to populate with resources.
    """
    logger.info(f"Worker starting: worker_id={WORKER_ID}")

    # Initialize database connection
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/dataing")
    app_database_url = os.getenv("APP_DATABASE_URL", database_url)

    db = AppDatabase(app_database_url)
    await db.connect()
    ctx["db"] = db
    ctx["worker_id"] = WORKER_ID
    ctx["shutdown_event"] = shutdown_event

    # Register signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info(f"Received {sig.name}, initiating graceful shutdown")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

    logger.info("Worker startup complete")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Clean up worker resources on shutdown.

    Args:
        ctx: Worker context containing resources to clean up.
    """
    logger.info(f"Worker shutting down: worker_id={WORKER_ID}")

    # Close database connection
    db = ctx.get("db")
    if db is not None:
        await db.close()
        logger.info("Database connection closed")

    logger.info("Worker shutdown complete")


class WorkerSettings:
    """Arq worker configuration.

    Attributes:
        functions: List of job handler functions.
        queue_name: Redis queue name to poll.
        redis_settings: Redis connection configuration.
        on_startup: Startup coroutine for resource initialization.
        on_shutdown: Shutdown coroutine for cleanup.
        max_jobs: Maximum concurrent jobs per worker.
        job_timeout: Maximum job execution time in seconds.
        job_completion_wait: Grace period for in-flight jobs on shutdown.
        health_check_interval: Interval for health check pings.
        handle_signals: Whether to handle SIGTERM/SIGINT.
        retry_jobs: Whether to auto-retry failed jobs.
    """

    functions = [run_investigation]
    queue_name = INVESTIGATIONS_QUEUE
    redis_settings = get_redis_settings()

    on_startup = startup
    on_shutdown = shutdown

    # Concurrency
    max_jobs = 5

    # Timeouts (in seconds)
    job_timeout = 7200  # 2 hours - investigations can be long-running
    job_completion_wait = 30  # Align with K8s terminationGracePeriodSeconds

    # Health
    health_check_interval = 30

    # Signals
    handle_signals = True

    # Retries - we handle retries via investigation_jobs.attempts
    retry_jobs = False


def main() -> None:
    """Entry point for the worker process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Starting Arq worker")
    Worker(WorkerSettings).run()


if __name__ == "__main__":
    main()
