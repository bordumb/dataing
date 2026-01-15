"""Tests for queue trace context propagation."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from dataing.core.queue import enqueue_investigation


class TestEnqueueInvestigationTracing:
    """Tests for trace context propagation in enqueue_investigation."""

    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        """Create a mock Arq pool."""
        pool = MagicMock()
        pool.close = AsyncMock()
        return pool

    @pytest.fixture
    def mock_job(self) -> MagicMock:
        """Create a mock job."""
        job = MagicMock()
        job.job_id = "test-job-id"
        return job

    async def test_creates_producer_span(
        self, mock_pool: MagicMock, mock_job: MagicMock
    ) -> None:
        """Producer span is created with correct attributes."""
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)
        investigation_id = str(uuid4())
        tenant_id = str(uuid4())

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with (
            patch("dataing.core.queue.create_pool", return_value=mock_pool),
            patch("dataing.core.queue.get_tracer", return_value=mock_tracer),
        ):
            await enqueue_investigation(
                investigation_id=investigation_id,
                tenant_id=tenant_id,
            )

            # Verify span was created with correct name and kind
            mock_tracer.start_as_current_span.assert_called_once()
            call_args = mock_tracer.start_as_current_span.call_args
            assert call_args[0][0] == "investigation.enqueue"
            assert "kind" in call_args[1]

    async def test_includes_trace_context_in_job_payload(
        self, mock_pool: MagicMock, mock_job: MagicMock
    ) -> None:
        """Full W3C trace context is included in job payload."""
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with (
            patch("dataing.core.queue.create_pool", return_value=mock_pool),
            patch(
                "dataing.core.queue.serialize_trace_context",
                return_value={
                    "traceparent": "00-1234-5678-01",
                    "tracestate": "vendor=value",
                },
            ),
        ):
            await enqueue_investigation(
                investigation_id="inv-123",
                tenant_id="tenant-456",
                correlation_id="corr-789",
            )

            # Verify trace_context was passed in job args
            call_kwargs = mock_pool.enqueue_job.call_args[1]
            assert "trace_context" in call_kwargs
            assert call_kwargs["trace_context"]["traceparent"] == "00-1234-5678-01"
            assert call_kwargs["trace_context"]["tracestate"] == "vendor=value"
            assert call_kwargs["trace_context"]["correlation_id"] == "corr-789"
            assert "enqueued_at" in call_kwargs["trace_context"]

    async def test_includes_enqueued_at_timestamp(
        self, mock_pool: MagicMock, mock_job: MagicMock
    ) -> None:
        """enqueued_at timestamp is included for SLO measurement."""
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with (
            patch("dataing.core.queue.create_pool", return_value=mock_pool),
            patch(
                "dataing.core.queue.serialize_trace_context",
                return_value={},
            ),
        ):
            await enqueue_investigation(
                investigation_id="inv-123",
                tenant_id="tenant-456",
            )

            call_kwargs = mock_pool.enqueue_job.call_args[1]
            enqueued_at = call_kwargs["trace_context"]["enqueued_at"]
            # Should be ISO format timestamp
            assert "T" in enqueued_at
            assert enqueued_at.endswith("+00:00") or enqueued_at.endswith("Z")

    async def test_correlation_id_propagation(
        self, mock_pool: MagicMock, mock_job: MagicMock
    ) -> None:
        """Correlation ID is passed through to job payload."""
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with (
            patch("dataing.core.queue.create_pool", return_value=mock_pool),
            patch(
                "dataing.core.queue.serialize_trace_context",
                return_value={},
            ),
        ):
            await enqueue_investigation(
                investigation_id="inv-123",
                tenant_id="tenant-456",
                correlation_id="my-correlation-id",
            )

            call_kwargs = mock_pool.enqueue_job.call_args[1]
            assert call_kwargs["trace_context"]["correlation_id"] == "my-correlation-id"

    async def test_works_without_correlation_id(
        self, mock_pool: MagicMock, mock_job: MagicMock
    ) -> None:
        """Works correctly when no correlation ID provided."""
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with (
            patch("dataing.core.queue.create_pool", return_value=mock_pool),
            patch(
                "dataing.core.queue.serialize_trace_context",
                return_value={},
            ),
        ):
            job_id = await enqueue_investigation(
                investigation_id="inv-123",
                tenant_id="tenant-456",
            )

            assert job_id == "test-job-id"
            call_kwargs = mock_pool.enqueue_job.call_args[1]
            assert call_kwargs["trace_context"]["correlation_id"] is None

    async def test_branch_spec_with_trace_context(
        self, mock_pool: MagicMock, mock_job: MagicMock
    ) -> None:
        """Branch jobs also get trace context propagation."""
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with (
            patch("dataing.core.queue.create_pool", return_value=mock_pool),
            patch(
                "dataing.core.queue.serialize_trace_context",
                return_value={"traceparent": "00-abc-def-01"},
            ),
        ):
            await enqueue_investigation(
                investigation_id="inv-123",
                tenant_id="tenant-456",
                parent_job_id="parent-job",
                branch_spec={"name": "hypothesis-1"},
                correlation_id="branch-corr-id",
            )

            call_kwargs = mock_pool.enqueue_job.call_args[1]
            assert call_kwargs["branch_spec"] == {"name": "hypothesis-1"}
            assert call_kwargs["parent_job_id"] == "parent-job"
            assert call_kwargs["trace_context"]["correlation_id"] == "branch-corr-id"
