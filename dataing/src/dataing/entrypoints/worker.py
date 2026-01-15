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
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from arq import Worker
from opentelemetry.trace import SpanKind

from dataing.adapters.context.engine import ContextEngine
from dataing.adapters.datasource import create_adapter_for_datasource
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.investigation_repository import PostgresInvestigationRepository
from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository
from dataing.agents.client import AgentClient
from dataing.core.investigation.flow import (
    AwaitingUserInput,
    InvestigationCancelled,
    InvestigationError,
    WorkerShutdownError,
    build_investigation_workflow,
    run_with_checkpointing,
)
from dataing.core.investigation.values import StepType, VersionId
from dataing.core.json_utils import to_json_string
from dataing.core.queue import INVESTIGATIONS_QUEUE, get_redis_settings
from dataing.telemetry import (
    get_tracer,
    init_metrics,
    init_telemetry,
    record_investigation_completed,
    record_queue_wait_time,
    restore_trace_context,
)

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
    trace_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute an investigation workflow with proper trace context restoration.

    This is the main job handler. Supports both root jobs and branch jobs
    (child jobs created from BRANCH signal).

    Args:
        ctx: Worker context containing database connection and other resources.
        investigation_id: UUID of the investigation to process.
        tenant_id: UUID of the tenant owning the investigation.
        datasource_id: Optional specific datasource ID to use.
        parent_job_id: Parent job ID if this is a branch job.
        branch_spec: BranchSpec data if this is a branch job.
        trace_context: Optional trace context from queue for distributed tracing.

    Returns:
        Dictionary with job result status and investigation_id.
    """
    tracer = get_tracer("dataing.worker")

    # Extract parent context from queue payload for proper span linking
    parent_ctx = None
    enqueued_at: datetime | None = None
    correlation_id: str | None = None

    if trace_context:
        # Restore W3C trace context (creates proper parent link)
        parent_ctx = restore_trace_context(trace_context)
        if trace_context.get("enqueued_at"):
            enqueued_at = datetime.fromisoformat(trace_context["enqueued_at"])
        correlation_id = trace_context.get("correlation_id")

    # Calculate queue wait time for SLOs
    worker_start = datetime.now(UTC)
    if enqueued_at:
        queue_wait_seconds = (worker_start - enqueued_at).total_seconds()
        record_queue_wait_time(queue_wait_seconds)
        logger.info(f"Queue wait time: {queue_wait_seconds:.3f}s")

    is_branch = parent_job_id is not None
    logger.info(
        f"Processing investigation: investigation_id={investigation_id}, "
        f"tenant_id={tenant_id}, worker_id={WORKER_ID}, "
        f"is_branch={is_branch}, parent_job_id={parent_job_id}, "
        f"correlation_id={correlation_id}"
    )

    db: AppDatabase = ctx["db"]
    inv_uuid = UUID(investigation_id)

    # Get the job record
    job = await db.get_investigation_job(inv_uuid)
    if not job:
        logger.error(f"No job found for investigation: {investigation_id}")
        return {
            "status": "failed",
            "investigation_id": investigation_id,
            "worker_id": WORKER_ID,
            "error": "Job not found",
        }

    job_id = job["id"]

    # Check for cancellation before starting
    if job.get("status") == "cancelling":
        logger.info(f"Job already cancelled: job_id={job_id}")
        await db.mark_job_cancelled(job_id)
        await db.execute(
            """
            UPDATE investigations
            SET outcome = $1
            WHERE id = $2
            """,
            to_json_string({"status": "cancelled", "reason": "User cancelled before execution"}),
            inv_uuid,
        )
        return {
            "status": "cancelled",
            "investigation_id": investigation_id,
            "worker_id": WORKER_ID,
        }

    # Mark job as running
    await db.update_job_status(job_id, status="running", current_step="starting")

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
            await db.update_job_status(job_id, status="failed")
            return {
                "status": "failed",
                "investigation_id": investigation_id,
                "worker_id": WORKER_ID,
                "error": str(e),
            }

    # Get workflow dependencies from context
    repository: PostgresInvestigationRepository = ctx["repository"]
    agent_client: AgentClient | None = ctx["agent_client"]
    pattern_repository: InMemoryPatternRepository = ctx["pattern_repository"]
    context_engine: ContextEngine = ctx["context_engine"]

    if not agent_client:
        logger.error("AgentClient not available - cannot run workflow")
        await db.update_job_status(job_id, status="failed")
        return {
            "status": "failed",
            "investigation_id": investigation_id,
            "worker_id": WORKER_ID,
            "error": "ANTHROPIC_API_KEY not configured",
        }

    # Load investigation and current state
    investigation = await repository.get_investigation(inv_uuid)
    if not investigation or not investigation.main_branch_id:
        logger.error(f"Investigation or main branch not found: {investigation_id}")
        await db.update_job_status(job_id, status="failed")
        return {
            "status": "failed",
            "investigation_id": investigation_id,
            "worker_id": WORKER_ID,
            "error": "Investigation or main branch not found",
        }

    main_branch = await repository.get_branch(investigation.main_branch_id)
    if not main_branch or not main_branch.head_snapshot_id:
        logger.error(f"Main branch or snapshot not found: {investigation.main_branch_id}")
        await db.update_job_status(job_id, status="failed")
        return {
            "status": "failed",
            "investigation_id": investigation_id,
            "worker_id": WORKER_ID,
            "error": "Main branch or snapshot not found",
        }

    snapshot = await repository.get_snapshot(main_branch.head_snapshot_id)
    if not snapshot:
        logger.error(f"Snapshot not found: {main_branch.head_snapshot_id}")
        await db.update_job_status(job_id, status="failed")
        return {
            "status": "failed",
            "investigation_id": investigation_id,
            "worker_id": WORKER_ID,
            "error": "Snapshot not found",
        }

    # Build the workflow
    workflow = build_investigation_workflow(
        context_engine=context_engine,
        llm=agent_client,
        database=adapter,
        pattern_repository=pattern_repository,
    )

    # Checkpoint callback - saves state after each step
    async def on_step_complete(
        context: Any, next_step: str | None, step_cursor: dict[str, Any] | None = None
    ) -> None:
        """Save checkpoint after each step completes."""
        step_type = StepType(next_step) if next_step else StepType.COMPLETE
        new_snapshot = await repository.create_snapshot(
            investigation_id=inv_uuid,
            branch_id=main_branch.id,
            version=VersionId(
                major=snapshot.version.major,
                minor=snapshot.version.minor,
                patch=snapshot.version.patch + 1,
            ),
            step=step_type,
            context=context,
            parent_snapshot_id=snapshot.id,
            trigger="worker",
            step_cursor=step_cursor,
        )
        await repository.update_branch_head(main_branch.id, new_snapshot.id)
        await db.update_job_status(
            job_id,
            status="running",
            current_step=step_type.value,
            checkpoint=step_cursor, # Also store in job record for easy inspection
        )

        # Check for cancellation at step boundaries
        if await check_cancellation(db, job_id):
            raise InvestigationCancelled()

        logger.info(f"Checkpoint saved: step={step_type.value}, snapshot={new_snapshot.id}")

    # Create consumer span linked to producer span from API
    with tracer.start_as_current_span(
        "investigation.process",
        context=parent_ctx,  # Links to parent span from queue producer
        kind=SpanKind.CONSUMER,
        attributes={
            # Safe attributes only - no PII
            "investigation.id": investigation_id,
            "tenant.id": tenant_id,
            "worker.id": WORKER_ID,
            "job.is_branch": is_branch,
            "correlation_id": correlation_id or "",
            "messaging.system": "redis",
            "messaging.operation": "process",
        },
    ) as job_span:
        async with AsyncExitStack() as stack:
            if adapter:
                await stack.enter_async_context(adapter)

            # Run the workflow
            try:
                final_context = await run_with_checkpointing(
                    workflow=workflow,
                    context=snapshot.context,
                    start_step=snapshot.step.value,
                    on_step_complete=on_step_complete,
                    shutdown_signal=shutdown_event,
                    start_cursor=snapshot.step_cursor,
                    max_iterations=50,
                )

                # Workflow completed successfully
                job_span.set_attribute("investigation.status", "completed")
                outcome = {
                    "status": "completed",
                    "synthesis": final_context.current_synthesis,
                    "evidence_count": len(final_context.evidence),
                    "queries_executed": final_context.total_queries_executed,
                }
                await repository.update_investigation_outcome(inv_uuid, outcome)
                await db.update_job_status(job_id, status="completed")
                record_investigation_completed("completed")
                logger.info(f"Investigation completed: {investigation_id}")

                # Record E2E duration from enqueue to completion
                if enqueued_at:
                    e2e_duration = (datetime.now(UTC) - enqueued_at).total_seconds()
                    job_span.set_attribute("investigation.e2e_duration_seconds", e2e_duration)
                    logger.info(f"E2E duration: {e2e_duration:.3f}s")

                # If this is a branch job, check if parent can merge
                if is_branch and parent_job_id:
                    await check_and_trigger_merge(db, UUID(parent_job_id))

                return {
                    "status": "completed",
                    "investigation_id": investigation_id,
                    "worker_id": WORKER_ID,
                }

            except WorkerShutdownError:
                # Graceful shutdown - job will be retried
                job_span.set_attribute("investigation.status", "shutdown")
                logger.info(f"Worker shutdown, job checkpointed: {investigation_id}")
                await db.update_job_status(job_id, status="pending")
                return {
                    "status": "shutdown",
                    "investigation_id": investigation_id,
                    "worker_id": WORKER_ID,
                }

            except AwaitingUserInput as e:
                # Workflow paused for user input
                job_span.set_attribute("investigation.status", "awaiting_input")
                logger.info(
                    f"Awaiting user input: {investigation_id}, next_step={e.next_step}"
                )
                await db.update_job_status(
                    job_id, status="awaiting_input", current_step=e.next_step
                )
                return {
                    "status": "awaiting_input",
                    "investigation_id": investigation_id,
                    "worker_id": WORKER_ID,
                    "next_step": e.next_step,
                }

            except InvestigationCancelled:
                # User cancelled the investigation
                job_span.set_attribute("investigation.status", "cancelled")
                record_investigation_completed("cancelled")
                logger.info(f"Investigation cancelled: {investigation_id}")
                await db.mark_job_cancelled(job_id)
                await db.execute(
                    """
                                UPDATE investigations
                                SET outcome = $1
                                WHERE id = $2
                                """,
                    to_json_string({"status": "cancelled", "reason": "User cancelled"}),
                    inv_uuid,
                )
                return {
                    "status": "cancelled",
                    "investigation_id": investigation_id,
                    "worker_id": WORKER_ID,
                }

            except InvestigationError as e:
                # Workflow failed
                job_span.record_exception(e)
                job_span.set_attribute("investigation.status", "failed")
                record_investigation_completed("failed")
                logger.error(f"Investigation failed: {investigation_id}, error={e.error}")
                await db.update_job_status(job_id, status="failed")
                await db.execute(
                    """
                                UPDATE investigations
                                SET outcome = $1
                                WHERE id = $2
                                """,
                    to_json_string({"status": "failed", "error": e.error}),
                    inv_uuid,
                )

                if enqueued_at:
                    e2e_duration = (datetime.now(UTC) - enqueued_at).total_seconds()
                    job_span.set_attribute("investigation.e2e_duration_seconds", e2e_duration)

                return {
                    "status": "failed",
                    "investigation_id": investigation_id,
                    "worker_id": WORKER_ID,
                    "error": e.error,
                }

            except Exception as e:
                # Unexpected error
                job_span.record_exception(e)
                job_span.set_attribute("investigation.status", "failed")
                record_investigation_completed("failed")
                logger.exception(f"Unexpected error in investigation: {investigation_id}")
                await db.update_job_status(job_id, status="failed")
                await db.execute(
                    """
                                UPDATE investigations
                                SET outcome = $1
                                WHERE id = $2
                                """,
                    to_json_string({"status": "failed", "error": str(e)}),
                    inv_uuid,
                )

                if enqueued_at:
                    e2e_duration = (datetime.now(UTC) - enqueued_at).total_seconds()
                    job_span.set_attribute("investigation.e2e_duration_seconds", e2e_duration)

                return {
                    "status": "failed",
                    "investigation_id": investigation_id,
                    "worker_id": WORKER_ID,
                    "error": str(e),
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
    status: str | None = await db.get_job_status(job_id)
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
    await db.mark_job_cancelled(job_id)
    logger.info(f"Job cancelled: job_id={job_id}")
    raise InvestigationCancelled()


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize worker resources on startup.

    Sets up database connection, LLM client, telemetry, and signal handlers.

    Args:
        ctx: Worker context dictionary to populate with resources.
    """
    # Initialize OpenTelemetry SDK and metrics (idempotent)
    init_telemetry()
    init_metrics()

    logger.info(f"Worker starting: worker_id={WORKER_ID}")

    # Initialize database connection
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/dataing")
    app_database_url = os.getenv("APP_DATABASE_URL", database_url)

    db = AppDatabase(app_database_url)
    await db.connect()
    ctx["db"] = db
    ctx["worker_id"] = WORKER_ID
    ctx["shutdown_event"] = shutdown_event

    # Initialize investigation repository
    ctx["repository"] = PostgresInvestigationRepository(db)

    # Initialize LLM client (required for workflow steps)
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_api_key:
        ctx["agent_client"] = AgentClient(api_key=anthropic_api_key)
        logger.info("AgentClient initialized")
    else:
        logger.warning("ANTHROPIC_API_KEY not set - workflow execution will fail")
        ctx["agent_client"] = None

    # Initialize pattern repository (in-memory for now)
    ctx["pattern_repository"] = InMemoryPatternRepository()

    # Initialize context engine
    ctx["context_engine"] = ContextEngine()

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

    # Pass settings as keyword arguments - Worker expects explicit params, not a class
    Worker(
        functions=WorkerSettings.functions,
        queue_name=WorkerSettings.queue_name,
        redis_settings=WorkerSettings.redis_settings,
        on_startup=WorkerSettings.on_startup,
        on_shutdown=WorkerSettings.on_shutdown,
        max_jobs=WorkerSettings.max_jobs,
        job_timeout=WorkerSettings.job_timeout,
        keep_result_forever=False,
        health_check_interval=WorkerSettings.health_check_interval,
        handle_signals=WorkerSettings.handle_signals,
        retry_jobs=WorkerSettings.retry_jobs,
    ).run()


if __name__ == "__main__":
    main()
