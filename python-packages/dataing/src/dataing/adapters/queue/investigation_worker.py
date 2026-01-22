"""Investigation queue worker that processes jobs and starts Temporal workflows.

This worker:
- Polls teams with pending jobs
- Respects per-team rate limits
- Processes jobs in batches
- Starts Temporal workflows for each job
- Handles failures with retry
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from dataing.adapters.queue.investigation_queue import (
    InvestigationJob,
    InvestigationQueue,
)
from dataing.adapters.queue.redis_rate_limiter import RedisRateLimiter
from dataing.services.policy import PolicyService, QueueConfig

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from dataing.adapters.db.app_db import AppDatabase
    from dataing.temporal.client import TemporalInvestigationClient

logger = structlog.get_logger()


@dataclass
class WorkerConfig:
    """Configuration for the investigation worker."""

    poll_interval_seconds: float = 1.0
    retry_poll_interval_seconds: float = 5.0
    max_concurrent_teams: int = 10
    default_batch_size: int = 5


class InvestigationWorker:
    """Worker that processes investigation jobs from the queue."""

    def __init__(
        self,
        queue: InvestigationQueue,
        rate_limiter: RedisRateLimiter,
        temporal_client: TemporalInvestigationClient,
        db: AppDatabase,
        config: WorkerConfig | None = None,
    ) -> None:
        """Initialize the worker."""
        self.queue = queue
        self.rate_limiter = rate_limiter
        self.temporal_client = temporal_client
        self.db = db
        self.config = config or WorkerConfig()
        self._running = False
        self._policy_service = PolicyService(db)
        self._team_configs: dict[UUID, QueueConfig] = {}

    async def _get_queue_config(self, team_id: UUID) -> QueueConfig:
        """Get queue configuration for a team, with caching."""
        if team_id not in self._team_configs:
            config = await self._policy_service.get_queue_config(team_id)
            self._team_configs[team_id] = config
        return self._team_configs[team_id]

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        logger.info("investigation_worker_started")

        # Start both the main loop and retry processor
        await asyncio.gather(
            self._main_loop(),
            self._retry_loop(),
        )

    async def stop(self) -> None:
        """Stop the worker loop."""
        self._running = False
        logger.info("investigation_worker_stopped")

    async def _main_loop(self) -> None:
        """Main worker loop that processes jobs."""
        while self._running:
            try:
                # Get teams with pending jobs
                teams = await self.queue.get_active_teams()

                if teams:
                    # Process teams concurrently, up to max_concurrent_teams
                    tasks = []
                    for team_id in teams[: self.config.max_concurrent_teams]:
                        tasks.append(self._process_team(team_id))

                    await asyncio.gather(*tasks, return_exceptions=True)

                # Clean up teams with no jobs
                await self.queue.cleanup_empty_teams()

            except Exception as e:
                logger.error("worker_loop_error", error=str(e))

            await asyncio.sleep(self.config.poll_interval_seconds)

    async def _retry_loop(self) -> None:
        """Loop that re-queues jobs ready for retry."""
        while self._running:
            try:
                jobs = await self.queue.process_retries()
                if jobs:
                    logger.debug("retries_processed", count=len(jobs))
            except Exception as e:
                logger.error("retry_loop_error", error=str(e))

            await asyncio.sleep(self.config.retry_poll_interval_seconds)

    async def _process_team(self, team_id: UUID) -> None:
        """Process pending jobs for a team."""
        config = await self._get_queue_config(team_id)

        # Check rate limit
        rate_result = await self.rate_limiter.check_and_consume(
            team_id,
            config,
            tokens=config.batch_size,
        )

        if not rate_result.allowed:
            logger.debug(
                "team_rate_limited",
                team_id=str(team_id),
                retry_after=rate_result.retry_after,
            )
            return

        # Dequeue jobs
        jobs = await self.queue.dequeue(team_id, batch_size=config.batch_size)

        if not jobs:
            return

        # Process jobs concurrently
        tasks = []
        for job in jobs:
            tasks.append(self._process_job(job))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log results
        successful = sum(1 for r in results if r is True)
        failed = len(results) - successful

        logger.info(
            "team_jobs_processed",
            team_id=str(team_id),
            total=len(jobs),
            successful=successful,
            failed=failed,
        )

    async def _process_job(self, job: InvestigationJob) -> bool:
        """Process a single investigation job.

        Returns True if successful, False if failed.
        """
        try:
            # Start Temporal workflow
            await self.temporal_client.start_investigation(
                investigation_id=job.job_id,
                tenant_id=str(job.tenant_id),
                datasource_id=str(job.datasource_id),
                alert_data=job.alert_data,
                alert_summary=job.alert_summary,
            )

            # Mark as completed
            await self.queue.complete(job.job_id)

            logger.info(
                "job_workflow_started",
                job_id=job.job_id,
                team_id=str(job.team_id),
            )

            return True

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "job_workflow_failed",
                job_id=job.job_id,
                team_id=str(job.team_id),
                error=error_msg,
            )

            # Mark as failed (will retry if retries remain)
            await self.queue.fail(job, error_msg)

            return False

    def clear_config_cache(self, team_id: UUID | None = None) -> None:
        """Clear cached queue configurations.

        Args:
            team_id: Team to clear config for. If None, clears all.
        """
        if team_id:
            self._team_configs.pop(team_id, None)
        else:
            self._team_configs.clear()


async def create_worker(
    redis: Redis,
    temporal_client: TemporalInvestigationClient,
    db: AppDatabase,
    config: WorkerConfig | None = None,
) -> InvestigationWorker:
    """Create and configure an investigation worker.

    Args:
        redis: Redis client connection.
        temporal_client: Temporal client for starting workflows.
        db: Database connection.
        config: Optional worker configuration.

    Returns:
        Configured InvestigationWorker.
    """
    queue = InvestigationQueue(redis)
    rate_limiter = RedisRateLimiter(redis)

    return InvestigationWorker(
        queue=queue,
        rate_limiter=rate_limiter,
        temporal_client=temporal_client,
        db=db,
        config=config,
    )
