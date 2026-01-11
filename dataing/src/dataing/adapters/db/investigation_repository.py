"""PostgreSQL implementation of InvestigationRepository.

This adapter persists investigation state to PostgreSQL using the
schema defined in migrations/013_unified_investigation.sql.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.domain_types import AnomalyAlert
from dataing.core.investigation.entities import (
    Branch,
    Investigation,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.repository import ExecutionLock
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    StepType,
    VersionId,
)

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase


class PostgresInvestigationRepository:
    """PostgreSQL implementation of InvestigationRepository protocol."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository with a database connection."""
        self.db = db

    # =========================================================================
    # Investigation Operations
    # =========================================================================

    async def create_investigation(
        self,
        tenant_id: UUID,
        alert: dict[str, Any],
        created_by: UUID | None = None,
    ) -> Investigation:
        """Create a new investigation."""
        result = await self.db.execute_returning(
            """
            INSERT INTO investigations (tenant_id, alert, created_by)
            VALUES ($1, $2, $3)
            RETURNING id, tenant_id, alert, main_branch_id, outcome, created_at, created_by
            """,
            tenant_id,
            json.dumps(alert),
            created_by,
        )
        if result is None:
            raise RuntimeError("Failed to create investigation")
        return self._row_to_investigation(result)

    async def get_investigation(self, investigation_id: UUID) -> Investigation | None:
        """Get investigation by ID."""
        result = await self.db.fetch_one(
            """
            SELECT id, tenant_id, alert, main_branch_id, outcome, created_at, created_by
            FROM investigations
            WHERE id = $1
            """,
            investigation_id,
        )
        if result is None:
            return None
        return self._row_to_investigation(result)

    async def update_investigation_outcome(
        self,
        investigation_id: UUID,
        outcome: dict[str, Any],
    ) -> None:
        """Set the final outcome of an investigation."""
        await self.db.execute(
            """
            UPDATE investigations
            SET outcome = $2
            WHERE id = $1
            """,
            investigation_id,
            json.dumps(outcome),
        )

    async def set_main_branch(
        self,
        investigation_id: UUID,
        branch_id: UUID,
    ) -> None:
        """Set the main branch for an investigation."""
        await self.db.execute(
            """
            UPDATE investigations
            SET main_branch_id = $2
            WHERE id = $1
            """,
            investigation_id,
            branch_id,
        )

    # =========================================================================
    # Branch Operations
    # =========================================================================

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
        result = await self.db.execute_returning(
            """
            INSERT INTO investigation_branches
                (investigation_id, branch_type, name, parent_branch_id,
                 forked_from_snapshot_id, owner_user_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, investigation_id, branch_type, name, parent_branch_id,
                      forked_from_snapshot_id, owner_user_id, head_snapshot_id,
                      status, created_at, updated_at
            """,
            investigation_id,
            branch_type.value,
            name,
            parent_branch_id,
            forked_from_snapshot_id,
            owner_user_id,
        )
        if result is None:
            raise RuntimeError("Failed to create branch")
        return self._row_to_branch(result)

    async def get_branch(self, branch_id: UUID) -> Branch | None:
        """Get branch by ID."""
        result = await self.db.fetch_one(
            """
            SELECT id, investigation_id, branch_type, name, parent_branch_id,
                   forked_from_snapshot_id, owner_user_id, head_snapshot_id,
                   status, created_at, updated_at
            FROM investigation_branches
            WHERE id = $1
            """,
            branch_id,
        )
        if result is None:
            return None
        return self._row_to_branch(result)

    async def get_user_branch(
        self,
        investigation_id: UUID,
        user_id: UUID,
    ) -> Branch | None:
        """Get user's branch for an investigation."""
        result = await self.db.fetch_one(
            """
            SELECT id, investigation_id, branch_type, name, parent_branch_id,
                   forked_from_snapshot_id, owner_user_id, head_snapshot_id,
                   status, created_at, updated_at
            FROM investigation_branches
            WHERE investigation_id = $1 AND owner_user_id = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            investigation_id,
            user_id,
        )
        if result is None:
            return None
        return self._row_to_branch(result)

    async def update_branch_status(
        self,
        branch_id: UUID,
        status: BranchStatus,
    ) -> None:
        """Update branch status."""
        await self.db.execute(
            """
            UPDATE investigation_branches
            SET status = $2
            WHERE id = $1
            """,
            branch_id,
            status.value,
        )

    async def update_branch_head(
        self,
        branch_id: UUID,
        snapshot_id: UUID,
    ) -> None:
        """Update branch head to point to new snapshot."""
        await self.db.execute(
            """
            UPDATE investigation_branches
            SET head_snapshot_id = $2
            WHERE id = $1
            """,
            branch_id,
            snapshot_id,
        )

    # =========================================================================
    # Snapshot Operations
    # =========================================================================

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
        step_cursor: dict[str, Any] | None = None,
    ) -> Snapshot:
        """Create a new snapshot."""
        result = await self.db.execute_returning(
            """
            INSERT INTO investigation_snapshots
                (investigation_id, branch_id, version_major, version_minor, version_patch,
                 parent_snapshot_id, step, step_cursor, context, created_by, trigger)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id, investigation_id, branch_id, version_major, version_minor,
                      version_patch, parent_snapshot_id, step, step_cursor, context,
                      created_at, created_by, trigger
            """,
            investigation_id,
            branch_id,
            version.major,
            version.minor,
            version.patch,
            parent_snapshot_id,
            step.value,
            json.dumps(step_cursor or {}),
            json.dumps(context.model_dump()),
            created_by,
            trigger,
        )
        if result is None:
            raise RuntimeError("Failed to create snapshot")
        return self._row_to_snapshot(result)

    async def get_snapshot(self, snapshot_id: UUID) -> Snapshot | None:
        """Get snapshot by ID."""
        result = await self.db.fetch_one(
            """
            SELECT id, investigation_id, branch_id, version_major, version_minor,
                   version_patch, parent_snapshot_id, step, step_cursor, context,
                   created_at, created_by, trigger
            FROM investigation_snapshots
            WHERE id = $1
            """,
            snapshot_id,
        )
        if result is None:
            return None
        return self._row_to_snapshot(result)

    # =========================================================================
    # Lock Operations
    # =========================================================================

    async def acquire_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> ExecutionLock | None:
        """Try to acquire execution lock on a branch.

        Returns ExecutionLock if acquired, None if already locked.
        Uses INSERT with ON CONFLICT to handle concurrent acquisition attempts.
        """
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        # Try to insert new lock or update expired lock
        result = await self.db.execute_returning(
            """
            INSERT INTO execution_locks (branch_id, locked_by, expires_at, heartbeat_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (branch_id) DO UPDATE
            SET locked_by = $2, locked_at = NOW(), expires_at = $3, heartbeat_at = NOW()
            WHERE execution_locks.expires_at < NOW()
               OR execution_locks.locked_by = $2
            RETURNING branch_id, locked_by, expires_at
            """,
            branch_id,
            worker_id,
            expires_at,
        )
        if result is None:
            return None
        return ExecutionLock(
            branch_id=result["branch_id"],
            locked_by=result["locked_by"],
            expires_at=result["expires_at"].isoformat(),
        )

    async def release_lock(self, branch_id: UUID, worker_id: str) -> bool:
        """Release execution lock.

        Returns True if released, False if lock was not held.
        """
        result = await self.db.execute(
            """
            DELETE FROM execution_locks
            WHERE branch_id = $1 AND locked_by = $2
            """,
            branch_id,
            worker_id,
        )
        return "DELETE 1" in result

    async def refresh_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """Refresh lock heartbeat.

        Returns True if refreshed, False if lock expired/not held.
        """
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        result = await self.db.execute(
            """
            UPDATE execution_locks
            SET heartbeat_at = NOW(), expires_at = $3
            WHERE branch_id = $1 AND locked_by = $2 AND expires_at > NOW()
            """,
            branch_id,
            worker_id,
            expires_at,
        )
        return "UPDATE 1" in result

    # =========================================================================
    # Message Operations
    # =========================================================================

    async def add_message(
        self,
        branch_id: UUID,
        role: str,
        content: str,
        user_id: UUID | None = None,
        resulting_snapshot_id: UUID | None = None,
    ) -> UUID:
        """Add a message to a branch."""
        result = await self.db.execute_returning(
            """
            INSERT INTO branch_messages
                (branch_id, user_id, role, content, resulting_snapshot_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            branch_id,
            user_id,
            role,
            content,
            resulting_snapshot_id,
        )
        if result is None:
            raise RuntimeError("Failed to add message")
        message_id: UUID = result["id"]
        return message_id

    async def get_messages(
        self,
        branch_id: UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get messages for a branch."""
        return await self.db.fetch_all(
            """
            SELECT id, branch_id, user_id, role, content,
                   resulting_snapshot_id, created_at
            FROM branch_messages
            WHERE branch_id = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            branch_id,
            limit,
        )

    # =========================================================================
    # Merge Point Operations
    # =========================================================================

    async def set_merge_point(
        self,
        parent_branch_id: UUID,
        child_branch_ids: list[UUID],
        merge_step: StepType,
    ) -> None:
        """Record merge point for parallel branches."""
        for child_id in child_branch_ids:
            await self.db.execute(
                """
                INSERT INTO branch_merge_points (parent_branch_id, child_branch_id, merge_step)
                VALUES ($1, $2, $3)
                ON CONFLICT (parent_branch_id, child_branch_id) DO NOTHING
                """,
                parent_branch_id,
                child_id,
                merge_step.value,
            )

    async def get_merge_children(
        self,
        parent_branch_id: UUID,
    ) -> list[UUID]:
        """Get child branch IDs waiting to merge."""
        results = await self.db.fetch_all(
            """
            SELECT child_branch_id
            FROM branch_merge_points
            WHERE parent_branch_id = $1
            """,
            parent_branch_id,
        )
        return [row["child_branch_id"] for row in results]

    async def check_merge_ready(
        self,
        parent_branch_id: UUID,
    ) -> bool:
        """Check if all children are done and ready to merge.

        Returns True if all child branches have a terminal status
        (completed, merged, or abandoned). Abandoned branches don't block merge.
        """
        result = await self.db.fetch_one(
            """
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (
                       WHERE ib.status IN ('completed', 'merged', 'abandoned')
                   ) as ready
            FROM branch_merge_points bmp
            JOIN investigation_branches ib ON ib.id = bmp.child_branch_id
            WHERE bmp.parent_branch_id = $1
            """,
            parent_branch_id,
        )
        if result is None:
            return True  # No children means ready
        total: int = result["total"]
        ready: int = result["ready"]
        return total > 0 and total == ready

    async def get_merge_step(
        self,
        parent_branch_id: UUID,
    ) -> StepType | None:
        """Get the merge step for a parent branch.

        Returns the step to transition to when all children complete.
        """
        result = await self.db.fetch_one(
            """
            SELECT merge_step
            FROM branch_merge_points
            WHERE parent_branch_id = $1
            LIMIT 1
            """,
            parent_branch_id,
        )
        if result is None:
            return None
        return StepType(result["merge_step"])

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _row_to_investigation(self, row: dict[str, Any]) -> Investigation:
        """Convert database row to Investigation entity."""
        alert_data = row["alert"]
        if isinstance(alert_data, str):
            alert_data = json.loads(alert_data)

        outcome_data = row["outcome"]
        if isinstance(outcome_data, str):
            outcome_data = json.loads(outcome_data)

        return Investigation(
            id=row["id"],
            tenant_id=row["tenant_id"],
            alert=AnomalyAlert.model_validate(alert_data),
            main_branch_id=row["main_branch_id"],
            outcome=outcome_data,
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def _row_to_branch(self, row: dict[str, Any]) -> Branch:
        """Convert database row to Branch entity."""
        return Branch(
            id=row["id"],
            investigation_id=row["investigation_id"],
            branch_type=BranchType(row["branch_type"]),
            name=row["name"],
            parent_branch_id=row["parent_branch_id"],
            forked_from_snapshot_id=row["forked_from_snapshot_id"],
            owner_user_id=row["owner_user_id"],
            head_snapshot_id=row["head_snapshot_id"],
            status=BranchStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_snapshot(self, row: dict[str, Any]) -> Snapshot:
        """Convert database row to Snapshot entity."""
        context_data = row["context"]
        if isinstance(context_data, str):
            context_data = json.loads(context_data)

        step_cursor_data = row["step_cursor"]
        if isinstance(step_cursor_data, str):
            step_cursor_data = json.loads(step_cursor_data)

        return Snapshot(
            id=row["id"],
            investigation_id=row["investigation_id"],
            branch_id=row["branch_id"],
            version=VersionId(
                major=row["version_major"],
                minor=row["version_minor"],
                patch=row["version_patch"],
            ),
            parent_snapshot_id=row["parent_snapshot_id"],
            step=StepType(row["step"]),
            step_cursor=step_cursor_data,
            context=InvestigationContext.model_validate(context_data),
            created_at=row["created_at"],
            created_by=row["created_by"],
            trigger=row["trigger"],
        )
