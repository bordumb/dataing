"""Permissions repository."""

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.rbac import Permission, PermissionGrant

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class PermissionsRepository:
    """Repository for permission grant operations."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository."""
        self._conn = conn

    async def create_user_resource_grant(
        self,
        org_id: UUID,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a direct user -> resource grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, user_id, resource_type, resource_id, permission, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            org_id,
            user_id,
            resource_type,
            resource_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def create_user_tag_grant(
        self,
        org_id: UUID,
        user_id: UUID,
        tag_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a user -> tag grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, user_id, resource_type, tag_id, permission, created_by)
            VALUES ($1, $2, 'investigation', $3, $4, $5)
            RETURNING *
            """,
            org_id,
            user_id,
            tag_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def create_user_datasource_grant(
        self,
        org_id: UUID,
        user_id: UUID,
        data_source_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a user -> datasource grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, user_id, resource_type, data_source_id, permission, created_by)
            VALUES ($1, $2, 'investigation', $3, $4, $5)
            RETURNING *
            """,
            org_id,
            user_id,
            data_source_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def create_team_resource_grant(
        self,
        org_id: UUID,
        team_id: UUID,
        resource_type: str,
        resource_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a team -> resource grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, team_id, resource_type, resource_id, permission, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            org_id,
            team_id,
            resource_type,
            resource_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def create_team_tag_grant(
        self,
        org_id: UUID,
        team_id: UUID,
        tag_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a team -> tag grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, team_id, resource_type, tag_id, permission, created_by)
            VALUES ($1, $2, 'investigation', $3, $4, $5)
            RETURNING *
            """,
            org_id,
            team_id,
            tag_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def delete(self, grant_id: UUID) -> bool:
        """Delete a permission grant."""
        result: str = await self._conn.execute(
            "DELETE FROM permission_grants WHERE id = $1",
            grant_id,
        )
        return result == "DELETE 1"

    async def list_by_org(self, org_id: UUID) -> list[PermissionGrant]:
        """List all grants in an organization."""
        rows = await self._conn.fetch(
            "SELECT * FROM permission_grants WHERE org_id = $1 ORDER BY created_at DESC",
            org_id,
        )
        return [self._row_to_grant(row) for row in rows]

    async def list_by_user(self, user_id: UUID) -> list[PermissionGrant]:
        """List all grants for a user."""
        rows = await self._conn.fetch(
            "SELECT * FROM permission_grants WHERE user_id = $1",
            user_id,
        )
        return [self._row_to_grant(row) for row in rows]

    async def list_by_resource(
        self, resource_type: str, resource_id: UUID
    ) -> list[PermissionGrant]:
        """List all grants for a resource."""
        rows = await self._conn.fetch(
            """
            SELECT * FROM permission_grants
            WHERE resource_type = $1 AND resource_id = $2
            """,
            resource_type,
            resource_id,
        )
        return [self._row_to_grant(row) for row in rows]

    def _row_to_grant(self, row: dict[str, Any]) -> PermissionGrant:
        """Convert database row to PermissionGrant."""
        return PermissionGrant(
            id=row["id"],
            org_id=row["org_id"],
            user_id=row["user_id"],
            team_id=row["team_id"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            tag_id=row["tag_id"],
            data_source_id=row["data_source_id"],
            permission=Permission(row["permission"]),
            created_at=row["created_at"].replace(tzinfo=UTC),
            created_by=row["created_by"],
        )
