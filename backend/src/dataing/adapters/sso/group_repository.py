"""Group repository for SCIM operations."""

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.adapters.rbac import TeamsRepository

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)

# Role prefix for SCIM groups that map to user roles
ROLE_PREFIX = "role-"


class SCIMGroupRepository:
    """Repository for SCIM group operations.

    Groups prefixed with 'role-' map to user roles.
    All other groups map to teams.
    """

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository."""
        self._conn = conn
        self._teams_repo = TeamsRepository(conn)

    def _is_role_group(self, display_name: str) -> bool:
        """Check if group name indicates a role group."""
        return display_name.lower().startswith(ROLE_PREFIX)

    def _extract_role(self, display_name: str) -> str:
        """Extract role name from role group display name."""
        return display_name[len(ROLE_PREFIX) :].lower()

    async def create_group(
        self,
        org_id: UUID,
        display_name: str,
        external_id: str | None = None,
        member_ids: list[UUID] | None = None,
    ) -> dict[str, Any]:
        """Create a SCIM group.

        If the group name starts with 'role-', it's a role group.
        Otherwise, it creates a team.

        Args:
            org_id: Organization/tenant ID.
            display_name: Group display name.
            external_id: External ID from the IdP.
            member_ids: List of user IDs to add as members.

        Returns:
            Created group data.
        """
        if self._is_role_group(display_name):
            return await self._create_role_group(
                org_id, display_name, external_id, member_ids or []
            )
        else:
            return await self._create_team_group(
                org_id, display_name, external_id, member_ids or []
            )

    async def _create_role_group(
        self,
        org_id: UUID,
        display_name: str,
        external_id: str | None,
        member_ids: list[UUID],
    ) -> dict[str, Any]:
        """Create a role group and assign role to members."""
        role = self._extract_role(display_name)

        # Validate role
        if role not in ("owner", "admin", "member"):
            raise ValueError(f"Invalid role: {role}. Must be owner, admin, or member.")

        # Track role group in scim_role_groups table
        row = await self._conn.fetchrow(
            """
            INSERT INTO scim_role_groups (org_id, external_id, role_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (org_id, external_id) DO UPDATE SET role_name = $3
            RETURNING id, org_id, external_id, role_name, created_at
            """,
            org_id,
            external_id or display_name,
            role,
        )

        # Update role for all members
        for user_id in member_ids:
            await self._conn.execute(
                """
                UPDATE users SET role = $2, updated_at = NOW()
                WHERE id = $1 AND tenant_id = $3
                """,
                user_id,
                role,
                org_id,
            )

        return {
            "id": str(row["id"]),
            "display_name": display_name,
            "external_id": row["external_id"],
            "is_role_group": True,
            "role": role,
            "member_count": len(member_ids),
        }

    async def _create_team_group(
        self,
        org_id: UUID,
        display_name: str,
        external_id: str | None,
        member_ids: list[UUID],
    ) -> dict[str, Any]:
        """Create a team group."""
        team = await self._teams_repo.create(
            org_id=org_id,
            name=display_name,
            external_id=external_id,
            is_scim_managed=True,
        )

        # Add members
        for user_id in member_ids:
            await self._teams_repo.add_member(team.id, user_id)

        return {
            "id": str(team.id),
            "display_name": team.name,
            "external_id": team.external_id,
            "is_role_group": False,
            "member_count": len(member_ids),
        }

    async def get_group(self, org_id: UUID, group_id: UUID) -> dict[str, Any] | None:
        """Get a group by ID (could be team or role group).

        Args:
            org_id: Organization/tenant ID.
            group_id: Group ID.

        Returns:
            Group data if found, None otherwise.
        """
        # Try team first
        team = await self._teams_repo.get_by_id(group_id)
        if team and team.org_id == org_id:
            members = await self._teams_repo.get_members(team.id)
            return {
                "id": str(team.id),
                "display_name": team.name,
                "external_id": team.external_id,
                "is_role_group": False,
                "member_ids": [str(m) for m in members],
            }

        # Try role group
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, external_id, role_name, created_at
            FROM scim_role_groups
            WHERE id = $1 AND org_id = $2
            """,
            group_id,
            org_id,
        )
        if row:
            # Get users with this role
            users = await self._conn.fetch(
                "SELECT id FROM users WHERE tenant_id = $1 AND role = $2",
                org_id,
                row["role_name"],
            )
            return {
                "id": str(row["id"]),
                "display_name": f"{ROLE_PREFIX}{row['role_name']}",
                "external_id": row["external_id"],
                "is_role_group": True,
                "role": row["role_name"],
                "member_ids": [str(u["id"]) for u in users],
            }

        return None

    async def get_group_by_external_id(
        self, org_id: UUID, external_id: str
    ) -> dict[str, Any] | None:
        """Get a group by external ID.

        Args:
            org_id: Organization/tenant ID.
            external_id: External ID from the IdP.

        Returns:
            Group data if found, None otherwise.
        """
        # Try team first
        team = await self._teams_repo.get_by_external_id(org_id, external_id)
        if team:
            members = await self._teams_repo.get_members(team.id)
            return {
                "id": str(team.id),
                "display_name": team.name,
                "external_id": team.external_id,
                "is_role_group": False,
                "member_ids": [str(m) for m in members],
            }

        # Try role group
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, external_id, role_name, created_at
            FROM scim_role_groups
            WHERE org_id = $1 AND external_id = $2
            """,
            org_id,
            external_id,
        )
        if row:
            # Get users with this role
            users = await self._conn.fetch(
                "SELECT id FROM users WHERE tenant_id = $1 AND role = $2",
                org_id,
                row["role_name"],
            )
            return {
                "id": str(row["id"]),
                "display_name": f"{ROLE_PREFIX}{row['role_name']}",
                "external_id": row["external_id"],
                "is_role_group": True,
                "role": row["role_name"],
                "member_ids": [str(u["id"]) for u in users],
            }

        return None

    async def delete_group(self, org_id: UUID, group_id: UUID) -> bool:
        """Delete a group.

        Args:
            org_id: Organization/tenant ID.
            group_id: Group ID.

        Returns:
            True if deleted, False if not found.
        """
        # Try deleting team
        team = await self._teams_repo.get_by_id(group_id)
        if team and team.org_id == org_id:
            return await self._teams_repo.delete(group_id)

        # Try deleting role group (doesn't remove role from users)
        result: str = await self._conn.execute(
            "DELETE FROM scim_role_groups WHERE id = $1 AND org_id = $2",
            group_id,
            org_id,
        )
        return result == "DELETE 1"

    async def list_groups(
        self,
        org_id: UUID,
        start_index: int = 1,
        count: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        """List all groups (teams + role groups).

        Args:
            org_id: Organization/tenant ID.
            start_index: 1-based start index for pagination.
            count: Maximum number of groups to return.

        Returns:
            Tuple of (list of group dicts, total count).
        """
        groups: list[dict[str, Any]] = []

        # Get teams
        teams = await self._teams_repo.list_by_org(org_id)
        for team in teams:
            members = await self._teams_repo.get_members(team.id)
            groups.append(
                {
                    "id": str(team.id),
                    "display_name": team.name,
                    "external_id": team.external_id,
                    "is_role_group": False,
                    "member_ids": [str(m) for m in members],
                }
            )

        # Get role groups
        role_rows = await self._conn.fetch(
            "SELECT id, external_id, role_name FROM scim_role_groups WHERE org_id = $1",
            org_id,
        )
        for row in role_rows:
            users = await self._conn.fetch(
                "SELECT id FROM users WHERE tenant_id = $1 AND role = $2",
                org_id,
                row["role_name"],
            )
            groups.append(
                {
                    "id": str(row["id"]),
                    "display_name": f"{ROLE_PREFIX}{row['role_name']}",
                    "external_id": row["external_id"],
                    "is_role_group": True,
                    "role": row["role_name"],
                    "member_ids": [str(u["id"]) for u in users],
                }
            )

        total = len(groups)
        # Apply pagination
        start = start_index - 1
        end = start + count
        return groups[start:end], total

    async def update_group(
        self,
        org_id: UUID,
        group_id: UUID,
        display_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a group's display name.

        Args:
            org_id: Organization/tenant ID.
            group_id: Group ID.
            display_name: New display name.

        Returns:
            Updated group data if found, None otherwise.
        """
        group = await self.get_group(org_id, group_id)
        if not group:
            return None

        if display_name and not group["is_role_group"]:
            # Only update team names (role groups have fixed names)
            await self._teams_repo.update(group_id, display_name)

        return await self.get_group(org_id, group_id)

    async def update_group_members(
        self,
        org_id: UUID,
        group_id: UUID,
        member_ids: list[UUID],
    ) -> dict[str, Any] | None:
        """Update group membership (replace all members).

        Args:
            org_id: Organization/tenant ID.
            group_id: Group ID.
            member_ids: New list of member user IDs.

        Returns:
            Updated group data if found, None otherwise.
        """
        group = await self.get_group(org_id, group_id)
        if not group:
            return None

        if group["is_role_group"]:
            # For role groups, update user roles
            role = group["role"]
            # Remove role from current members (set to member)
            current_members = [UUID(m) for m in group["member_ids"]]
            for user_id in current_members:
                if user_id not in member_ids:
                    await self._conn.execute(
                        """
                        UPDATE users SET role = 'member', updated_at = NOW()
                        WHERE id = $1 AND tenant_id = $2
                        """,
                        user_id,
                        org_id,
                    )
            # Add role to new members
            for user_id in member_ids:
                await self._conn.execute(
                    """
                    UPDATE users SET role = $2, updated_at = NOW()
                    WHERE id = $1 AND tenant_id = $3
                    """,
                    user_id,
                    role,
                    org_id,
                )
        else:
            # For team groups, update team membership
            team_id = UUID(group["id"])
            current_members = await self._teams_repo.get_members(team_id)
            # Remove members not in new list
            for user_id in current_members:
                if user_id not in member_ids:
                    await self._teams_repo.remove_member(team_id, user_id)
            # Add new members
            for user_id in member_ids:
                await self._teams_repo.add_member(team_id, user_id)

        return await self.get_group(org_id, group_id)

    async def add_group_member(
        self,
        org_id: UUID,
        group_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Add a member to a group.

        Args:
            org_id: Organization/tenant ID.
            group_id: Group ID.
            user_id: User ID to add.

        Returns:
            True if added, False if group not found.
        """
        group = await self.get_group(org_id, group_id)
        if not group:
            return False

        if group["is_role_group"]:
            # Assign role to user
            await self._conn.execute(
                """
                UPDATE users SET role = $2, updated_at = NOW()
                WHERE id = $1 AND tenant_id = $3
                """,
                user_id,
                group["role"],
                org_id,
            )
        else:
            # Add to team
            team_id = UUID(group["id"])
            await self._teams_repo.add_member(team_id, user_id)

        return True

    async def remove_group_member(
        self,
        org_id: UUID,
        group_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Remove a member from a group.

        Args:
            org_id: Organization/tenant ID.
            group_id: Group ID.
            user_id: User ID to remove.

        Returns:
            True if removed, False if group not found.
        """
        group = await self.get_group(org_id, group_id)
        if not group:
            return False

        if group["is_role_group"]:
            # Set user role back to member
            await self._conn.execute(
                """
                UPDATE users SET role = 'member', updated_at = NOW()
                WHERE id = $1 AND tenant_id = $2
                """,
                user_id,
                org_id,
            )
        else:
            # Remove from team
            team_id = UUID(group["id"])
            await self._teams_repo.remove_member(team_id, user_id)

        return True
