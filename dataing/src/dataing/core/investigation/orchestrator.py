"""Investigation orchestrator for tick-based execution.

The orchestrator processes investigations one step at a time,
persisting state between steps for durability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from dataing.core.investigation.registry import StepRegistry
from dataing.core.investigation.steps.protocol import BranchRequest, StepResult
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
    child_branch_ids: list[UUID] | None = None


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
        elif result.signal == ExecutionSignal.BRANCH:
            return await self._handle_branch(branch, snapshot, result)
        else:
            # Other signals (AWAIT_USER, etc.) will be added later
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

    async def _handle_branch(
        self,
        branch: Branch,
        snapshot: Snapshot,
        result: StepResult[Any],
    ) -> TickResult:
        """Handle BRANCH signal - create child branches for parallel execution.

        Args:
            branch: Current (parent) branch.
            snapshot: Current snapshot.
            result: StepResult from step execution with branch_request.

        Returns:
            TickResult with child_branch_ids.
        """
        # Validate branch_request exists
        if result.branch_request is None:
            return TickResult(
                signal=ExecutionSignal.FAIL,
                error="BRANCH signal without branch_request",
            )

        branch_request: BranchRequest = result.branch_request

        # Determine child start step (default to GENERATE_QUERY)
        child_start_step = branch_request.child_start_step or StepType.GENERATE_QUERY

        # Create child branches and their initial snapshots
        child_branch_ids: list[UUID] = []

        for spec in branch_request.branches:
            # Create child branch
            child_branch = await self.repository.create_branch(
                investigation_id=snapshot.investigation_id,
                branch_type=branch_request.branch_type,
                name=spec.name,
                parent_branch_id=branch.id,
                forked_from_snapshot_id=snapshot.id,
            )
            child_branch_ids.append(child_branch.id)

            # Create initial snapshot for child branch
            # Copy context from parent, store branch data in step_cursor
            child_snapshot = await self.repository.create_snapshot(
                investigation_id=snapshot.investigation_id,
                branch_id=child_branch.id,
                version=snapshot.version.next_minor(),
                step=child_start_step,
                context=result.context,
                parent_snapshot_id=snapshot.id,
                step_cursor=spec.data,
            )

            # Update child branch head
            await self.repository.update_branch_head(child_branch.id, child_snapshot.id)

        # Set merge point on parent branch
        await self.repository.set_merge_point(
            parent_branch_id=branch.id,
            child_branch_ids=child_branch_ids,
            merge_step=branch_request.merge_step,
        )

        # Suspend parent branch (waiting for merge)
        await self.repository.update_branch_status(branch.id, BranchStatus.SUSPENDED)

        return TickResult(
            signal=ExecutionSignal.BRANCH,
            output=result.output,
            child_branch_ids=child_branch_ids,
        )
