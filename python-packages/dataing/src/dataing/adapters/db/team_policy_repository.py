"""PostgreSQL repository for team policies and overrides.

This adapter persists team policy configuration to PostgreSQL using the
schema defined in migrations/028_team_policies.sql.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase


class PolicyAction(str, Enum):
    """Actions a policy can trigger."""

    AUTO = "auto"
    REVIEW = "review"
    ISSUE_ONLY = "issue_only"


@dataclass
class TeamPolicy:
    """Team default policy configuration."""

    id: UUID
    org_id: UUID
    team_id: UUID
    sources: list[str]
    default_action: PolicyAction
    auto_investigate_min_severity: str | None
    review_required_max_severity: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class TeamPolicyOverride:
    """Dataset or tag-specific policy override."""

    id: UUID
    org_id: UUID
    team_id: UUID
    dataset_id: str | None
    tag_id: UUID | None
    default_action: PolicyAction | None
    auto_investigate_min_severity: str | None
    review_required_max_severity: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class TeamQueueLimits:
    """Per-team queue rate limits and concurrency settings."""

    id: UUID
    org_id: UUID
    team_id: UUID
    rate_limit_per_minute: int
    burst_size: int
    max_concurrent: int
    batch_size: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TeamPolicyRepository:
    """PostgreSQL implementation for team policy operations."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository."""
        self.db = db

    # =========================================================================
    # Team Policy Operations
    # =========================================================================

    async def create_policy(
        self,
        org_id: UUID,
        team_id: UUID,
        sources: list[str] | None = None,
        default_action: PolicyAction = PolicyAction.ISSUE_ONLY,
        auto_investigate_min_severity: str | None = None,
        review_required_max_severity: str | None = None,
    ) -> TeamPolicy:
        """Create a team policy."""
        result = await self.db.execute_returning(
            """
            INSERT INTO team_policies
                (org_id, team_id, sources, default_action,
                 auto_investigate_min_severity, review_required_max_severity)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, org_id, team_id, sources, default_action,
                      auto_investigate_min_severity, review_required_max_severity,
                      is_active, created_at, updated_at
            """,
            org_id,
            team_id,
            sources or [],
            default_action.value,
            auto_investigate_min_severity,
            review_required_max_severity,
        )
        if result is None:
            raise RuntimeError("Failed to create team policy")
        return self._row_to_policy(result)

    async def get_policy(self, policy_id: UUID) -> TeamPolicy | None:
        """Get a team policy by ID."""
        result = await self.db.fetch_one(
            """
            SELECT id, org_id, team_id, sources, default_action,
                   auto_investigate_min_severity, review_required_max_severity,
                   is_active, created_at, updated_at
            FROM team_policies
            WHERE id = $1
            """,
            policy_id,
        )
        if result is None:
            return None
        return self._row_to_policy(result)

    async def get_policy_by_team(self, team_id: UUID) -> TeamPolicy | None:
        """Get the policy for a team."""
        result = await self.db.fetch_one(
            """
            SELECT id, org_id, team_id, sources, default_action,
                   auto_investigate_min_severity, review_required_max_severity,
                   is_active, created_at, updated_at
            FROM team_policies
            WHERE team_id = $1 AND is_active = true
            """,
            team_id,
        )
        if result is None:
            return None
        return self._row_to_policy(result)

    async def list_policies(self, org_id: UUID) -> list[TeamPolicy]:
        """List all policies for an organization."""
        results = await self.db.fetch_all(
            """
            SELECT id, org_id, team_id, sources, default_action,
                   auto_investigate_min_severity, review_required_max_severity,
                   is_active, created_at, updated_at
            FROM team_policies
            WHERE org_id = $1
            ORDER BY created_at DESC
            """,
            org_id,
        )
        return [self._row_to_policy(row) for row in results]

    async def update_policy(
        self,
        policy_id: UUID,
        sources: list[str] | None = None,
        default_action: PolicyAction | None = None,
        auto_investigate_min_severity: str | None = None,
        review_required_max_severity: str | None = None,
        is_active: bool | None = None,
    ) -> TeamPolicy | None:
        """Update a team policy."""
        updates: list[str] = []
        args: list[Any] = [policy_id]
        idx = 2

        if sources is not None:
            updates.append(f"sources = ${idx}")
            args.append(sources)
            idx += 1

        if default_action is not None:
            updates.append(f"default_action = ${idx}")
            args.append(default_action.value)
            idx += 1

        if auto_investigate_min_severity is not None:
            updates.append(f"auto_investigate_min_severity = ${idx}")
            args.append(auto_investigate_min_severity)
            idx += 1

        if review_required_max_severity is not None:
            updates.append(f"review_required_max_severity = ${idx}")
            args.append(review_required_max_severity)
            idx += 1

        if is_active is not None:
            updates.append(f"is_active = ${idx}")
            args.append(is_active)
            idx += 1

        if not updates:
            return await self.get_policy(policy_id)

        query = f"""
            UPDATE team_policies
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = $1
            RETURNING id, org_id, team_id, sources, default_action,
                      auto_investigate_min_severity, review_required_max_severity,
                      is_active, created_at, updated_at
        """
        result = await self.db.execute_returning(query, *args)
        if result is None:
            return None
        return self._row_to_policy(result)

    async def delete_policy(self, policy_id: UUID) -> bool:
        """Delete a team policy."""
        result = await self.db.execute(
            "DELETE FROM team_policies WHERE id = $1",
            policy_id,
        )
        return "DELETE 1" in result

    # =========================================================================
    # Policy Override Operations
    # =========================================================================

    async def create_override(
        self,
        org_id: UUID,
        team_id: UUID,
        dataset_id: str | None = None,
        tag_id: UUID | None = None,
        default_action: PolicyAction | None = None,
        auto_investigate_min_severity: str | None = None,
        review_required_max_severity: str | None = None,
    ) -> TeamPolicyOverride:
        """Create a policy override for a dataset or tag."""
        if (dataset_id is None) == (tag_id is None):
            raise ValueError("Exactly one of dataset_id or tag_id must be set")

        result = await self.db.execute_returning(
            """
            INSERT INTO team_policy_overrides
                (org_id, team_id, dataset_id, tag_id, default_action,
                 auto_investigate_min_severity, review_required_max_severity)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, org_id, team_id, dataset_id, tag_id, default_action,
                      auto_investigate_min_severity, review_required_max_severity,
                      is_active, created_at, updated_at
            """,
            org_id,
            team_id,
            dataset_id,
            tag_id,
            default_action.value if default_action else None,
            auto_investigate_min_severity,
            review_required_max_severity,
        )
        if result is None:
            raise RuntimeError("Failed to create policy override")
        return self._row_to_override(result)

    async def get_override(self, override_id: UUID) -> TeamPolicyOverride | None:
        """Get a policy override by ID."""
        result = await self.db.fetch_one(
            """
            SELECT id, org_id, team_id, dataset_id, tag_id, default_action,
                   auto_investigate_min_severity, review_required_max_severity,
                   is_active, created_at, updated_at
            FROM team_policy_overrides
            WHERE id = $1
            """,
            override_id,
        )
        if result is None:
            return None
        return self._row_to_override(result)

    async def get_overrides_for_team(self, team_id: UUID) -> list[TeamPolicyOverride]:
        """Get all policy overrides for a team."""
        results = await self.db.fetch_all(
            """
            SELECT id, org_id, team_id, dataset_id, tag_id, default_action,
                   auto_investigate_min_severity, review_required_max_severity,
                   is_active, created_at, updated_at
            FROM team_policy_overrides
            WHERE team_id = $1 AND is_active = true
            ORDER BY created_at DESC
            """,
            team_id,
        )
        return [self._row_to_override(row) for row in results]

    async def get_override_for_dataset(
        self, team_id: UUID, dataset_id: str
    ) -> TeamPolicyOverride | None:
        """Get the override for a specific dataset."""
        result = await self.db.fetch_one(
            """
            SELECT id, org_id, team_id, dataset_id, tag_id, default_action,
                   auto_investigate_min_severity, review_required_max_severity,
                   is_active, created_at, updated_at
            FROM team_policy_overrides
            WHERE team_id = $1 AND dataset_id = $2 AND is_active = true
            """,
            team_id,
            dataset_id,
        )
        if result is None:
            return None
        return self._row_to_override(result)

    async def get_overrides_for_tag(self, team_id: UUID, tag_id: UUID) -> TeamPolicyOverride | None:
        """Get the override for a specific tag."""
        result = await self.db.fetch_one(
            """
            SELECT id, org_id, team_id, dataset_id, tag_id, default_action,
                   auto_investigate_min_severity, review_required_max_severity,
                   is_active, created_at, updated_at
            FROM team_policy_overrides
            WHERE team_id = $1 AND tag_id = $2 AND is_active = true
            """,
            team_id,
            tag_id,
        )
        if result is None:
            return None
        return self._row_to_override(result)

    async def update_override(
        self,
        override_id: UUID,
        default_action: PolicyAction | None = None,
        auto_investigate_min_severity: str | None = None,
        review_required_max_severity: str | None = None,
        is_active: bool | None = None,
    ) -> TeamPolicyOverride | None:
        """Update a policy override."""
        updates: list[str] = []
        args: list[Any] = [override_id]
        idx = 2

        if default_action is not None:
            updates.append(f"default_action = ${idx}")
            args.append(default_action.value)
            idx += 1

        if auto_investigate_min_severity is not None:
            updates.append(f"auto_investigate_min_severity = ${idx}")
            args.append(auto_investigate_min_severity)
            idx += 1

        if review_required_max_severity is not None:
            updates.append(f"review_required_max_severity = ${idx}")
            args.append(review_required_max_severity)
            idx += 1

        if is_active is not None:
            updates.append(f"is_active = ${idx}")
            args.append(is_active)
            idx += 1

        if not updates:
            return await self.get_override(override_id)

        query = f"""
            UPDATE team_policy_overrides
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = $1
            RETURNING id, org_id, team_id, dataset_id, tag_id, default_action,
                      auto_investigate_min_severity, review_required_max_severity,
                      is_active, created_at, updated_at
        """
        result = await self.db.execute_returning(query, *args)
        if result is None:
            return None
        return self._row_to_override(result)

    async def delete_override(self, override_id: UUID) -> bool:
        """Delete a policy override."""
        result = await self.db.execute(
            "DELETE FROM team_policy_overrides WHERE id = $1",
            override_id,
        )
        return "DELETE 1" in result

    # =========================================================================
    # Queue Limits Operations
    # =========================================================================

    async def create_queue_limits(
        self,
        org_id: UUID,
        team_id: UUID,
        rate_limit_per_minute: int = 60,
        burst_size: int = 10,
        max_concurrent: int = 5,
        batch_size: int = 5,
    ) -> TeamQueueLimits:
        """Create queue limits for a team."""
        result = await self.db.execute_returning(
            """
            INSERT INTO team_queue_limits
                (org_id, team_id, rate_limit_per_minute, burst_size,
                 max_concurrent, batch_size)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, org_id, team_id, rate_limit_per_minute, burst_size,
                      max_concurrent, batch_size, is_active, created_at, updated_at
            """,
            org_id,
            team_id,
            rate_limit_per_minute,
            burst_size,
            max_concurrent,
            batch_size,
        )
        if result is None:
            raise RuntimeError("Failed to create queue limits")
        return self._row_to_queue_limits(result)

    async def get_queue_limits(self, team_id: UUID) -> TeamQueueLimits | None:
        """Get queue limits for a team."""
        result = await self.db.fetch_one(
            """
            SELECT id, org_id, team_id, rate_limit_per_minute, burst_size,
                   max_concurrent, batch_size, is_active, created_at, updated_at
            FROM team_queue_limits
            WHERE team_id = $1 AND is_active = true
            """,
            team_id,
        )
        if result is None:
            return None
        return self._row_to_queue_limits(result)

    async def update_queue_limits(
        self,
        team_id: UUID,
        rate_limit_per_minute: int | None = None,
        burst_size: int | None = None,
        max_concurrent: int | None = None,
        batch_size: int | None = None,
    ) -> TeamQueueLimits | None:
        """Update queue limits for a team."""
        updates: list[str] = []
        args: list[Any] = [team_id]
        idx = 2

        if rate_limit_per_minute is not None:
            updates.append(f"rate_limit_per_minute = ${idx}")
            args.append(rate_limit_per_minute)
            idx += 1

        if burst_size is not None:
            updates.append(f"burst_size = ${idx}")
            args.append(burst_size)
            idx += 1

        if max_concurrent is not None:
            updates.append(f"max_concurrent = ${idx}")
            args.append(max_concurrent)
            idx += 1

        if batch_size is not None:
            updates.append(f"batch_size = ${idx}")
            args.append(batch_size)
            idx += 1

        if not updates:
            return await self.get_queue_limits(team_id)

        query = f"""
            UPDATE team_queue_limits
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE team_id = $1 AND is_active = true
            RETURNING id, org_id, team_id, rate_limit_per_minute, burst_size,
                      max_concurrent, batch_size, is_active, created_at, updated_at
        """
        result = await self.db.execute_returning(query, *args)
        if result is None:
            return None
        return self._row_to_queue_limits(result)

    # =========================================================================
    # Dataset Tags Operations
    # =========================================================================

    async def add_dataset_tag(self, dataset_id: UUID, tag_id: UUID) -> None:
        """Add a tag to a dataset."""
        await self.db.execute(
            """
            INSERT INTO dataset_tags (dataset_id, tag_id)
            VALUES ($1, $2)
            ON CONFLICT (dataset_id, tag_id) DO NOTHING
            """,
            dataset_id,
            tag_id,
        )

    async def remove_dataset_tag(self, dataset_id: UUID, tag_id: UUID) -> bool:
        """Remove a tag from a dataset."""
        result = await self.db.execute(
            "DELETE FROM dataset_tags WHERE dataset_id = $1 AND tag_id = $2",
            dataset_id,
            tag_id,
        )
        return "DELETE 1" in result

    async def get_dataset_tags(self, dataset_id: UUID) -> list[UUID]:
        """Get all tags for a dataset."""
        results = await self.db.fetch_all(
            "SELECT tag_id FROM dataset_tags WHERE dataset_id = $1",
            dataset_id,
        )
        return [row["tag_id"] for row in results]

    async def get_datasets_by_tag(self, tag_id: UUID) -> list[UUID]:
        """Get all datasets with a specific tag."""
        results = await self.db.fetch_all(
            "SELECT dataset_id FROM dataset_tags WHERE tag_id = $1",
            tag_id,
        )
        return [row["dataset_id"] for row in results]

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _row_to_policy(self, row: dict[str, Any]) -> TeamPolicy:
        """Convert a database row to a TeamPolicy."""
        return TeamPolicy(
            id=row["id"],
            org_id=row["org_id"],
            team_id=row["team_id"],
            sources=row["sources"] or [],
            default_action=PolicyAction(row["default_action"]),
            auto_investigate_min_severity=row["auto_investigate_min_severity"],
            review_required_max_severity=row["review_required_max_severity"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_override(self, row: dict[str, Any]) -> TeamPolicyOverride:
        """Convert a database row to a TeamPolicyOverride."""
        return TeamPolicyOverride(
            id=row["id"],
            org_id=row["org_id"],
            team_id=row["team_id"],
            dataset_id=row["dataset_id"],
            tag_id=row["tag_id"],
            default_action=PolicyAction(row["default_action"]) if row["default_action"] else None,
            auto_investigate_min_severity=row["auto_investigate_min_severity"],
            review_required_max_severity=row["review_required_max_severity"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_queue_limits(self, row: dict[str, Any]) -> TeamQueueLimits:
        """Convert a database row to TeamQueueLimits."""
        return TeamQueueLimits(
            id=row["id"],
            org_id=row["org_id"],
            team_id=row["team_id"],
            rate_limit_per_minute=row["rate_limit_per_minute"],
            burst_size=row["burst_size"],
            max_concurrent=row["max_concurrent"],
            batch_size=row["batch_size"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
