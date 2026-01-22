"""Unit tests for InvestigationQueue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from dataing.adapters.queue.investigation_queue import (
    InvestigationJob,
    InvestigationQueue,
    InvestigationQueueConfig,
    JobStatus,
)


class TestInvestigationJob:
    """Tests for InvestigationJob."""

    def test_job_to_dict(self) -> None:
        """Test job serialization."""
        job = InvestigationJob(
            job_id="job-123",
            team_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            issue_id=uuid.uuid4(),
            datasource_id=uuid.uuid4(),
            alert_data={"type": "test"},
            alert_summary="Test alert",
            priority=5,
        )

        data = job.to_dict()

        assert data["job_id"] == "job-123"
        assert data["priority"] == 5
        assert data["alert_data"] == {"type": "test"}
        assert data["retry_count"] == 0

    def test_job_from_dict(self) -> None:
        """Test job deserialization."""
        team_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        issue_id = uuid.uuid4()
        datasource_id = uuid.uuid4()
        now = datetime.now(UTC)

        data = {
            "job_id": "job-456",
            "team_id": str(team_id),
            "tenant_id": str(tenant_id),
            "issue_id": str(issue_id),
            "datasource_id": str(datasource_id),
            "alert_data": {"severity": "high"},
            "alert_summary": "High severity alert",
            "priority": 10,
            "retry_count": 2,
            "max_retries": 5,
            "created_at": now.isoformat(),
            "next_retry_at": None,
        }

        job = InvestigationJob.from_dict(data)

        assert job.job_id == "job-456"
        assert job.team_id == team_id
        assert job.priority == 10
        assert job.retry_count == 2

    def test_job_defaults(self) -> None:
        """Test job default values."""
        job = InvestigationJob(
            job_id="job-789",
            team_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            issue_id=uuid.uuid4(),
            datasource_id=uuid.uuid4(),
            alert_data={},
            alert_summary="",
        )

        assert job.priority == 0
        assert job.retry_count == 0
        assert job.max_retries == 3


class TestInvestigationQueue:
    """Tests for InvestigationQueue."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create a mock Redis client."""
        mock = AsyncMock()
        # Set up default return values
        mock.set = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.zadd = AsyncMock()
        mock.zrange = AsyncMock(return_value=[])
        mock.zrem = AsyncMock()
        mock.sadd = AsyncMock()
        mock.smembers = AsyncMock(return_value=set())
        mock.zcard = AsyncMock(return_value=0)
        mock.srem = AsyncMock()
        mock.expire = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def queue(self, mock_redis: AsyncMock) -> InvestigationQueue:
        """Create a queue with mock Redis."""
        return InvestigationQueue(mock_redis, InvestigationQueueConfig())

    @pytest.fixture
    def sample_job(self) -> InvestigationJob:
        """Create a sample job."""
        return InvestigationJob(
            job_id="test-job-1",
            team_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            issue_id=uuid.uuid4(),
            datasource_id=uuid.uuid4(),
            alert_data={"test": "data"},
            alert_summary="Test alert",
            priority=5,
        )

    async def test_enqueue_stores_job(
        self, queue: InvestigationQueue, mock_redis: AsyncMock, sample_job: InvestigationJob
    ) -> None:
        """Test that enqueue stores job data."""
        await queue.enqueue(sample_job)

        # Verify job data was stored
        mock_redis.set.assert_called()
        # Verify status was set to pending
        calls = mock_redis.set.call_args_list
        assert any(JobStatus.PENDING.value in str(call) for call in calls)
        # Verify added to team queue
        mock_redis.zadd.assert_called()
        # Verify team tracked
        mock_redis.sadd.assert_called()

    async def test_dequeue_returns_jobs(
        self, queue: InvestigationQueue, mock_redis: AsyncMock, sample_job: InvestigationJob
    ) -> None:
        """Test that dequeue returns jobs."""
        import json

        # Set up mock to return job
        mock_redis.zrange.return_value = [sample_job.job_id]
        mock_redis.get.return_value = json.dumps(sample_job.to_dict())

        jobs = await queue.dequeue(sample_job.team_id, batch_size=1)

        assert len(jobs) == 1
        assert jobs[0].job_id == sample_job.job_id
        # Verify job was removed from queue
        mock_redis.zrem.assert_called()

    async def test_dequeue_marks_as_processing(
        self, queue: InvestigationQueue, mock_redis: AsyncMock, sample_job: InvestigationJob
    ) -> None:
        """Test that dequeue marks jobs as processing."""
        import json

        mock_redis.zrange.return_value = [sample_job.job_id]
        mock_redis.get.return_value = json.dumps(sample_job.to_dict())

        await queue.dequeue(sample_job.team_id, batch_size=1)

        # Verify status was set to processing
        calls = mock_redis.set.call_args_list
        assert any(JobStatus.PROCESSING.value in str(call) for call in calls)

    async def test_complete_marks_job_done(
        self, queue: InvestigationQueue, mock_redis: AsyncMock
    ) -> None:
        """Test that complete marks job as completed."""
        await queue.complete("test-job")

        # Verify status was set to completed
        calls = mock_redis.set.call_args_list
        assert any(JobStatus.COMPLETED.value in str(call) for call in calls)
        # Verify expiry was set
        mock_redis.expire.assert_called()

    async def test_fail_retries_job(
        self, queue: InvestigationQueue, mock_redis: AsyncMock, sample_job: InvestigationJob
    ) -> None:
        """Test that fail schedules retry when retries remain."""
        import json

        mock_redis.get.return_value = json.dumps(sample_job.to_dict())

        await queue.fail(sample_job, "Test error")

        # Verify retry count incremented
        assert sample_job.retry_count == 1
        # Verify status set to retrying
        calls = mock_redis.set.call_args_list
        assert any(JobStatus.RETRYING.value in str(call) for call in calls)
        # Verify added to retry queue
        mock_redis.zadd.assert_called()

    async def test_fail_permanent_after_max_retries(
        self, queue: InvestigationQueue, mock_redis: AsyncMock, sample_job: InvestigationJob
    ) -> None:
        """Test that fail marks as failed after max retries."""
        sample_job.retry_count = sample_job.max_retries

        await queue.fail(sample_job, "Final error")

        # Verify status set to failed
        calls = mock_redis.set.call_args_list
        assert any(JobStatus.FAILED.value in str(call) for call in calls)

    async def test_get_status(self, queue: InvestigationQueue, mock_redis: AsyncMock) -> None:
        """Test getting job status."""
        mock_redis.get.return_value = JobStatus.PROCESSING.value

        status = await queue.get_status("test-job")

        assert status == JobStatus.PROCESSING

    async def test_get_status_not_found(
        self, queue: InvestigationQueue, mock_redis: AsyncMock
    ) -> None:
        """Test getting status for nonexistent job."""
        mock_redis.get.return_value = None

        status = await queue.get_status("nonexistent")

        assert status is None

    async def test_get_queue_length(self, queue: InvestigationQueue, mock_redis: AsyncMock) -> None:
        """Test getting queue length for a team."""
        mock_redis.zcard.return_value = 5
        team_id = uuid.uuid4()

        length = await queue.get_queue_length(team_id)

        assert length == 5

    async def test_get_active_teams(self, queue: InvestigationQueue, mock_redis: AsyncMock) -> None:
        """Test getting active teams."""
        team1 = uuid.uuid4()
        team2 = uuid.uuid4()
        mock_redis.smembers.return_value = {str(team1), str(team2)}

        teams = await queue.get_active_teams()

        assert len(teams) == 2
        assert team1 in teams
        assert team2 in teams


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.RETRYING.value == "retrying"
