"""RBAC domain types."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class Role(str, Enum):
    """User roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Permission(str, Enum):
    """Permission levels."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class GranteeType(str, Enum):
    """Type of permission grantee."""

    USER = "user"
    TEAM = "team"


class AccessType(str, Enum):
    """Type of access target."""

    RESOURCE = "resource"
    TAG = "tag"
    DATASOURCE = "datasource"


@dataclass
class Team:
    """A team in an organization."""

    id: UUID
    org_id: UUID
    name: str
    external_id: str | None
    is_scim_managed: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class TeamMember:
    """A user's membership in a team."""

    team_id: UUID
    user_id: UUID
    added_at: datetime


@dataclass
class ResourceTag:
    """A tag that can be applied to resources."""

    id: UUID
    org_id: UUID
    name: str
    color: str
    created_at: datetime


@dataclass
class PermissionGrant:
    """A permission grant (ACL entry)."""

    id: UUID
    org_id: UUID
    # Grantee (one of these)
    user_id: UUID | None
    team_id: UUID | None
    # Target (one of these)
    resource_type: str
    resource_id: UUID | None
    tag_id: UUID | None
    data_source_id: UUID | None
    # Level
    permission: Permission
    created_at: datetime
    created_by: UUID | None

    @property
    def grantee_type(self) -> GranteeType:
        """Get the type of grantee."""
        return GranteeType.USER if self.user_id else GranteeType.TEAM

    @property
    def access_type(self) -> AccessType:
        """Get the type of access target."""
        if self.resource_id:
            return AccessType.RESOURCE
        if self.tag_id:
            return AccessType.TAG
        return AccessType.DATASOURCE
