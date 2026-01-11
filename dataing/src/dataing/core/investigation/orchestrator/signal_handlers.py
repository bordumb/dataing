"""Signal handlers for investigation orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.investigation.steps.protocol import BranchRequest
from dataing.core.investigation.values import BranchStatus, ExecutionSignal, StepType

from .merge import check_and_trigger_merge
from .types import TickResult

if TYPE_CHECKING:
    from dataing.core.investigation.entities import Branch, Snapshot
    from dataing.core.investigation.repository import InvestigationRepository
    from dataing.core.investigation.steps.protocol import StepResult


async def handle_continue(
    repository: InvestigationRepository,
    branch: Branch,
    snapshot: Snapshot,
    result: StepResult[Any],
) -> TickResult:
    """Handle CONTINUE signal - create new snapshot and continue.

    Args:
        repository: Repository for persistence operations.
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

    # Create new snapshot, preserving step_cursor (branch-specific data like hypothesis)
    new_version = snapshot.version.next_patch()
    new_snapshot = await repository.create_snapshot(
        investigation_id=snapshot.investigation_id,
        branch_id=branch.id,
        version=new_version,
        step=result.next_step,
        context=result.context,
        parent_snapshot_id=snapshot.id,
        step_cursor=snapshot.step_cursor,  # Preserve branch-specific data
    )

    # Update branch head
    await repository.update_branch_head(branch.id, new_snapshot.id)

    return TickResult(
        signal=ExecutionSignal.CONTINUE,
        new_snapshot_id=new_snapshot.id,
        output=result.output,
    )


async def handle_complete(
    repository: InvestigationRepository,
    branch: Branch,
    snapshot: Snapshot,
    result: StepResult[Any],
) -> TickResult:
    """Handle COMPLETE signal - finalize branch and investigation.

    Args:
        repository: Repository for persistence operations.
        branch: Current branch.
        snapshot: Current snapshot.
        result: StepResult from step execution.

    Returns:
        TickResult indicating completion.
    """
    # Create final snapshot
    new_version = snapshot.version.next_major()
    new_snapshot = await repository.create_snapshot(
        investigation_id=snapshot.investigation_id,
        branch_id=branch.id,
        version=new_version,
        step=StepType.COMPLETE,
        context=result.context,
        parent_snapshot_id=snapshot.id,
    )

    # Update branch head and status
    await repository.update_branch_head(branch.id, new_snapshot.id)
    await repository.update_branch_status(branch.id, BranchStatus.COMPLETED)

    # Update investigation outcome (only for main branch)
    if branch.branch_type.value == "main":
        await repository.update_investigation_outcome(
            snapshot.investigation_id,
            result.output or {},
        )

    # Check if this is a child branch that needs to trigger merge
    if branch.parent_branch_id is not None:
        await check_and_trigger_merge(repository, branch.parent_branch_id)

    return TickResult(
        signal=ExecutionSignal.COMPLETE,
        new_snapshot_id=new_snapshot.id,
        output=result.output,
    )


async def handle_fail(
    repository: InvestigationRepository,
    branch: Branch,
    snapshot: Snapshot,
    result: StepResult[Any],
) -> TickResult:
    """Handle FAIL signal - mark branch as abandoned.

    Args:
        repository: Repository for persistence operations.
        branch: Current branch.
        snapshot: Current snapshot.
        result: StepResult from step execution.

    Returns:
        TickResult indicating failure.
    """
    # Create failure snapshot
    new_snapshot = await repository.create_snapshot(
        investigation_id=snapshot.investigation_id,
        branch_id=branch.id,
        version=snapshot.version.next_patch(),
        step=StepType.FAIL,
        context=result.context,
        parent_snapshot_id=snapshot.id,
    )

    # Update branch
    await repository.update_branch_head(branch.id, new_snapshot.id)
    await repository.update_branch_status(branch.id, BranchStatus.ABANDONED)

    # Extract error message from output or provide default
    error_message: str | None = None
    if result.output is not None:
        if isinstance(result.output, dict) and "error" in result.output:
            error_message = str(result.output["error"])
        elif isinstance(result.output, str):
            error_message = result.output
        else:
            error_message = str(result.output)
    if error_message is None:
        error_message = f"Step {snapshot.step.value} failed without error details"

    return TickResult(
        signal=ExecutionSignal.FAIL,
        new_snapshot_id=new_snapshot.id,
        output=result.output,
        error=error_message,
    )


async def handle_branch(
    repository: InvestigationRepository,
    branch: Branch,
    snapshot: Snapshot,
    result: StepResult[Any],
) -> TickResult:
    """Handle BRANCH signal - create child branches for parallel execution.

    Args:
        repository: Repository for persistence operations.
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

    # Update parent's snapshot with the new context (e.g., hypotheses from step result)
    # This is critical so that when merge happens, the parent has the updated context
    parent_snapshot = await repository.create_snapshot(
        investigation_id=snapshot.investigation_id,
        branch_id=branch.id,
        version=snapshot.version.next_patch(),
        step=snapshot.step,  # Stay at current step (will resume at merge_step)
        context=result.context,
        parent_snapshot_id=snapshot.id,
    )
    await repository.update_branch_head(branch.id, parent_snapshot.id)

    # Create child branches and their initial snapshots
    child_branch_ids: list[UUID] = []

    for spec in branch_request.branches:
        # Create child branch
        child_branch = await repository.create_branch(
            investigation_id=snapshot.investigation_id,
            branch_type=branch_request.branch_type,
            name=spec.name,
            parent_branch_id=branch.id,
            forked_from_snapshot_id=parent_snapshot.id,
        )
        child_branch_ids.append(child_branch.id)

        # Create initial snapshot for child branch
        # Copy context from parent, store branch data in step_cursor
        child_snapshot = await repository.create_snapshot(
            investigation_id=snapshot.investigation_id,
            branch_id=child_branch.id,
            version=parent_snapshot.version.next_minor(),
            step=child_start_step,
            context=result.context,
            parent_snapshot_id=parent_snapshot.id,
            step_cursor=spec.data,
        )

        # Update child branch head
        await repository.update_branch_head(child_branch.id, child_snapshot.id)

    # Set merge point on parent branch
    await repository.set_merge_point(
        parent_branch_id=branch.id,
        child_branch_ids=child_branch_ids,
        merge_step=branch_request.merge_step,
    )

    # Suspend parent branch (waiting for merge)
    await repository.update_branch_status(branch.id, BranchStatus.SUSPENDED)

    return TickResult(
        signal=ExecutionSignal.BRANCH,
        output=result.output,
        child_branch_ids=child_branch_ids,
        new_snapshot_id=parent_snapshot.id,
    )


async def handle_await_user(
    repository: InvestigationRepository,
    branch: Branch,
    snapshot: Snapshot,
    result: StepResult[Any],
) -> TickResult:
    """Handle AWAIT_USER signal - suspend branch and wait for input.

    Creates a snapshot at AWAIT_USER step and suspends the branch
    to wait for user input before continuing.

    Args:
        repository: Repository for persistence operations.
        branch: Current branch.
        snapshot: Current snapshot.
        result: StepResult from step execution.

    Returns:
        TickResult with AWAIT_USER signal.
    """
    # Create snapshot at AWAIT_USER step
    new_version = snapshot.version.next_patch()
    new_snapshot = await repository.create_snapshot(
        investigation_id=snapshot.investigation_id,
        branch_id=branch.id,
        version=new_version,
        step=StepType.AWAIT_USER,
        context=result.context,
        parent_snapshot_id=snapshot.id,
    )

    # Update branch head and suspend
    await repository.update_branch_head(branch.id, new_snapshot.id)
    await repository.update_branch_status(branch.id, BranchStatus.SUSPENDED)

    return TickResult(
        signal=ExecutionSignal.AWAIT_USER,
        new_snapshot_id=new_snapshot.id,
        output=result.output,
    )
