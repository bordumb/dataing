"""PostgreSQL implementation of AuthRepository."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.auth.types import (
    Organization,
    OrgMembership,
    OrgRole,
    Team,
    TeamMembership,
    User,
)


class PostgresAuthRepository:
    """PostgreSQL implementation of auth repository."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize with database connection.

        Args:
            db: Application database instance.
        """
        self._db = db

    def _row_to_user(self, row: dict[str, Any]) -> User:
        """Convert database row to User model."""
        return User(
            id=row["id"],
            email=row["email"],
            name=row.get("name"),
            password_hash=row.get("password_hash"),
            is_active=row.get("is_active", True),
            created_at=row["created_at"],
        )

    def _row_to_org(self, row: dict[str, Any]) -> Organization:
        """Convert database row to Organization model."""
        return Organization(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            plan=row.get("plan", "free"),
            created_at=row["created_at"],
        )

    def _row_to_team(self, row: dict[str, Any]) -> Team:
        """Convert database row to Team model."""
        return Team(
            id=row["id"],
            org_id=row["org_id"],
            name=row["name"],
            created_at=row["created_at"],
        )

    # User operations
    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Get user by ID."""
        row = await self._db.fetch_one(
            "SELECT * FROM users WHERE id = $1",
            user_id,
        )
        return self._row_to_user(row) if row else None

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        row = await self._db.fetch_one(
            "SELECT * FROM users WHERE email = $1",
            email,
        )
        return self._row_to_user(row) if row else None

    async def create_user(
        self,
        email: str,
        name: str | None = None,
        password_hash: str | None = None,
    ) -> User:
        """Create a new user."""
        row = await self._db.fetch_one(
            """
            INSERT INTO users (email, name, password_hash)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            email,
            name,
            password_hash,
        )
        assert row is not None, "INSERT RETURNING should always return a row"
        return self._row_to_user(row)

    async def update_user(
        self,
        user_id: UUID,
        name: str | None = None,
        password_hash: str | None = None,
        is_active: bool | None = None,
    ) -> User | None:
        """Update user fields."""
        updates = []
        params: list[Any] = []
        param_idx = 1

        if name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(name)
            param_idx += 1

        if password_hash is not None:
            updates.append(f"password_hash = ${param_idx}")
            params.append(password_hash)
            param_idx += 1

        if is_active is not None:
            updates.append(f"is_active = ${param_idx}")
            params.append(is_active)
            param_idx += 1

        if not updates:
            return await self.get_user_by_id(user_id)

        updates.append(f"updated_at = ${param_idx}")
        params.append(datetime.now(UTC))
        param_idx += 1

        params.append(user_id)
        query = f"""
            UPDATE users SET {", ".join(updates)}
            WHERE id = ${param_idx}
            RETURNING *
        """
        row = await self._db.fetch_one(query, *params)
        return self._row_to_user(row) if row else None

    # Organization operations
    async def get_org_by_id(self, org_id: UUID) -> Organization | None:
        """Get organization by ID."""
        row = await self._db.fetch_one(
            "SELECT * FROM organizations WHERE id = $1",
            org_id,
        )
        return self._row_to_org(row) if row else None

    async def get_org_by_slug(self, slug: str) -> Organization | None:
        """Get organization by slug."""
        row = await self._db.fetch_one(
            "SELECT * FROM organizations WHERE slug = $1",
            slug,
        )
        return self._row_to_org(row) if row else None

    async def create_org(
        self,
        name: str,
        slug: str,
        plan: str = "free",
    ) -> Organization:
        """Create a new organization."""
        row = await self._db.fetch_one(
            """
            INSERT INTO organizations (name, slug, plan)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            name,
            slug,
            plan,
        )
        assert row is not None, "INSERT RETURNING should always return a row"
        return self._row_to_org(row)

    # Team operations
    async def get_team_by_id(self, team_id: UUID) -> Team | None:
        """Get team by ID."""
        row = await self._db.fetch_one(
            "SELECT * FROM teams WHERE id = $1",
            team_id,
        )
        return self._row_to_team(row) if row else None

    async def get_org_teams(self, org_id: UUID) -> list[Team]:
        """Get all teams in an organization."""
        rows = await self._db.fetch_all(
            "SELECT * FROM teams WHERE org_id = $1 ORDER BY name",
            org_id,
        )
        return [self._row_to_team(row) for row in rows]

    async def create_team(self, org_id: UUID, name: str) -> Team:
        """Create a new team in an organization."""
        row = await self._db.fetch_one(
            """
            INSERT INTO teams (org_id, name)
            VALUES ($1, $2)
            RETURNING *
            """,
            org_id,
            name,
        )
        assert row is not None, "INSERT RETURNING should always return a row"
        return self._row_to_team(row)

    # Membership operations
    async def get_user_org_membership(self, user_id: UUID, org_id: UUID) -> OrgMembership | None:
        """Get user's membership in an organization."""
        row = await self._db.fetch_one(
            "SELECT * FROM org_memberships WHERE user_id = $1 AND org_id = $2",
            user_id,
            org_id,
        )
        if not row:
            return None
        return OrgMembership(
            user_id=row["user_id"],
            org_id=row["org_id"],
            role=OrgRole(row["role"]),
            created_at=row["created_at"],
        )

    async def get_user_orgs(self, user_id: UUID) -> list[tuple[Organization, OrgRole]]:
        """Get all organizations a user belongs to with their roles."""
        rows = await self._db.fetch_all(
            """
            SELECT o.*, m.role
            FROM organizations o
            JOIN org_memberships m ON o.id = m.org_id
            WHERE m.user_id = $1
            ORDER BY o.name
            """,
            user_id,
        )
        return [(self._row_to_org(row), OrgRole(row["role"])) for row in rows]

    async def add_user_to_org(
        self,
        user_id: UUID,
        org_id: UUID,
        role: OrgRole = OrgRole.MEMBER,
    ) -> OrgMembership:
        """Add user to organization with role."""
        row = await self._db.fetch_one(
            """
            INSERT INTO org_memberships (user_id, org_id, role)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            user_id,
            org_id,
            role.value,
        )
        assert row is not None, "INSERT RETURNING should always return a row"
        return OrgMembership(
            user_id=row["user_id"],
            org_id=row["org_id"],
            role=OrgRole(row["role"]),
            created_at=row["created_at"],
        )

    async def get_user_teams(self, user_id: UUID, org_id: UUID) -> list[Team]:
        """Get teams user belongs to within an org."""
        rows = await self._db.fetch_all(
            """
            SELECT t.*
            FROM teams t
            JOIN team_memberships tm ON t.id = tm.team_id
            WHERE tm.user_id = $1 AND t.org_id = $2
            ORDER BY t.name
            """,
            user_id,
            org_id,
        )
        return [self._row_to_team(row) for row in rows]

    async def add_user_to_team(self, user_id: UUID, team_id: UUID) -> TeamMembership:
        """Add user to a team."""
        row = await self._db.fetch_one(
            """
            INSERT INTO team_memberships (user_id, team_id)
            VALUES ($1, $2)
            RETURNING *
            """,
            user_id,
            team_id,
        )
        assert row is not None, "INSERT RETURNING should always return a row"
        return TeamMembership(
            user_id=row["user_id"],
            team_id=row["team_id"],
            created_at=row["created_at"],
        )
