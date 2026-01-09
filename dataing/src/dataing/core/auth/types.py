"""Auth domain types."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, EmailStr


class OrgRole(str, Enum):
    """Organization membership roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(BaseModel):
    """User domain model."""

    id: UUID
    email: EmailStr
    name: str | None = None
    password_hash: str | None = None  # None for SSO-only users
    is_active: bool = True
    created_at: datetime


class Organization(BaseModel):
    """Organization domain model."""

    id: UUID
    name: str
    slug: str
    plan: str = "free"
    created_at: datetime


class Team(BaseModel):
    """Team domain model."""

    id: UUID
    org_id: UUID
    name: str
    created_at: datetime


class OrgMembership(BaseModel):
    """User's membership in an organization."""

    user_id: UUID
    org_id: UUID
    role: OrgRole
    created_at: datetime


class TeamMembership(BaseModel):
    """User's membership in a team."""

    user_id: UUID
    team_id: UUID
    created_at: datetime


class TokenPayload(BaseModel):
    """JWT token payload claims."""

    sub: str  # user_id
    org_id: str
    role: str
    teams: list[str]
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
