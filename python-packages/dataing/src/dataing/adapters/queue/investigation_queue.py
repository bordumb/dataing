"""Redis-backed investigation queue with per-team routing.

This module provides a queue for investigation jobs with:
- Per-team job queuing
- Priority support
- Retry handling with exponential backoff
- Job status tracking
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger()


class JobStatus(str, Enum):
    """Status of an investigation job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class InvestigationJob:
    """An investigation job to be processed."""

    job_id: str
    team_id: UUID
    tenant_id: UUID
    issue_id: UUID
    datasource_id: UUID
    alert_data: dict[str, Any]
    alert_summary: str
    priority: int = 0  # Higher = more urgent
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    next_retry_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize job to dictionary."""
        return {
            "job_id": self.job_id,
            "team_id": str(self.team_id),
            "tenant_id": str(self.tenant_id),
            "issue_id": str(self.issue_id),
            "datasource_id": str(self.datasource_id),
            "alert_data": self.alert_data,
            "alert_summary": self.alert_summary,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat(),
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InvestigationJob:
        """Deserialize job from dictionary."""
        return cls(
            job_id=data["job_id"],
            team_id=UUID(data["team_id"]),
            tenant_id=UUID(data["tenant_id"]),
            issue_id=UUID(data["issue_id"]),
            datasource_id=UUID(data["datasource_id"]),
            alert_data=data["alert_data"],
            alert_summary=data["alert_summary"],
            priority=data.get("priority", 0),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            created_at=datetime.fromisoformat(data["created_at"]),
            next_retry_at=(
                datetime.fromisoformat(data["next_retry_at"]) if data.get("next_retry_at") else None
            ),
        )


@dataclass
class InvestigationQueueConfig:
    """Configuration for the investigation queue."""

    key_prefix: str = "dataing:investigation_queue"
    default_batch_size: int = 5
    max_retry_delay_seconds: int = 300  # 5 minutes max


class InvestigationQueue:
    """Redis-backed investigation queue with per-team routing."""

    def __init__(
        self,
        redis: Redis,
        config: InvestigationQueueConfig | None = None,
    ) -> None:
        """Initialize the investigation queue."""
        self.redis = redis
        self.config = config or InvestigationQueueConfig()

    def _team_queue_key(self, team_id: UUID) -> str:
        """Get the queue key for a team."""
        return f"{self.config.key_prefix}:team:{team_id}"

    def _job_key(self, job_id: str) -> str:
        """Get the key for job data."""
        return f"{self.config.key_prefix}:job:{job_id}"

    def _status_key(self, job_id: str) -> str:
        """Get the key for job status."""
        return f"{self.config.key_prefix}:status:{job_id}"

    def _retry_queue_key(self) -> str:
        """Get the retry queue key (sorted set by retry time)."""
        return f"{self.config.key_prefix}:retry"

    def _teams_set_key(self) -> str:
        """Get the key for tracking active teams."""
        return f"{self.config.key_prefix}:teams"

    async def enqueue(self, job: InvestigationJob) -> None:
        """Add an investigation job to the team's queue.

        Jobs are stored in a per-team list and sorted by priority.
        """
        team_queue_key = self._team_queue_key(job.team_id)
        job_key = self._job_key(job.job_id)
        status_key = self._status_key(job.job_id)

        # Store job data
        job_json = json.dumps(job.to_dict())
        await self.redis.set(job_key, job_json)

        # Set initial status
        await self.redis.set(status_key, JobStatus.PENDING.value)

        # Add to team queue (using sorted set with priority as score)
        # Negative priority so higher priority jobs are first
        await self.redis.zadd(team_queue_key, {job.job_id: -job.priority})

        # Track this team
        await self.redis.sadd(  # type: ignore[misc]
            self._teams_set_key(), str(job.team_id)
        )

        logger.debug(
            "job_enqueued",
            job_id=job.job_id,
            team_id=str(job.team_id),
            priority=job.priority,
        )

    async def dequeue(
        self,
        team_id: UUID,
        batch_size: int | None = None,
    ) -> list[InvestigationJob]:
        """Dequeue a batch of jobs for a team.

        Returns up to batch_size jobs, marking them as processing.
        """
        if batch_size is None:
            batch_size = self.config.default_batch_size

        team_queue_key = self._team_queue_key(team_id)
        jobs: list[InvestigationJob] = []

        # Get job IDs from sorted set (highest priority first)
        job_ids = await self.redis.zrange(team_queue_key, 0, batch_size - 1)

        for job_id_bytes in job_ids:
            job_id = job_id_bytes.decode() if isinstance(job_id_bytes, bytes) else job_id_bytes

            # Get job data
            job_key = self._job_key(job_id)
            job_json = await self.redis.get(job_key)

            if not job_json:
                # Job data missing, remove from queue
                await self.redis.zrem(team_queue_key, job_id)
                continue

            job_data = json.loads(job_json)
            job = InvestigationJob.from_dict(job_data)

            # Mark as processing
            status_key = self._status_key(job_id)
            await self.redis.set(status_key, JobStatus.PROCESSING.value)

            # Remove from queue
            await self.redis.zrem(team_queue_key, job_id)

            jobs.append(job)

        if jobs:
            logger.debug(
                "jobs_dequeued",
                team_id=str(team_id),
                count=len(jobs),
            )

        return jobs

    async def complete(self, job_id: str) -> None:
        """Mark a job as completed."""
        status_key = self._status_key(job_id)
        job_key = self._job_key(job_id)

        await self.redis.set(status_key, JobStatus.COMPLETED.value)

        # Clean up after a delay (optional: could keep for auditing)
        await self.redis.expire(job_key, 3600)  # 1 hour
        await self.redis.expire(status_key, 3600)

        logger.debug("job_completed", job_id=job_id)

    async def fail(self, job: InvestigationJob, error: str) -> None:
        """Mark a job as failed. Will retry if retries remain."""
        job_key = self._job_key(job.job_id)
        status_key = self._status_key(job.job_id)

        job.retry_count += 1

        if job.retry_count <= job.max_retries:
            # Calculate backoff delay (exponential: 2^n seconds, capped)
            delay = min(
                2**job.retry_count,
                self.config.max_retry_delay_seconds,
            )
            job.next_retry_at = datetime.now(UTC).replace(microsecond=0) + __import__(
                "datetime"
            ).timedelta(seconds=delay)

            # Update job data
            job_json = json.dumps(job.to_dict())
            await self.redis.set(job_key, job_json)

            # Set status to retrying
            await self.redis.set(status_key, JobStatus.RETRYING.value)

            # Add to retry queue (sorted set by retry time)
            retry_time = job.next_retry_at.timestamp()
            await self.redis.zadd(self._retry_queue_key(), {job.job_id: retry_time})

            logger.info(
                "job_scheduled_for_retry",
                job_id=job.job_id,
                retry_count=job.retry_count,
                next_retry_at=job.next_retry_at.isoformat(),
                error=error,
            )
        else:
            # Max retries exceeded
            await self.redis.set(status_key, JobStatus.FAILED.value)
            await self.redis.expire(job_key, 86400)  # Keep for 24 hours
            await self.redis.expire(status_key, 86400)

            logger.error(
                "job_failed_permanently",
                job_id=job.job_id,
                retry_count=job.retry_count,
                error=error,
            )

    async def process_retries(self) -> list[InvestigationJob]:
        """Get jobs that are ready for retry and re-enqueue them.

        Returns the jobs that were moved back to their team queues.
        """
        retry_queue_key = self._retry_queue_key()
        now = time.time()

        # Get jobs with retry time <= now
        job_ids = await self.redis.zrangebyscore(retry_queue_key, 0, now)

        jobs: list[InvestigationJob] = []
        for job_id_bytes in job_ids:
            job_id = job_id_bytes.decode() if isinstance(job_id_bytes, bytes) else job_id_bytes

            # Get job data
            job_key = self._job_key(job_id)
            job_json = await self.redis.get(job_key)

            if not job_json:
                # Job data missing, remove from retry queue
                await self.redis.zrem(retry_queue_key, job_id)
                continue

            job_data = json.loads(job_json)
            job = InvestigationJob.from_dict(job_data)

            # Remove from retry queue
            await self.redis.zrem(retry_queue_key, job_id)

            # Re-enqueue to team queue
            team_queue_key = self._team_queue_key(job.team_id)
            await self.redis.zadd(team_queue_key, {job.job_id: -job.priority})

            # Update status
            status_key = self._status_key(job.job_id)
            await self.redis.set(status_key, JobStatus.PENDING.value)

            jobs.append(job)

            logger.debug(
                "job_retry_requeued",
                job_id=job.job_id,
                team_id=str(job.team_id),
            )

        return jobs

    async def get_status(self, job_id: str) -> JobStatus | None:
        """Get the status of a job."""
        status_key = self._status_key(job_id)
        status = await self.redis.get(status_key)
        if status:
            status_str = status.decode() if isinstance(status, bytes) else status
            return JobStatus(status_str)
        return None

    async def get_queue_length(self, team_id: UUID) -> int:
        """Get the number of pending jobs for a team."""
        team_queue_key = self._team_queue_key(team_id)
        count: int = await self.redis.zcard(team_queue_key)
        return count

    async def get_active_teams(self) -> list[UUID]:
        """Get list of teams with pending jobs."""
        teams_key = self._teams_set_key()
        team_ids: set[Any] = await self.redis.smembers(  # type: ignore[misc]
            teams_key
        )
        return [UUID(t.decode() if isinstance(t, bytes) else t) for t in team_ids]

    async def cleanup_empty_teams(self) -> None:
        """Remove teams with no pending jobs from the active set."""
        teams = await self.get_active_teams()
        for team_id in teams:
            queue_length: int = await self.redis.zcard(self._team_queue_key(team_id))
            if queue_length == 0:
                await self.redis.srem(  # type: ignore[misc]
                    self._teams_set_key(), str(team_id)
                )
