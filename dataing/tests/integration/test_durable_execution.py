"""Integration tests for durable execution features.

These tests verify the integration between the queue module, worker,
and database components without requiring external Redis or Postgres.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from dataing.core.queue import (
    INVESTIGATIONS_QUEUE,
    enqueue_branch_jobs,
    enqueue_investigation,
)
from dataing.entrypoints.worker import (
    check_and_trigger_merge,
    handle_branch_signal,
    run_investigation,
)


class TestDurableExecutionIntegration:
    """Integration tests for the durable execution flow."""

    async def test_investigation_queued_with_correct_parameters(self) -> None:
        """Test that enqueue_investigation passes all parameters to arq."""
        mock_job = MagicMock()
        mock_job.job_id = "test-job-123"
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)
        mock_pool.close = AsyncMock()

        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        datasource_id = str(uuid4())

        with patch("dataing.core.queue.create_pool", return_value=mock_pool):
            job_id = await enqueue_investigation(
                investigation_id=investigation_id,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                priority=5,
            )

        assert job_id == "test-job-123"
        call_kwargs = mock_pool.enqueue_job.call_args.kwargs
        assert call_kwargs["investigation_id"] == investigation_id
        assert call_kwargs["tenant_id"] == tenant_id
        assert call_kwargs["datasource_id"] == datasource_id
        assert call_kwargs["_queue_name"] == INVESTIGATIONS_QUEUE
        mock_pool.close.assert_called_once()

    async def test_worker_reconstructs_adapter_from_datasource(self) -> None:
        """Test that worker reconstructs adapter using factory."""
        mock_db = AsyncMock()
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "PostgresAdapter"

        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        datasource_id = str(uuid4())

        ctx = {"db": mock_db}

        with patch(
            "dataing.entrypoints.worker.create_adapter_for_datasource",
            new_callable=AsyncMock,
            return_value=mock_adapter,
        ) as mock_create:
            result = await run_investigation(
                ctx,
                investigation_id=investigation_id,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
            )

        assert result["status"] == "complete"
        assert result["adapter_type"] == "PostgresAdapter"
        mock_create.assert_called_once()

    async def test_branch_creates_multiple_child_jobs(self) -> None:
        """Test that BRANCH signal creates child jobs and sets parent to awaiting_merge."""
        mock_db = AsyncMock()
        mock_db.create_child_job = AsyncMock()
        mock_db.set_job_awaiting_merge = AsyncMock()

        job_id = uuid4()
        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        branch_specs = [
            {"branch_id": "h1", "hypothesis": "Test hypothesis 1"},
            {"branch_id": "h2", "hypothesis": "Test hypothesis 2"},
            {"branch_id": "h3", "hypothesis": "Test hypothesis 3"},
        ]

        with patch(
            "dataing.core.queue.enqueue_branch_jobs",
            new_callable=AsyncMock,
            return_value=["j1", "j2", "j3"],
        ):
            result = await handle_branch_signal(
                db=mock_db,
                job_id=job_id,
                investigation_id=investigation_id,
                tenant_id=tenant_id,
                datasource_id=None,
                branch_specs=branch_specs,
            )

        assert result["status"] == "branched"
        assert result["children"] == 3
        assert mock_db.create_child_job.call_count == 3
        mock_db.set_job_awaiting_merge.assert_called_once_with(job_id)

    async def test_merge_triggered_after_all_children_complete(self) -> None:
        """Test that parent job is resumed when all children finish."""
        mock_db = AsyncMock()
        mock_db.get_pending_children_count = AsyncMock(return_value=0)
        mock_db.update_job_status = AsyncMock()

        parent_job_id = uuid4()

        triggered = await check_and_trigger_merge(mock_db, parent_job_id)

        assert triggered is True
        mock_db.update_job_status.assert_called_once_with(
            job_id=parent_job_id,
            status="pending",
            current_step="merge",
        )

    async def test_merge_not_triggered_with_pending_children(self) -> None:
        """Test that parent job stays in awaiting_merge when children pending."""
        mock_db = AsyncMock()
        mock_db.get_pending_children_count = AsyncMock(return_value=2)
        mock_db.update_job_status = AsyncMock()

        parent_job_id = uuid4()

        triggered = await check_and_trigger_merge(mock_db, parent_job_id)

        assert triggered is False
        mock_db.update_job_status.assert_not_called()

    async def test_branch_job_checks_merge_on_completion(self) -> None:
        """Test that completing branch job checks if parent can merge."""
        mock_db = AsyncMock()
        mock_db.get_pending_children_count = AsyncMock(return_value=1)  # Still pending
        mock_db.update_job_status = AsyncMock()

        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        parent_job_id = str(uuid4())

        ctx = {"db": mock_db}

        result = await run_investigation(
            ctx,
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            parent_job_id=parent_job_id,
            branch_spec={"branch_id": "test"},
        )

        assert result["status"] == "complete"
        assert result["is_branch"] is True
        mock_db.get_pending_children_count.assert_called_once()

    async def test_parallel_branch_enqueue(self) -> None:
        """Test that enqueue_branch_jobs creates multiple jobs."""
        mock_job = MagicMock()
        mock_job.job_id = "test-job"
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)
        mock_pool.close = AsyncMock()

        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        parent_job_id = str(uuid4())
        branch_specs = [
            {"branch_id": "b1"},
            {"branch_id": "b2"},
        ]

        with patch("dataing.core.queue.create_pool", return_value=mock_pool):
            job_ids = await enqueue_branch_jobs(
                investigation_id=investigation_id,
                tenant_id=tenant_id,
                parent_job_id=parent_job_id,
                datasource_id=None,
                branch_specs=branch_specs,
            )

        assert len(job_ids) == 2
        # enqueue_investigation is called twice (once per branch)
        assert mock_pool.enqueue_job.call_count == 2


class TestGracefulShutdownIntegration:
    """Integration tests for graceful shutdown behavior."""

    async def test_shutdown_event_propagates_to_worker(self) -> None:
        """Test that shutdown_event can be used to signal workers."""
        from dataing.entrypoints.worker import shutdown_event

        # Initially not set
        assert not shutdown_event.is_set()

        # Set signal
        shutdown_event.set()
        assert shutdown_event.is_set()

        # Clear for other tests
        shutdown_event.clear()

    async def test_worker_context_includes_shutdown_event(self) -> None:
        """Test that startup adds shutdown_event to context."""
        from dataing.entrypoints.worker import startup

        ctx: dict[str, Any] = {}

        with patch("dataing.entrypoints.worker.AppDatabase") as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value = mock_db

            await startup(ctx)

        assert "shutdown_event" in ctx
        assert isinstance(ctx["shutdown_event"], asyncio.Event)


class TestAdapterReconstructionIntegration:
    """Integration tests for adapter factory and worker interaction."""

    async def test_adapter_failure_returns_failed_status(self) -> None:
        """Test that adapter reconstruction failure is handled gracefully."""
        from dataing.adapters.datasource.errors import DatasourceNotFoundError

        mock_db = AsyncMock()
        ctx = {"db": mock_db}

        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        datasource_id = str(uuid4())

        with patch(
            "dataing.entrypoints.worker.create_adapter_for_datasource",
            new_callable=AsyncMock,
            side_effect=DatasourceNotFoundError(datasource_id),
        ):
            result = await run_investigation(
                ctx,
                investigation_id=investigation_id,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
            )

        assert result["status"] == "failed"
        assert "error" in result

    async def test_no_adapter_when_datasource_not_specified(self) -> None:
        """Test that worker works without datasource_id."""
        mock_db = AsyncMock()
        ctx = {"db": mock_db}

        investigation_id = str(uuid4())
        tenant_id = str(uuid4())

        with patch(
            "dataing.entrypoints.worker.create_adapter_for_datasource",
            new_callable=AsyncMock,
        ) as mock_create:
            result = await run_investigation(
                ctx,
                investigation_id=investigation_id,
                tenant_id=tenant_id,
                datasource_id=None,
            )

        assert result["status"] == "complete"
        assert result["adapter_type"] is None
        mock_create.assert_not_called()


class TestQueueServiceIntegration:
    """Integration tests for queue service components."""

    async def test_queue_uses_correct_queue_name(self) -> None:
        """Test that investigations go to the correct queue."""
        mock_job = MagicMock()
        mock_job.job_id = "test-123"
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)
        mock_pool.close = AsyncMock()

        with patch("dataing.core.queue.create_pool", return_value=mock_pool):
            await enqueue_investigation(
                investigation_id=str(uuid4()),
                tenant_id=str(uuid4()),
            )

        call_kwargs = mock_pool.enqueue_job.call_args.kwargs
        assert call_kwargs["_queue_name"] == "investigations"

    async def test_queue_cleanup_on_failure(self) -> None:
        """Test that queue connection is closed even on failure."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=None)  # Simulates failure
        mock_pool.close = AsyncMock()

        with (
            patch("dataing.core.queue.create_pool", return_value=mock_pool),
            pytest.raises(RuntimeError, match="Failed to enqueue"),
        ):
            await enqueue_investigation(
                investigation_id=str(uuid4()),
                tenant_id=str(uuid4()),
            )

        # Connection should still be closed
        mock_pool.close.assert_called_once()
