"""Auth repository protocol for database operations."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from dataing.core.auth.types import (
    Organization,
    OrgMembership,
    OrgRole,
    Team,
    TeamMembership,
    User,
)


@runtime_checkable
class AuthRepository(Protocol):
    """Protocol for auth database operations.

    Implementations provide actual database access (PostgreSQL, etc).
    """

    # User operations
    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Get user by ID."""
        ...

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        ...

    async def create_user(
        self,
        email: str,
        name: str | None = None,
        password_hash: str | None = None,
    ) -> User:
        """Create a new user."""
        ...

    async def update_user(
        self,
        user_id: UUID,
        name: str | None = None,
        password_hash: str | None = None,
        is_active: bool | None = None,
    ) -> User | None:
        """Update user fields."""
        ...

    # Organization operations
    async def get_org_by_id(self, org_id: UUID) -> Organization | None:
        """Get organization by ID."""
        ...

    async def get_org_by_slug(self, slug: str) -> Organization | None:
        """Get organization by slug."""
        ...

    async def create_org(
        self,
        name: str,
        slug: str,
        plan: str = "free",
    ) -> Organization:
        """Create a new organization."""
        ...

    # Team operations
    async def get_team_by_id(self, team_id: UUID) -> Team | None:
        """Get team by ID."""
        ...

    async def get_org_teams(self, org_id: UUID) -> list[Team]:
        """Get all teams in an organization."""
        ...

    async def create_team(self, org_id: UUID, name: str) -> Team:
        """Create a new team in an organization."""
        ...

    # Membership operations
    async def get_user_org_membership(self, user_id: UUID, org_id: UUID) -> OrgMembership | None:
        """Get user's membership in an organization."""
        ...

    async def get_user_orgs(self, user_id: UUID) -> list[tuple[Organization, OrgRole]]:
        """Get all organizations a user belongs to with their roles."""
        ...

    async def add_user_to_org(
        self,
        user_id: UUID,
        org_id: UUID,
        role: OrgRole = OrgRole.MEMBER,
    ) -> OrgMembership:
        """Add user to organization with role."""
        ...

    async def get_user_teams(self, user_id: UUID, org_id: UUID) -> list[Team]:
        """Get teams user belongs to within an org."""
        ...

    async def add_user_to_team(self, user_id: UUID, team_id: UUID) -> TeamMembership:
        """Add user to a team."""
        ...
