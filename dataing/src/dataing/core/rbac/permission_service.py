"""Permission evaluation service."""

import logging
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from dataing.core.rbac.types import Role

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class PermissionChecker(Protocol):
    """Protocol for permission checking."""

    async def can_access_investigation(self, user_id: UUID, investigation_id: UUID) -> bool:
        """Check if user can access an investigation."""
        ...

    async def get_accessible_investigation_ids(
        self, user_id: UUID, org_id: UUID
    ) -> list[UUID] | None:
        """Get IDs of investigations user can access. None means all."""
        ...


class PermissionService:
    """Service for evaluating permissions."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the service."""
        self._conn = conn

    async def can_access_investigation(self, user_id: UUID, investigation_id: UUID) -> bool:
        """Check if user can access an investigation.

        Returns True if ANY of these conditions are met:
        1. User has role 'owner' or 'admin'
        2. User created the investigation
        3. User has direct grant on the investigation
        4. User has grant on a tag the investigation has
        5. User has grant on the investigation's datasource
        6. User's team has any of the above grants
        """
        result = await self._conn.fetchval(
            """
            SELECT EXISTS (
                -- Role-based (owner/admin see everything in their org)
                SELECT 1 FROM org_memberships om
                JOIN investigations i ON i.tenant_id = om.org_id
                WHERE om.user_id = $1 AND i.id = $2 AND om.role IN ('owner', 'admin')

                UNION ALL

                -- Creator access
                SELECT 1 FROM investigations
                WHERE id = $2 AND created_by = $1

                UNION ALL

                -- Direct user grant on investigation
                SELECT 1 FROM permission_grants
                WHERE user_id = $1
                  AND resource_type = 'investigation'
                  AND resource_id = $2

                UNION ALL

                -- Tag-based grant (user)
                SELECT 1 FROM permission_grants pg
                JOIN investigation_tags it ON pg.tag_id = it.tag_id
                WHERE pg.user_id = $1 AND it.investigation_id = $2

                UNION ALL

                -- Datasource-based grant (user)
                SELECT 1 FROM permission_grants pg
                JOIN investigations i ON pg.data_source_id = i.data_source_id
                WHERE pg.user_id = $1 AND i.id = $2

                UNION ALL

                -- Team grants (direct on investigation)
                SELECT 1 FROM permission_grants pg
                JOIN team_members tm ON pg.team_id = tm.team_id
                WHERE tm.user_id = $1
                  AND pg.resource_type = 'investigation'
                  AND pg.resource_id = $2

                UNION ALL

                -- Team grants (tag-based)
                SELECT 1 FROM permission_grants pg
                JOIN team_members tm ON pg.team_id = tm.team_id
                JOIN investigation_tags it ON pg.tag_id = it.tag_id
                WHERE tm.user_id = $1 AND it.investigation_id = $2

                UNION ALL

                -- Team grants (datasource-based)
                SELECT 1 FROM permission_grants pg
                JOIN team_members tm ON pg.team_id = tm.team_id
                JOIN investigations i ON pg.data_source_id = i.data_source_id
                WHERE tm.user_id = $1 AND i.id = $2
            )
            """,
            user_id,
            investigation_id,
        )
        has_access: bool = result or False
        return has_access

    async def get_accessible_investigation_ids(
        self, user_id: UUID, org_id: UUID
    ) -> list[UUID] | None:
        """Get IDs of investigations user can access.

        Returns None if user is admin/owner (can see all).
        Returns list of IDs otherwise.
        """
        # Check if admin/owner
        role = await self._conn.fetchval(
            "SELECT role FROM org_memberships WHERE user_id = $1 AND org_id = $2",
            user_id,
            org_id,
        )

        if role in (Role.OWNER.value, Role.ADMIN.value):
            return None  # Can see all

        # Get accessible investigation IDs
        rows = await self._conn.fetch(
            """
            SELECT DISTINCT i.id
            FROM investigations i
            WHERE i.tenant_id = $2
            AND (
                -- Creator
                i.created_by = $1

                -- Direct grant
                OR EXISTS (
                    SELECT 1 FROM permission_grants pg
                    WHERE pg.user_id = $1
                      AND pg.resource_type = 'investigation'
                      AND pg.resource_id = i.id
                )

                -- Tag grant (user)
                OR EXISTS (
                    SELECT 1 FROM permission_grants pg
                    JOIN investigation_tags it ON pg.tag_id = it.tag_id
                    WHERE pg.user_id = $1 AND it.investigation_id = i.id
                )

                -- Datasource grant (user)
                OR EXISTS (
                    SELECT 1 FROM permission_grants pg
                    WHERE pg.user_id = $1 AND pg.data_source_id = i.data_source_id
                )

                -- Team grants
                OR EXISTS (
                    SELECT 1 FROM permission_grants pg
                    JOIN team_members tm ON pg.team_id = tm.team_id
                    WHERE tm.user_id = $1
                    AND (
                        (pg.resource_type = 'investigation' AND pg.resource_id = i.id)
                        OR pg.tag_id IN (
                            SELECT tag_id FROM investigation_tags
                            WHERE investigation_id = i.id
                        )
                        OR pg.data_source_id = i.data_source_id
                    )
                )
            )
            """,
            user_id,
            org_id,
        )

        return [row["id"] for row in rows]

    async def get_user_role(self, user_id: UUID, org_id: UUID) -> Role | None:
        """Get user's role in an organization."""
        role_str = await self._conn.fetchval(
            "SELECT role FROM org_memberships WHERE user_id = $1 AND org_id = $2",
            user_id,
            org_id,
        )
        if role_str:
            return Role(role_str)
        return None

    async def is_admin_or_owner(self, user_id: UUID, org_id: UUID) -> bool:
        """Check if user is admin or owner."""
        role = await self.get_user_role(user_id, org_id)
        return role in (Role.OWNER, Role.ADMIN)
