"""Tests for investigation flow with checkpointing."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.flow import (
    AwaitingUserInput,
    InvestigationError,
    WorkerShutdownError,
    run_with_checkpointing,
)
from maistro import RunCompleted, RunFailed, Signal, StepCompleted, Workflow


def create_test_context() -> InvestigationContext:
    """Create a minimal test context."""
    return InvestigationContext(alert_summary="Test anomaly")


async def mock_stream(*events: Any) -> AsyncIterator[Any]:
    """Create an async iterator from events."""
    for event in events:
        yield event


class TestRunWithCheckpointing:
    """Tests for run_with_checkpointing function."""

    @pytest.mark.asyncio
    async def test_checkpoint_callback_called(self) -> None:
        """Test that checkpoint callback is invoked after each step."""
        context = create_test_context()
        checkpoints: list[tuple[InvestigationContext, str | None]] = []

        async def on_checkpoint(
            ctx: InvestigationContext,
            next_step: str | None,
            cursor: dict[str, Any] | None = None,
        ) -> None:
            checkpoints.append((ctx, next_step))

        # Create StepCompleted events that update context
        ctx1 = context.model_copy(update={"alert_summary": "Step 1"})
        ctx2 = context.model_copy(update={"alert_summary": "Step 2"})
        ctx3 = context.model_copy(update={"alert_summary": "Step 3"})

        events = [
            StepCompleted(
                step_name="step1",
                context_update={"_full_context": ctx1},
                signal=Signal.CONTINUE,
                next_step="step2",
            ),
            StepCompleted(
                step_name="step2",
                context_update={"_full_context": ctx2},
                signal=Signal.CONTINUE,
                next_step="step3",
            ),
            StepCompleted(
                step_name="step3",
                context_update={"_full_context": ctx3},
                signal=Signal.COMPLETE,
                next_step=None,
            ),
            RunCompleted(final_context={}),
        ]

        workflow = MagicMock(spec=Workflow)
        workflow.run_streaming = MagicMock(return_value=mock_stream(*events))

        shutdown = asyncio.Event()

        await run_with_checkpointing(
            workflow=workflow,
            context=context,
            start_step="step1",
            on_step_complete=on_checkpoint,
            shutdown_signal=shutdown,
        )

        # Verify checkpoint called after each step
        assert len(checkpoints) == 3
        assert checkpoints[0][1] == "step2"
        assert checkpoints[1][1] == "step3"
        assert checkpoints[2][1] is None

    @pytest.mark.asyncio
    async def test_shutdown_signal_checkpoints(self) -> None:
        """Test that shutdown signal triggers checkpoint before raising."""
        context = create_test_context()
        checkpoints: list[tuple[InvestigationContext, str | None]] = []

        async def on_checkpoint(
            ctx: InvestigationContext,
            next_step: str | None,
            cursor: dict[str, Any] | None = None,
        ) -> None:
            checkpoints.append((ctx, next_step))

        # Create an event that will be processed when shutdown is set
        ctx1 = context.model_copy(update={"alert_summary": "Step 1"})
        events = [
            StepCompleted(
                step_name="step1",
                context_update={"_full_context": ctx1},
                signal=Signal.CONTINUE,
                next_step="step2",
            ),
        ]

        workflow = MagicMock(spec=Workflow)
        workflow.run_streaming = MagicMock(return_value=mock_stream(*events))

        shutdown = asyncio.Event()
        shutdown.set()  # Signal shutdown immediately

        with pytest.raises(WorkerShutdownError) as exc_info:
            await run_with_checkpointing(
                workflow=workflow,
                context=context,
                start_step="step1",
                on_step_complete=on_checkpoint,
                shutdown_signal=shutdown,
            )

        # Verify checkpoint was saved before raising
        assert len(checkpoints) == 1
        assert "checkpointed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fail_signal_raises_investigation_error(self) -> None:
        """Test that RunFailed event raises InvestigationError."""
        context = create_test_context()
        checkpoints: list[tuple[InvestigationContext, str | None]] = []

        async def on_checkpoint(
            ctx: InvestigationContext,
            next_step: str | None,
            cursor: dict[str, Any] | None = None,
        ) -> None:
            checkpoints.append((ctx, next_step))

        ctx1 = context.model_copy(update={"alert_summary": "Step 1"})
        events = [
            StepCompleted(
                step_name="step1",
                context_update={"_full_context": ctx1},
                signal=Signal.FAIL,
                next_step=None,
            ),
            RunFailed(error="Database connection failed"),
        ]

        workflow = MagicMock(spec=Workflow)
        workflow.run_streaming = MagicMock(return_value=mock_stream(*events))

        shutdown = asyncio.Event()

        with pytest.raises(InvestigationError) as exc_info:
            await run_with_checkpointing(
                workflow=workflow,
                context=context,
                start_step="step1",
                on_step_complete=on_checkpoint,
                shutdown_signal=shutdown,
            )

        assert "Database connection failed" in str(exc_info.value)
        # Checkpoint still called before raising
        assert len(checkpoints) == 1

    @pytest.mark.asyncio
    async def test_await_user_raises_exception(self) -> None:
        """Test that AWAIT_USER signal raises AwaitingUserInput."""
        context = create_test_context()
        checkpoints: list[tuple[InvestigationContext, str | None]] = []

        async def on_checkpoint(
            ctx: InvestigationContext,
            next_step: str | None,
            cursor: dict[str, Any] | None = None,
        ) -> None:
            checkpoints.append((ctx, next_step))

        ctx1 = context.model_copy(update={"alert_summary": "Step 1"})
        events = [
            StepCompleted(
                step_name="step1",
                context_update={"_full_context": ctx1},
                signal=Signal.AWAIT_USER,
                next_step="resume_step",
            ),
        ]

        workflow = MagicMock(spec=Workflow)
        workflow.run_streaming = MagicMock(return_value=mock_stream(*events))

        shutdown = asyncio.Event()

        with pytest.raises(AwaitingUserInput) as exc_info:
            await run_with_checkpointing(
                workflow=workflow,
                context=context,
                start_step="step1",
                on_step_complete=on_checkpoint,
                shutdown_signal=shutdown,
            )

        assert exc_info.value.next_step == "resume_step"
        # Checkpoint saved with resume step
        assert len(checkpoints) == 1
        assert checkpoints[0][1] == "resume_step"

    @pytest.mark.asyncio
    async def test_max_iterations_exceeded(self) -> None:
        """Test that exceeding max iterations raises RuntimeError."""
        context = create_test_context()

        async def on_checkpoint(
            ctx: InvestigationContext,
            next_step: str | None,
            cursor: dict[str, Any] | None = None,
        ) -> None:
            pass

        # Create many events to exceed max iterations
        events = []
        for i in range(10):
            ctx = context.model_copy(update={"alert_summary": f"Step {i}"})
            events.append(
                StepCompleted(
                    step_name=f"step{i}",
                    context_update={"_full_context": ctx},
                    signal=Signal.CONTINUE,
                    next_step=f"step{i+1}",
                )
            )

        workflow = MagicMock(spec=Workflow)
        workflow.run_streaming = MagicMock(return_value=mock_stream(*events))

        shutdown = asyncio.Event()

        with pytest.raises(RuntimeError) as exc_info:
            await run_with_checkpointing(
                workflow=workflow,
                context=context,
                start_step="step1",
                on_step_complete=on_checkpoint,
                shutdown_signal=shutdown,
                max_iterations=5,
            )

        assert "Max iterations (5) exceeded" in str(exc_info.value)
