"""User repository for SCIM operations."""

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class SCIMUserRepository:
    """Repository for SCIM user operations."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository."""
        self._conn = conn

    async def create_user(
        self,
        org_id: UUID,
        email: str,
        name: str | None = None,
        external_id: str | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        """Create a new user via SCIM.

        Args:
            org_id: Organization/tenant ID.
            email: User's email address.
            name: User's display name.
            external_id: External ID from the IdP.
            is_active: Whether the user is active.

        Returns:
            Created user data.
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO users (tenant_id, email, name, role, is_active)
            VALUES ($1, $2, $3, 'member', $4)
            RETURNING id, tenant_id, email, name, role, is_active, created_at, updated_at
            """,
            org_id,
            email,
            name,
            is_active,
        )

        user_id = row["id"]

        # Create SSO identity link if external_id provided
        if external_id:
            # Get the org's SSO config
            sso_config = await self._conn.fetchrow(
                "SELECT id FROM sso_configs WHERE org_id = $1 AND is_enabled = true",
                org_id,
            )
            if sso_config:
                await self._conn.execute(
                    """
                    INSERT INTO sso_identities (user_id, sso_config_id, idp_user_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (sso_config_id, idp_user_id) DO NOTHING
                    """,
                    user_id,
                    sso_config["id"],
                    external_id,
                )

        return dict(row)

    async def get_user_by_id(self, org_id: UUID, user_id: UUID) -> dict[str, Any] | None:
        """Get user by ID within an organization.

        Args:
            org_id: Organization/tenant ID.
            user_id: User ID.

        Returns:
            User data if found, None otherwise.
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, tenant_id, email, name, role, is_active, created_at, updated_at
            FROM users WHERE id = $1 AND tenant_id = $2
            """,
            user_id,
            org_id,
        )
        if not row:
            return None
        return dict(row)

    async def get_user_by_email(self, org_id: UUID, email: str) -> dict[str, Any] | None:
        """Get user by email in an org.

        Args:
            org_id: Organization/tenant ID.
            email: User's email address.

        Returns:
            User data if found, None otherwise.
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, tenant_id, email, name, role, is_active, created_at, updated_at
            FROM users WHERE tenant_id = $1 AND email = $2
            """,
            org_id,
            email,
        )
        if not row:
            return None
        return dict(row)

    async def get_user_by_external_id(
        self, org_id: UUID, external_id: str
    ) -> dict[str, Any] | None:
        """Get user by external ID (from IdP).

        Args:
            org_id: Organization/tenant ID.
            external_id: External ID from the IdP.

        Returns:
            User data if found, None otherwise.
        """
        row = await self._conn.fetchrow(
            """
            SELECT u.id, u.tenant_id, u.email, u.name, u.role, u.is_active,
                   u.created_at, u.updated_at
            FROM users u
            JOIN sso_identities si ON u.id = si.user_id
            JOIN sso_configs sc ON si.sso_config_id = sc.id
            WHERE sc.org_id = $1 AND si.idp_user_id = $2
            """,
            org_id,
            external_id,
        )
        if not row:
            return None
        return dict(row)

    async def update_user(
        self,
        org_id: UUID,
        user_id: UUID,
        email: str | None = None,
        name: str | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any] | None:
        """Update a user within an organization.

        Args:
            org_id: Organization/tenant ID.
            user_id: User ID.
            email: New email address.
            name: New display name.
            is_active: New active status.

        Returns:
            Updated user data if found, None otherwise.
        """
        updates = []
        params: list[Any] = [user_id, org_id]
        idx = 3

        if email is not None:
            updates.append(f"email = ${idx}")
            params.append(email)
            idx += 1

        if name is not None:
            updates.append(f"name = ${idx}")
            params.append(name)
            idx += 1

        if is_active is not None:
            updates.append(f"is_active = ${idx}")
            params.append(is_active)
            idx += 1

        if not updates:
            return await self.get_user_by_id(org_id, user_id)

        updates.append("updated_at = NOW()")

        query = f"""
            UPDATE users SET {', '.join(updates)}
            WHERE id = $1 AND tenant_id = $2
            RETURNING id, tenant_id, email, name, role, is_active, created_at, updated_at
        """

        row = await self._conn.fetchrow(query, *params)
        if not row:
            return None
        return dict(row)

    async def deactivate_user(self, org_id: UUID, user_id: UUID) -> bool:
        """Deactivate a user (soft delete).

        Args:
            org_id: Organization/tenant ID.
            user_id: User ID.

        Returns:
            True if deactivated, False if not found.
        """
        result: str = await self._conn.execute(
            "UPDATE users SET is_active = false, updated_at = NOW() "
            "WHERE id = $1 AND tenant_id = $2",
            user_id,
            org_id,
        )
        return result == "UPDATE 1"

    async def list_users(
        self,
        org_id: UUID,
        start_index: int = 1,
        count: int = 100,
        filter_email: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List users with pagination and optional filter.

        Args:
            org_id: Organization/tenant ID.
            start_index: 1-based start index for pagination.
            count: Maximum number of users to return.
            filter_email: Optional email filter.

        Returns:
            Tuple of (list of user dicts, total count).
        """
        # Count total
        if filter_email:
            total = await self._conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE tenant_id = $1 AND email = $2",
                org_id,
                filter_email,
            )
            rows = await self._conn.fetch(
                """
                SELECT id, tenant_id, email, name, role, is_active, created_at, updated_at
                FROM users WHERE tenant_id = $1 AND email = $2
                ORDER BY created_at
                OFFSET $3 LIMIT $4
                """,
                org_id,
                filter_email,
                start_index - 1,
                count,
            )
        else:
            total = await self._conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE tenant_id = $1",
                org_id,
            )
            rows = await self._conn.fetch(
                """
                SELECT id, tenant_id, email, name, role, is_active, created_at, updated_at
                FROM users WHERE tenant_id = $1
                ORDER BY created_at
                OFFSET $2 LIMIT $3
                """,
                org_id,
                start_index - 1,
                count,
            )

        return [dict(row) for row in rows], total or 0

    async def update_user_role(self, org_id: UUID, user_id: UUID, role: str) -> bool:
        """Update user's role.

        Args:
            org_id: Organization/tenant ID.
            user_id: User ID.
            role: New role.

        Returns:
            True if updated, False if not found.
        """
        result: str = await self._conn.execute(
            "UPDATE users SET role = $2, updated_at = NOW() WHERE id = $1 AND tenant_id = $3",
            user_id,
            role,
            org_id,
        )
        return result == "UPDATE 1"
