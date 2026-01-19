"""Tests for RBAC types."""

from datetime import UTC, datetime
from uuid import uuid4

from dataing.core.rbac import (
    AccessType,
    GranteeType,
    Permission,
    PermissionGrant,
    Role,
    Team,
)


class TestRole:
    """Tests for Role enum."""

    def test_role_values(self) -> None:
        """Role has expected values."""
        assert Role.OWNER.value == "owner"
        assert Role.ADMIN.value == "admin"
        assert Role.MEMBER.value == "member"


class TestPermission:
    """Tests for Permission enum."""

    def test_permission_values(self) -> None:
        """Permission has expected values."""
        assert Permission.READ.value == "read"
        assert Permission.WRITE.value == "write"
        assert Permission.ADMIN.value == "admin"


class TestTeam:
    """Tests for Team dataclass."""

    def test_create_team(self) -> None:
        """Can create a team."""
        team = Team(
            id=uuid4(),
            org_id=uuid4(),
            name="Engineering",
            external_id="okta-eng-123",
            is_scim_managed=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert team.name == "Engineering"
        assert team.is_scim_managed is True


class TestPermissionGrant:
    """Tests for PermissionGrant dataclass."""

    def test_grantee_type_user(self) -> None:
        """Grantee type is USER when user_id is set."""
        grant = PermissionGrant(
            id=uuid4(),
            org_id=uuid4(),
            user_id=uuid4(),
            team_id=None,
            resource_type="investigation",
            resource_id=uuid4(),
            tag_id=None,
            data_source_id=None,
            permission=Permission.READ,
            created_at=datetime.now(UTC),
            created_by=None,
        )
        assert grant.grantee_type == GranteeType.USER

    def test_grantee_type_team(self) -> None:
        """Grantee type is TEAM when team_id is set."""
        grant = PermissionGrant(
            id=uuid4(),
            org_id=uuid4(),
            user_id=None,
            team_id=uuid4(),
            resource_type="investigation",
            resource_id=uuid4(),
            tag_id=None,
            data_source_id=None,
            permission=Permission.READ,
            created_at=datetime.now(UTC),
            created_by=None,
        )
        assert grant.grantee_type == GranteeType.TEAM

    def test_access_type_resource(self) -> None:
        """Access type is RESOURCE when resource_id is set."""
        grant = PermissionGrant(
            id=uuid4(),
            org_id=uuid4(),
            user_id=uuid4(),
            team_id=None,
            resource_type="investigation",
            resource_id=uuid4(),
            tag_id=None,
            data_source_id=None,
            permission=Permission.READ,
            created_at=datetime.now(UTC),
            created_by=None,
        )
        assert grant.access_type == AccessType.RESOURCE

    def test_access_type_tag(self) -> None:
        """Access type is TAG when tag_id is set."""
        grant = PermissionGrant(
            id=uuid4(),
            org_id=uuid4(),
            user_id=uuid4(),
            team_id=None,
            resource_type="investigation",
            resource_id=None,
            tag_id=uuid4(),
            data_source_id=None,
            permission=Permission.READ,
            created_at=datetime.now(UTC),
            created_by=None,
        )
        assert grant.access_type == AccessType.TAG

    def test_access_type_datasource(self) -> None:
        """Access type is DATASOURCE when data_source_id is set."""
        grant = PermissionGrant(
            id=uuid4(),
            org_id=uuid4(),
            user_id=uuid4(),
            team_id=None,
            resource_type="investigation",
            resource_id=None,
            tag_id=None,
            data_source_id=uuid4(),
            permission=Permission.READ,
            created_at=datetime.now(UTC),
            created_by=None,
        )
        assert grant.access_type == AccessType.DATASOURCE
