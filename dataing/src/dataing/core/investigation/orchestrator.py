"""Investigation orchestrator for tick-based execution.

The orchestrator processes investigations one step at a time,
persisting state between steps for durability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.investigation.registry import StepRegistry
from dataing.core.investigation.steps.protocol import StepResult
from dataing.core.investigation.values import BranchStatus, ExecutionSignal, StepType

if TYPE_CHECKING:
    from dataing.core.investigation.entities import Branch, Snapshot
    from dataing.core.investigation.repository import InvestigationRepository


@dataclass
class TickResult:
    """Result of a single tick execution."""

    signal: ExecutionSignal
    new_snapshot_id: UUID | None = None
    output: Any = None
    error: str | None = None


class InvestigationOrchestrator:
    """Tick-based orchestrator for investigation execution.

    Processes one step at a time, handling signals to determine
    the next action (continue, complete, branch, etc.).
    """

    def __init__(
        self,
        repository: InvestigationRepository,
        registry: StepRegistry,
    ) -> None:
        """Initialize orchestrator.

        Args:
            repository: Repository for persistence operations.
            registry: Registry of step implementations.
        """
        self.repository = repository
        self.registry = registry

    async def tick(self, branch_id: UUID) -> TickResult:
        """Execute one step on a branch.

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

        # Execute step
        result = await step.execute(snapshot.context)

        # Handle signal
        return await self._handle_signal(branch, snapshot, result)

    async def _handle_signal(
        self,
        branch: Branch,
        snapshot: Snapshot,
        result: StepResult[Any],
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
            return await self._handle_continue(branch, snapshot, result)
        elif result.signal == ExecutionSignal.COMPLETE:
            return await self._handle_complete(branch, snapshot, result)
        elif result.signal == ExecutionSignal.FAIL:
            return await self._handle_fail(branch, snapshot, result)
        else:
            # Other signals (BRANCH, AWAIT_USER, etc.) will be added later
            return TickResult(
                signal=result.signal,
                output=result.output,
            )

    async def _handle_continue(
        self,
        branch: Branch,
        snapshot: Snapshot,
        result: StepResult[Any],
    ) -> TickResult:
        """Handle CONTINUE signal - create new snapshot and continue.

        Args:
            branch: Current branch.
            snapshot: Current snapshot.
            result: StepResult from step execution.

        Returns:
            TickResult with new snapshot ID.
        """
        if result.next_step is None:
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error="CONTINUE signal without next_step",
            )

        # Create new snapshot
        new_version = snapshot.version.next_patch()
        new_snapshot = await self.repository.create_snapshot(
            investigation_id=snapshot.investigation_id,
            branch_id=branch.id,
            version=new_version,
            step=result.next_step,
            context=result.context,
            parent_snapshot_id=snapshot.id,
        )

        # Update branch head
        await self.repository.update_branch_head(branch.id, new_snapshot.id)

        return TickResult(
            signal=ExecutionSignal.CONTINUE,
            new_snapshot_id=new_snapshot.id,
            output=result.output,
        )

    async def _handle_complete(
        self,
        branch: Branch,
        snapshot: Snapshot,
        result: StepResult[Any],
    ) -> TickResult:
        """Handle COMPLETE signal - finalize branch and investigation.

        Args:
            branch: Current branch.
            snapshot: Current snapshot.
            result: StepResult from step execution.

        Returns:
            TickResult indicating completion.
        """
        # Create final snapshot
        new_version = snapshot.version.next_major()
        new_snapshot = await self.repository.create_snapshot(
            investigation_id=snapshot.investigation_id,
            branch_id=branch.id,
            version=new_version,
            step=StepType.COMPLETE,
            context=result.context,
            parent_snapshot_id=snapshot.id,
        )

        # Update branch head and status
        await self.repository.update_branch_head(branch.id, new_snapshot.id)
        await self.repository.update_branch_status(branch.id, BranchStatus.COMPLETED)

        # Update investigation outcome (only for main branch)
        if branch.branch_type.value == "main":
            await self.repository.update_investigation_outcome(
                snapshot.investigation_id,
                result.output or {},
            )

        return TickResult(
            signal=ExecutionSignal.COMPLETE,
            new_snapshot_id=new_snapshot.id,
            output=result.output,
        )

    async def _handle_fail(
        self,
        branch: Branch,
        snapshot: Snapshot,
        result: StepResult[Any],
    ) -> TickResult:
        """Handle FAIL signal - mark branch as abandoned.

        Args:
            branch: Current branch.
            snapshot: Current snapshot.
            result: StepResult from step execution.

        Returns:
            TickResult indicating failure.
        """
        # Create failure snapshot
        new_snapshot = await self.repository.create_snapshot(
            investigation_id=snapshot.investigation_id,
            branch_id=branch.id,
            version=snapshot.version.next_patch(),
            step=StepType.FAIL,
            context=result.context,
            parent_snapshot_id=snapshot.id,
        )

        # Update branch
        await self.repository.update_branch_head(branch.id, new_snapshot.id)
        await self.repository.update_branch_status(branch.id, BranchStatus.ABANDONED)

        return TickResult(
            signal=ExecutionSignal.FAIL,
            new_snapshot_id=new_snapshot.id,
            output=result.output,
        )
