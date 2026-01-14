"""Tests for the worker entrypoint module."""

from __future__ import annotations

import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from dataing.core.queue import INVESTIGATIONS_QUEUE


class TestWorkerSettings:
    """Tests for WorkerSettings configuration."""

    def test_worker_settings_configured(self) -> None:
        """Test that WorkerSettings has expected configuration."""
        from dataing.entrypoints.worker import WorkerSettings

        assert WorkerSettings.max_jobs == 5
        assert WorkerSettings.job_timeout == 7200  # 2 hours
        assert WorkerSettings.job_completion_wait == 30  # 30 seconds grace period
        assert WorkerSettings.retry_jobs is False
        assert WorkerSettings.handle_signals is True
        assert WorkerSettings.queue_name == INVESTIGATIONS_QUEUE

    def test_worker_has_run_investigation_function(self) -> None:
        """Test that run_investigation is registered as a job function."""
        from dataing.entrypoints.worker import WorkerSettings, run_investigation

        assert run_investigation in WorkerSettings.functions


class TestWorkerLifecycle:
    """Tests for worker startup and shutdown."""

    async def test_startup_creates_db_connection(self) -> None:
        """Test that startup initializes database connection."""
        from dataing.entrypoints.worker import startup

        ctx: dict = {}

        with patch("dataing.entrypoints.worker.AppDatabase") as MockDB:
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance

            await startup(ctx)

            assert "db" in ctx
            assert ctx["db"] == mock_db_instance
            mock_db_instance.connect.assert_called_once()

    async def test_startup_sets_worker_id(self) -> None:
        """Test that startup sets worker_id in context."""
        from dataing.entrypoints.worker import startup

        ctx: dict = {}

        with patch("dataing.entrypoints.worker.AppDatabase") as MockDB:
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance

            await startup(ctx)

            assert "worker_id" in ctx
            # Worker ID should be a UUID string
            assert len(ctx["worker_id"]) == 36

    async def test_startup_sets_shutdown_event(self) -> None:
        """Test that startup sets shutdown_event in context."""
        from dataing.entrypoints.worker import startup

        ctx: dict = {}

        with patch("dataing.entrypoints.worker.AppDatabase") as MockDB:
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance

            await startup(ctx)

            assert "shutdown_event" in ctx
            assert isinstance(ctx["shutdown_event"], asyncio.Event)

    async def test_shutdown_closes_db(self) -> None:
        """Test that shutdown closes database connection."""
        from dataing.entrypoints.worker import shutdown

        mock_db = AsyncMock()
        ctx = {"db": mock_db}

        await shutdown(ctx)

        mock_db.close.assert_called_once()

    async def test_shutdown_without_db(self) -> None:
        """Test that shutdown handles missing db gracefully."""
        from dataing.entrypoints.worker import shutdown

        ctx: dict = {}

        # Should not raise
        await shutdown(ctx)


class TestRunInvestigation:
    """Tests for the run_investigation job handler."""

    async def test_returns_complete_status(self) -> None:
        """Test that run_investigation returns completion status."""
        from dataing.entrypoints.worker import WORKER_ID, run_investigation

        mock_db = AsyncMock()
        ctx = {"db": mock_db}
        investigation_id = str(uuid4())
        tenant_id = str(uuid4())

        result = await run_investigation(
            ctx,
            investigation_id=investigation_id,
            tenant_id=tenant_id,
        )

        assert result["status"] == "complete"
        assert result["investigation_id"] == investigation_id
        assert result["worker_id"] == WORKER_ID

    async def test_with_datasource_reconstructs_adapter(self) -> None:
        """Test that run_investigation reconstructs adapter when datasource_id provided."""
        from dataing.entrypoints.worker import run_investigation

        mock_db = AsyncMock()
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "PostgresAdapter"

        ctx = {"db": mock_db}
        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        datasource_id = str(uuid4())

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

            mock_create.assert_called_once()
            assert result["adapter_type"] == "PostgresAdapter"
            assert result["status"] == "complete"

    async def test_without_datasource_no_adapter(self) -> None:
        """Test that run_investigation works without datasource_id."""
        from dataing.entrypoints.worker import run_investigation

        mock_db = AsyncMock()
        ctx = {"db": mock_db}
        investigation_id = str(uuid4())
        tenant_id = str(uuid4())

        result = await run_investigation(
            ctx,
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            datasource_id=None,
        )

        assert result["adapter_type"] is None
        assert result["status"] == "complete"

    async def test_adapter_failure_returns_failed_status(self) -> None:
        """Test that adapter reconstruction failure returns failed status."""
        from dataing.entrypoints.worker import run_investigation

        mock_db = AsyncMock()
        ctx = {"db": mock_db}
        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        datasource_id = str(uuid4())

        with patch(
            "dataing.entrypoints.worker.create_adapter_for_datasource",
            new_callable=AsyncMock,
            side_effect=ValueError("Datasource not found"),
        ):
            result = await run_investigation(
                ctx,
                investigation_id=investigation_id,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
            )

            assert result["status"] == "failed"
            assert "error" in result
            assert "Datasource not found" in result["error"]


class TestBranchHandling:
    """Tests for BRANCH signal handling."""

    async def test_handle_branch_signal_creates_child_jobs(self) -> None:
        """Test that handle_branch_signal creates child jobs in database."""
        from dataing.entrypoints.worker import handle_branch_signal

        mock_db = AsyncMock()
        mock_db.create_child_job = AsyncMock()
        mock_db.set_job_awaiting_merge = AsyncMock()

        job_id = uuid4()
        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        branch_specs = [
            {"branch_id": "branch-1", "start_step": "step1"},
            {"branch_id": "branch-2", "start_step": "step2"},
        ]

        with patch(
            "dataing.core.queue.enqueue_branch_jobs",
            new_callable=AsyncMock,
            return_value=["job-1", "job-2"],
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
        assert result["children"] == 2
        assert mock_db.create_child_job.call_count == 2
        mock_db.set_job_awaiting_merge.assert_called_once_with(job_id)

    async def test_check_and_trigger_merge_all_complete(self) -> None:
        """Test that merge is triggered when all children complete."""
        from dataing.entrypoints.worker import check_and_trigger_merge

        mock_db = AsyncMock()
        mock_db.get_pending_children_count = AsyncMock(return_value=0)
        mock_db.update_job_status = AsyncMock()

        parent_job_id = uuid4()

        result = await check_and_trigger_merge(mock_db, parent_job_id)

        assert result is True
        mock_db.update_job_status.assert_called_once_with(
            job_id=parent_job_id,
            status="pending",
            current_step="merge",
        )

    async def test_check_and_trigger_merge_still_pending(self) -> None:
        """Test that merge is not triggered when children still pending."""
        from dataing.entrypoints.worker import check_and_trigger_merge

        mock_db = AsyncMock()
        mock_db.get_pending_children_count = AsyncMock(return_value=2)
        mock_db.update_job_status = AsyncMock()

        parent_job_id = uuid4()

        result = await check_and_trigger_merge(mock_db, parent_job_id)

        assert result is False
        mock_db.update_job_status.assert_not_called()

    async def test_branch_job_triggers_merge_check(self) -> None:
        """Test that branch job completion triggers merge check."""
        from dataing.entrypoints.worker import run_investigation

        mock_db = AsyncMock()
        mock_db.get_pending_children_count = AsyncMock(return_value=0)
        mock_db.update_job_status = AsyncMock()

        ctx = {"db": mock_db}
        investigation_id = str(uuid4())
        tenant_id = str(uuid4())
        parent_job_id = str(uuid4())

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


class TestCancellation:
    """Tests for job cancellation handling."""

    async def test_check_cancellation_returns_true_for_cancelling(self) -> None:
        """Test that check_cancellation returns True for cancelling status."""
        from dataing.entrypoints.worker import check_cancellation

        mock_db = AsyncMock()
        mock_db.get_job_status = AsyncMock(return_value="cancelling")

        job_id = uuid4()
        result = await check_cancellation(mock_db, job_id)

        assert result is True
        mock_db.get_job_status.assert_called_once_with(job_id)

    async def test_check_cancellation_returns_false_for_running(self) -> None:
        """Test that check_cancellation returns False for running status."""
        from dataing.entrypoints.worker import check_cancellation

        mock_db = AsyncMock()
        mock_db.get_job_status = AsyncMock(return_value="running")

        job_id = uuid4()
        result = await check_cancellation(mock_db, job_id)

        assert result is False

    async def test_handle_cancellation_marks_job_cancelled(self) -> None:
        """Test that handle_cancellation marks job as cancelled and raises."""
        from dataing.core.investigation.flow import InvestigationCancelled
        from dataing.entrypoints.worker import handle_cancellation

        mock_db = AsyncMock()
        mock_db.mark_job_cancelled = AsyncMock()

        job_id = uuid4()

        with pytest.raises(InvestigationCancelled):
            await handle_cancellation(mock_db, job_id)

        mock_db.mark_job_cancelled.assert_called_once_with(job_id)


class TestShutdownEvent:
    """Tests for shutdown event handling."""

    def test_shutdown_event_exists(self) -> None:
        """Test that shutdown_event is defined at module level."""
        from dataing.entrypoints.worker import shutdown_event

        assert isinstance(shutdown_event, asyncio.Event)
        assert not shutdown_event.is_set()
