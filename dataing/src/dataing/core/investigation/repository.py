"""Repository protocol for investigation persistence.

This module defines the interface for persisting investigation state.
Implementations should be in the adapters layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from .entities import Branch, Investigation, InvestigationContext, Snapshot
    from .values import BranchStatus, BranchType, StepType, VersionId


class ExecutionLock:
    """Represents an acquired execution lock."""

    def __init__(self, branch_id: UUID, locked_by: str, expires_at: str) -> None:
        """Initialize the lock."""
        self.branch_id = branch_id
        self.locked_by = locked_by
        self.expires_at = expires_at


class InvestigationRepository(Protocol):
    """Protocol for investigation persistence operations.

    This defines the interface that adapters must implement.
    All methods are async to support async database drivers.
    """

    # Investigation operations
    async def create_investigation(
        self,
        tenant_id: UUID,
        alert: dict[str, Any],
        created_by: UUID | None = None,
    ) -> Investigation:
        """Create a new investigation."""
        ...

    async def get_investigation(self, investigation_id: UUID) -> Investigation | None:
        """Get investigation by ID."""
        ...

    async def update_investigation_outcome(
        self,
        investigation_id: UUID,
        outcome: dict[str, Any],
    ) -> None:
        """Set the final outcome of an investigation."""
        ...

    async def set_main_branch(
        self,
        investigation_id: UUID,
        branch_id: UUID,
    ) -> None:
        """Set the main branch for an investigation."""
        ...

    # Branch operations
    async def create_branch(
        self,
        investigation_id: UUID,
        branch_type: BranchType,
        name: str,
        parent_branch_id: UUID | None = None,
        forked_from_snapshot_id: UUID | None = None,
        owner_user_id: UUID | None = None,
    ) -> Branch:
        """Create a new branch."""
        ...

    async def get_branch(self, branch_id: UUID) -> Branch | None:
        """Get branch by ID."""
        ...

    async def get_user_branch(
        self,
        investigation_id: UUID,
        user_id: UUID,
    ) -> Branch | None:
        """Get user's branch for an investigation."""
        ...

    async def update_branch_status(
        self,
        branch_id: UUID,
        status: BranchStatus,
    ) -> None:
        """Update branch status."""
        ...

    async def update_branch_head(
        self,
        branch_id: UUID,
        snapshot_id: UUID,
    ) -> None:
        """Update branch head to point to new snapshot."""
        ...

    # Snapshot operations
    async def create_snapshot(
        self,
        investigation_id: UUID,
        branch_id: UUID,
        version: VersionId,
        step: StepType,
        context: InvestigationContext,
        parent_snapshot_id: UUID | None = None,
        created_by: UUID | None = None,
        trigger: str = "system",
    ) -> Snapshot:
        """Create a new snapshot."""
        ...

    async def get_snapshot(self, snapshot_id: UUID) -> Snapshot | None:
        """Get snapshot by ID."""
        ...

    # Lock operations
    async def acquire_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> ExecutionLock | None:
        """Try to acquire execution lock on a branch.

        Returns ExecutionLock if acquired, None if already locked.
        """
        ...

    async def release_lock(self, branch_id: UUID, worker_id: str) -> bool:
        """Release execution lock.

        Returns True if released, False if lock was not held.
        """
        ...

    async def refresh_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """Refresh lock heartbeat.

        Returns True if refreshed, False if lock expired/not held.
        """
        ...

    # Message operations
    async def add_message(
        self,
        branch_id: UUID,
        role: str,
        content: str,
        user_id: UUID | None = None,
        resulting_snapshot_id: UUID | None = None,
    ) -> UUID:
        """Add a message to a branch."""
        ...

    async def get_messages(
        self,
        branch_id: UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get messages for a branch."""
        ...

    # Merge point operations
    async def set_merge_point(
        self,
        parent_branch_id: UUID,
        child_branch_ids: list[UUID],
        merge_step: StepType,
    ) -> None:
        """Record merge point for parallel branches."""
        ...

    async def get_merge_children(
        self,
        parent_branch_id: UUID,
    ) -> list[UUID]:
        """Get child branch IDs waiting to merge."""
        ...

    async def check_merge_ready(
        self,
        parent_branch_id: UUID,
    ) -> bool:
        """Check if all children are ready to merge."""
        ...
