"""Tests for auth domain types."""

from datetime import UTC, datetime
from uuid import uuid4

from dataing.core.auth.types import (
    Organization,
    OrgRole,
    Team,
    TokenPayload,
    User,
)


class TestUser:
    """Test User model."""

    def test_create_user(self) -> None:
        """Should create user with required fields."""
        user = User(
            id=uuid4(),
            email="test@example.com",
            name="Test User",
            is_active=True,
            created_at=datetime.now(UTC),
        )
        assert user.email == "test@example.com"
        assert user.password_hash is None

    def test_user_password_hash_optional(self) -> None:
        """Password hash should be optional for SSO users."""
        user = User(
            id=uuid4(),
            email="sso@example.com",
            name="SSO User",
            is_active=True,
            created_at=datetime.now(UTC),
        )
        assert user.password_hash is None


class TestOrganization:
    """Test Organization model."""

    def test_create_org(self) -> None:
        """Should create org with slug."""
        org = Organization(
            id=uuid4(),
            name="Acme Corp",
            slug="acme",
            plan="free",
            created_at=datetime.now(UTC),
        )
        assert org.slug == "acme"
        assert org.plan == "free"


class TestTeam:
    """Test Team model."""

    def test_create_team(self) -> None:
        """Should create team with org_id."""
        org_id = uuid4()
        team = Team(
            id=uuid4(),
            org_id=org_id,
            name="Data Team",
            created_at=datetime.now(UTC),
        )
        assert team.name == "Data Team"
        assert team.org_id == org_id


class TestOrgRole:
    """Test OrgRole enum."""

    def test_role_values(self) -> None:
        """Roles should have correct string values."""
        assert OrgRole.OWNER.value == "owner"
        assert OrgRole.ADMIN.value == "admin"
        assert OrgRole.MEMBER.value == "member"
        assert OrgRole.VIEWER.value == "viewer"


class TestTokenPayload:
    """Test TokenPayload for JWT."""

    def test_create_token_payload(self) -> None:
        """Should create token payload with required claims."""
        user_id = uuid4()
        org_id = uuid4()
        payload = TokenPayload(
            sub=str(user_id),
            org_id=str(org_id),
            role="admin",
            teams=["team-1", "team-2"],
            exp=1234567890,
            iat=1234567800,
        )
        assert payload.sub == str(user_id)
        assert payload.role == "admin"
        assert len(payload.teams) == 2
