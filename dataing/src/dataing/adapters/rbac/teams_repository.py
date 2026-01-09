"""Teams repository."""

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.rbac import Team

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class TeamsRepository:
    """Repository for team operations."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository."""
        self._conn = conn

    async def create(
        self,
        org_id: UUID,
        name: str,
        external_id: str | None = None,
        is_scim_managed: bool = False,
    ) -> Team:
        """Create a new team."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO teams (org_id, name, external_id, is_scim_managed)
            VALUES ($1, $2, $3, $4)
            RETURNING id, org_id, name, external_id, is_scim_managed, created_at, updated_at
            """,
            org_id,
            name,
            external_id,
            is_scim_managed,
        )
        return self._row_to_team(row)

    async def get_by_id(self, team_id: UUID) -> Team | None:
        """Get team by ID."""
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, name, external_id, is_scim_managed, created_at, updated_at
            FROM teams WHERE id = $1
            """,
            team_id,
        )
        if not row:
            return None
        return self._row_to_team(row)

    async def get_by_external_id(self, org_id: UUID, external_id: str) -> Team | None:
        """Get team by external ID (SCIM)."""
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, name, external_id, is_scim_managed, created_at, updated_at
            FROM teams WHERE org_id = $1 AND external_id = $2
            """,
            org_id,
            external_id,
        )
        if not row:
            return None
        return self._row_to_team(row)

    async def list_by_org(self, org_id: UUID) -> list[Team]:
        """List all teams in an organization."""
        rows = await self._conn.fetch(
            """
            SELECT id, org_id, name, external_id, is_scim_managed, created_at, updated_at
            FROM teams WHERE org_id = $1 ORDER BY name
            """,
            org_id,
        )
        return [self._row_to_team(row) for row in rows]

    async def update(self, team_id: UUID, name: str) -> Team | None:
        """Update team name."""
        row = await self._conn.fetchrow(
            """
            UPDATE teams SET name = $2, updated_at = NOW()
            WHERE id = $1
            RETURNING id, org_id, name, external_id, is_scim_managed, created_at, updated_at
            """,
            team_id,
            name,
        )
        if not row:
            return None
        return self._row_to_team(row)

    async def delete(self, team_id: UUID) -> bool:
        """Delete a team."""
        result: str = await self._conn.execute(
            "DELETE FROM teams WHERE id = $1",
            team_id,
        )
        return result == "DELETE 1"

    async def add_member(self, team_id: UUID, user_id: UUID) -> bool:
        """Add a user to a team."""
        try:
            await self._conn.execute(
                """
                INSERT INTO team_members (team_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT (team_id, user_id) DO NOTHING
                """,
                team_id,
                user_id,
            )
            return True
        except Exception:
            logger.exception(f"Failed to add member {user_id} to team {team_id}")
            return False

    async def remove_member(self, team_id: UUID, user_id: UUID) -> bool:
        """Remove a user from a team."""
        result: str = await self._conn.execute(
            "DELETE FROM team_members WHERE team_id = $1 AND user_id = $2",
            team_id,
            user_id,
        )
        return result == "DELETE 1"

    async def get_members(self, team_id: UUID) -> list[UUID]:
        """Get user IDs of team members."""
        rows = await self._conn.fetch(
            "SELECT user_id FROM team_members WHERE team_id = $1",
            team_id,
        )
        return [row["user_id"] for row in rows]

    async def get_user_teams(self, user_id: UUID) -> list[Team]:
        """Get teams a user belongs to."""
        rows = await self._conn.fetch(
            """
            SELECT t.id, t.org_id, t.name, t.external_id, t.is_scim_managed,
                   t.created_at, t.updated_at
            FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.user_id = $1
            ORDER BY t.name
            """,
            user_id,
        )
        return [self._row_to_team(row) for row in rows]

    def _row_to_team(self, row: dict[str, Any]) -> Team:
        """Convert database row to Team."""
        return Team(
            id=row["id"],
            org_id=row["org_id"],
            name=row["name"],
            external_id=row["external_id"],
            is_scim_managed=row["is_scim_managed"],
            created_at=row["created_at"].replace(tzinfo=UTC),
            updated_at=row["updated_at"].replace(tzinfo=UTC),
        )
