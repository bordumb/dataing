"""Investigation orchestrator for tick-based execution.

The orchestrator processes investigations one step at a time,
persisting state between steps for durability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from dataing.core.investigation.registry import StepRegistry
from dataing.core.investigation.values import ExecutionSignal

from . import signal_handlers
from .types import TickResult

if TYPE_CHECKING:
    from dataing.core.investigation.repository import InvestigationRepository


class InvestigationOrchestrator:
    """Tick-based orchestrator for investigation execution.

    Processes one step at a time, handling signals to determine
    the next action (continue, complete, branch, etc.).
    """

    def __init__(
        self,
        repository: InvestigationRepository,
        registry: StepRegistry,
        worker_id: str | None = None,
        lock_ttl_seconds: int = 300,
    ) -> None:
        """Initialize orchestrator.

        Args:
            repository: Repository for persistence operations.
            registry: Registry of step implementations.
            worker_id: Unique identifier for this worker. Auto-generated if not provided.
            lock_ttl_seconds: Lock time-to-live in seconds. Defaults to 300 (5 minutes).
        """
        self.repository = repository
        self.registry = registry
        self.worker_id = worker_id if worker_id is not None else uuid4().hex
        self.lock_ttl_seconds = lock_ttl_seconds

    async def tick(self, branch_id: UUID) -> TickResult:
        """Execute one step on a branch.

        Args:
            branch_id: ID of the branch to process.

        Returns:
            TickResult with signal and any output/error.
        """
        # Acquire lock before any processing
        lock = await self.repository.acquire_lock(
            branch_id,
            self.worker_id,
            self.lock_ttl_seconds,
        )
        if lock is None:
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error=f"Could not acquire lock for branch: {branch_id}",
            )

        try:
            return await self._tick_inner(branch_id)
        except Exception as e:
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error=f"Step execution failed: {e}",
            )
        finally:
            await self.repository.release_lock(branch_id, self.worker_id)

    async def _tick_inner(self, branch_id: UUID) -> TickResult:
        """Execute one step on a branch (inner implementation).

        Args:
            branch_id: ID of the branch to process.

        Returns:
            TickResult with signal and any output/error.
        """
        # Load current state
        branch = await self.repository.get_branch(branch_id)
        if branch is None:
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error=f"Branch not found: {branch_id}",
            )

        if branch.head_snapshot_id is None:
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error=f"Branch has no head snapshot: {branch_id}",
            )

        snapshot = await self.repository.get_snapshot(branch.head_snapshot_id)
        if snapshot is None:
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error=f"Snapshot not found: {branch.head_snapshot_id}",
            )

        # Get step implementation
        step = self.registry.get(snapshot.step)
        if step is None:
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error=f"No step registered for: {snapshot.step}",
            )

        # Check preconditions
        if not step.can_execute(snapshot.context):
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error=f"Step preconditions not met: {snapshot.step}",
            )

        # Execute step - pass step_cursor as input_data for branch-specific data
        result = await step.execute(
            snapshot.context,
            snapshot.step_cursor if snapshot.step_cursor else None,
        )

        # Handle signal
        return await self._handle_signal(branch, snapshot, result)

    async def _handle_signal(
        self,
        branch: Any,
        snapshot: Any,
        result: Any,
    ) -> TickResult:
        """Handle the execution signal from a step.

        Args:
            branch: Current branch.
            snapshot: Current snapshot.
            result: StepResult from step execution.

        Returns:
            TickResult with appropriate action taken.
        """
        if result.signal == ExecutionSignal.CONTINUE:
            return await signal_handlers.handle_continue(
                self.repository, branch, snapshot, result
            )
        elif result.signal == ExecutionSignal.COMPLETE:
            return await signal_handlers.handle_complete(
                self.repository, branch, snapshot, result
            )
        elif result.signal == ExecutionSignal.FAIL:
            return await signal_handlers.handle_fail(
                self.repository, branch, snapshot, result
            )
        elif result.signal == ExecutionSignal.BRANCH:
            return await signal_handlers.handle_branch(
                self.repository, branch, snapshot, result
            )
        elif result.signal == ExecutionSignal.AWAIT_USER:
            return await signal_handlers.handle_await_user(
                self.repository, branch, snapshot, result
            )
        else:
            # Unknown signal
            return TickResult(
                signal=result.signal,
                output=result.output,
            )
