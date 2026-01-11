"""Merge handling for investigation branches."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dataing.core.investigation.values import BranchStatus

if TYPE_CHECKING:
    from uuid import UUID

    from dataing.core.investigation.repository import InvestigationRepository


async def check_and_trigger_merge(
    repository: InvestigationRepository,
    parent_branch_id: UUID,
) -> None:
    """Check if all child branches are complete and resume parent for merge.

    Args:
        repository: Repository for persistence operations.
        parent_branch_id: ID of the parent branch to potentially resume.
    """
    # Check if all children are ready to merge
    merge_ready = await repository.check_merge_ready(parent_branch_id)
    if not merge_ready:
        return

    # Get the merge step
    merge_step = await repository.get_merge_step(parent_branch_id)
    if merge_step is None:
        return

    # Get parent branch
    parent_branch = await repository.get_branch(parent_branch_id)
    if parent_branch is None or parent_branch.head_snapshot_id is None:
        return

    # Get parent's current snapshot
    parent_snapshot = await repository.get_snapshot(parent_branch.head_snapshot_id)
    if parent_snapshot is None:
        return

    # Collect evidence from all child branches
    child_branch_ids = await repository.get_merge_children(parent_branch_id)
    merged_evidence: list[dict[str, Any]] = list(parent_snapshot.context.evidence)

    for child_id in child_branch_ids:
        child_branch = await repository.get_branch(child_id)
        if child_branch is None or child_branch.head_snapshot_id is None:
            continue
        child_snap = await repository.get_snapshot(child_branch.head_snapshot_id)
        if child_snap is not None:
            merged_evidence.extend(child_snap.context.evidence)

    # Create updated context with merged evidence
    merged_context = parent_snapshot.context.model_copy(
        update={"evidence": merged_evidence}
    )

    # Create new snapshot at merge step for parent
    new_snapshot = await repository.create_snapshot(
        investigation_id=parent_snapshot.investigation_id,
        branch_id=parent_branch_id,
        version=parent_snapshot.version.next_minor(),
        step=merge_step,
        context=merged_context,
        parent_snapshot_id=parent_snapshot.id,
    )

    # Update parent branch head and resume it
    await repository.update_branch_head(parent_branch_id, new_snapshot.id)
    await repository.update_branch_status(parent_branch_id, BranchStatus.ACTIVE)
