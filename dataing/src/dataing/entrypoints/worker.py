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
from uuid import uuid4

from arq import Worker

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
) -> dict[str, Any]:
    """Execute an investigation workflow.

    This is the main job handler. Full implementation will be added
    in task fn-10.5 (Integrate queue with InvestigationService).

    Args:
        ctx: Worker context containing database connection and other resources.
        investigation_id: UUID of the investigation to process.
        tenant_id: UUID of the tenant owning the investigation.
        datasource_id: Optional specific datasource ID to use.

    Returns:
        Dictionary with job result status and investigation_id.
    """
    logger.info(
        f"Processing investigation: investigation_id={investigation_id}, "
        f"tenant_id={tenant_id}, worker_id={WORKER_ID}"
    )

    # TODO: Full implementation in fn-10.5
    # - Load/create job record
    # - Reconstruct adapter (fn-10.6)
    # - Run workflow with checkpointing (fn-10.4)
    # - Update job status

    return {
        "status": "complete",
        "investigation_id": investigation_id,
        "worker_id": WORKER_ID,
    }


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
