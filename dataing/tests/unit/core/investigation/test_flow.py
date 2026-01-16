"""Tests for investigation flow with checkpointing."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.flow import (
    AwaitingUserInput,
    InvestigationError,
    WorkerShutdownError,
    run_with_checkpointing,
)
from maestro import Signal, Workflow


def create_test_context() -> InvestigationContext:
    """Create a minimal test context."""
    return InvestigationContext(alert_summary="Test anomaly")


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

        # Mock workflow that runs 3 steps then completes
        workflow = MagicMock(spec=Workflow)
        tick_results = [
            MagicMock(context=context, signal=Signal.CONTINUE, next_step="step2", error=None),
            MagicMock(context=context, signal=Signal.CONTINUE, next_step="step3", error=None),
            MagicMock(context=context, signal=Signal.COMPLETE, next_step=None, error=None),
        ]
        workflow.tick = AsyncMock(side_effect=tick_results)

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

        workflow = MagicMock(spec=Workflow)
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
        assert checkpoints[0][1] == "step1"  # Next step that would have run
        assert "checkpointed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fail_signal_raises_investigation_error(self) -> None:
        """Test that FAIL signal raises InvestigationError."""
        context = create_test_context()
        checkpoints: list[tuple[InvestigationContext, str | None]] = []

        async def on_checkpoint(
            ctx: InvestigationContext,
            next_step: str | None,
            cursor: dict[str, Any] | None = None,
        ) -> None:
            checkpoints.append((ctx, next_step))

        workflow = MagicMock(spec=Workflow)
        workflow.tick = AsyncMock(
            return_value=MagicMock(
                context=context,
                signal=Signal.FAIL,
                next_step=None,
                error="Database connection failed",
            )
        )
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

        workflow = MagicMock(spec=Workflow)
        workflow.tick = AsyncMock(
            return_value=MagicMock(
                context=context,
                signal=Signal.AWAIT_USER,
                next_step="resume_step",
                error=None,
            )
        )
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

        workflow = MagicMock(spec=Workflow)
        # Always return CONTINUE to loop forever
        workflow.tick = AsyncMock(
            return_value=MagicMock(
                context=context,
                signal=Signal.CONTINUE,
                next_step="next_step",
                error=None,
            )
        )
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
