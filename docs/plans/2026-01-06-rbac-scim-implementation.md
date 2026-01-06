# RBAC + SCIM Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement resource-level ACLs for investigations with SCIM user/group provisioning that creates real users and teams.

**Architecture:** Flexible permission grants via tags, teams, datasource, or direct assignment. SCIM groups map to teams (or roles if prefixed `role-`). Permission evaluation uses Union (OR) logic - any matching grant allows access.

**Tech Stack:** Python/FastAPI, AsyncPG, SQLAlchemy models, pytest, React/TypeScript frontend

---

## Task 1: Database Migration for RBAC Tables

**Files:**
- Create: `backend/migrations/008_rbac_tables.sql`

**Step 1: Write the migration**

```sql
-- RBAC tables for teams, tags, and permission grants
-- Migration 008: RBAC

-- Teams (synced from SCIM Groups or created manually)
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    external_id VARCHAR(255),
    is_scim_managed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, name)
);

-- Team membership
CREATE TABLE team_members (
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id)
);

-- Resource tags
CREATE TABLE resource_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    color VARCHAR(7) DEFAULT '#6366f1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, name)
);

-- Tag assignments to investigations
CREATE TABLE investigation_tags (
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES resource_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (investigation_id, tag_id)
);

-- Permission grants (ACL table)
CREATE TABLE permission_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Who (one of these)
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,

    -- What (one of these)
    resource_type VARCHAR(50) NOT NULL DEFAULT 'investigation',
    resource_id UUID,
    tag_id UUID REFERENCES resource_tags(id) ON DELETE CASCADE,
    data_source_id UUID REFERENCES data_sources(id) ON DELETE CASCADE,

    -- Permission level
    permission VARCHAR(20) NOT NULL DEFAULT 'read',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    -- Ensure exactly one grantee
    CONSTRAINT one_grantee CHECK (
        (user_id IS NOT NULL AND team_id IS NULL) OR
        (user_id IS NULL AND team_id IS NOT NULL)
    ),
    -- Ensure exactly one access target
    CONSTRAINT one_target CHECK (
        (resource_id IS NOT NULL)::int +
        (tag_id IS NOT NULL)::int +
        (data_source_id IS NOT NULL)::int = 1
    )
);

-- SCIM role groups tracking (for role-* groups)
CREATE TABLE scim_role_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_id VARCHAR(255) NOT NULL,
    role_name VARCHAR(20) NOT NULL CHECK (role_name IN ('owner', 'admin', 'member')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, external_id)
);

-- Indexes
CREATE INDEX idx_teams_org ON teams(org_id);
CREATE INDEX idx_teams_external ON teams(external_id) WHERE external_id IS NOT NULL;
CREATE INDEX idx_team_members_user ON team_members(user_id);
CREATE INDEX idx_team_members_team ON team_members(team_id);
CREATE INDEX idx_resource_tags_org ON resource_tags(org_id);
CREATE INDEX idx_investigation_tags_inv ON investigation_tags(investigation_id);
CREATE INDEX idx_investigation_tags_tag ON investigation_tags(tag_id);
CREATE INDEX idx_permission_grants_org ON permission_grants(org_id);
CREATE INDEX idx_permission_grants_user ON permission_grants(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX idx_permission_grants_team ON permission_grants(team_id) WHERE team_id IS NOT NULL;
CREATE INDEX idx_permission_grants_resource ON permission_grants(resource_type, resource_id) WHERE resource_id IS NOT NULL;
CREATE INDEX idx_permission_grants_tag ON permission_grants(tag_id) WHERE tag_id IS NOT NULL;
CREATE INDEX idx_permission_grants_datasource ON permission_grants(data_source_id) WHERE data_source_id IS NOT NULL;

-- Triggers for updated_at
CREATE TRIGGER update_teams_updated_at BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

**Step 2: Verify migration syntax**

Run: `cat backend/migrations/008_rbac_tables.sql | head -20`
Expected: Shows migration header and first table

**Step 3: Commit**

```bash
git add backend/migrations/008_rbac_tables.sql
git commit -m "feat: add RBAC database tables (teams, tags, permissions)"
```

---

## Task 2: Core Domain Types for RBAC

**Files:**
- Create: `backend/src/dataing/core/rbac/__init__.py`
- Create: `backend/src/dataing/core/rbac/types.py`
- Test: `backend/tests/unit/core/rbac/test_types.py`

**Step 1: Create the types module**

```python
# backend/src/dataing/core/rbac/types.py
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
```

**Step 2: Create the __init__.py**

```python
# backend/src/dataing/core/rbac/__init__.py
"""RBAC core domain."""

from dataing.core.rbac.types import (
    AccessType,
    GranteeType,
    Permission,
    PermissionGrant,
    ResourceTag,
    Role,
    Team,
    TeamMember,
)

__all__ = [
    "AccessType",
    "GranteeType",
    "Permission",
    "PermissionGrant",
    "ResourceTag",
    "Role",
    "Team",
    "TeamMember",
]
```

**Step 3: Write tests**

```python
# backend/tests/unit/core/rbac/test_types.py
"""Tests for RBAC types."""

from uuid import uuid4
from datetime import datetime, UTC

import pytest
from dataing.core.rbac import (
    Role,
    Permission,
    GranteeType,
    AccessType,
    Team,
    ResourceTag,
    PermissionGrant,
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
```

**Step 4: Create test __init__.py**

```bash
mkdir -p backend/tests/unit/core/rbac
touch backend/tests/unit/core/rbac/__init__.py
```

**Step 5: Run tests**

Run: `cd backend && PYTHONPATH=src uv run pytest tests/unit/core/rbac/test_types.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/src/dataing/core/rbac/ backend/tests/unit/core/rbac/
git commit -m "feat: add RBAC core domain types"
```

---

## Task 3: Permission Service (Evaluation Logic)

**Files:**
- Create: `backend/src/dataing/core/rbac/permission_service.py`
- Modify: `backend/src/dataing/core/rbac/__init__.py`
- Test: `backend/tests/unit/core/rbac/test_permission_service.py`

**Step 1: Create permission service**

```python
# backend/src/dataing/core/rbac/permission_service.py
"""Permission evaluation service."""

import logging
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from dataing.core.rbac.types import Permission, Role

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class PermissionChecker(Protocol):
    """Protocol for permission checking."""

    async def can_access_investigation(
        self, user_id: UUID, investigation_id: UUID
    ) -> bool:
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

    async def can_access_investigation(
        self, user_id: UUID, investigation_id: UUID
    ) -> bool:
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
                SELECT 1 FROM users u
                JOIN investigations i ON i.tenant_id = u.tenant_id
                WHERE u.id = $1 AND i.id = $2 AND u.role IN ('owner', 'admin')

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
            "SELECT role FROM users WHERE id = $1 AND tenant_id = $2",
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
                            SELECT tag_id FROM investigation_tags WHERE investigation_id = i.id
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
            "SELECT role FROM users WHERE id = $1 AND tenant_id = $2",
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
```

**Step 2: Update __init__.py**

```python
# backend/src/dataing/core/rbac/__init__.py
"""RBAC core domain."""

from dataing.core.rbac.permission_service import PermissionService
from dataing.core.rbac.types import (
    AccessType,
    GranteeType,
    Permission,
    PermissionGrant,
    ResourceTag,
    Role,
    Team,
    TeamMember,
)

__all__ = [
    "AccessType",
    "GranteeType",
    "Permission",
    "PermissionGrant",
    "PermissionService",
    "ResourceTag",
    "Role",
    "Team",
    "TeamMember",
]
```

**Step 3: Write tests**

```python
# backend/tests/unit/core/rbac/test_permission_service.py
"""Tests for permission service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.core.rbac import PermissionService, Role


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def service(mock_conn: MagicMock) -> PermissionService:
    """Create permission service with mock connection."""
    return PermissionService(mock_conn)


class TestCanAccessInvestigation:
    """Tests for can_access_investigation method."""

    async def test_returns_true_when_has_access(
        self, service: PermissionService, mock_conn: MagicMock
    ) -> None:
        """Returns True when user has access."""
        mock_conn.fetchval = AsyncMock(return_value=True)

        result = await service.can_access_investigation(uuid4(), uuid4())

        assert result is True

    async def test_returns_false_when_no_access(
        self, service: PermissionService, mock_conn: MagicMock
    ) -> None:
        """Returns False when user has no access."""
        mock_conn.fetchval = AsyncMock(return_value=False)

        result = await service.can_access_investigation(uuid4(), uuid4())

        assert result is False


class TestGetAccessibleInvestigationIds:
    """Tests for get_accessible_investigation_ids method."""

    async def test_returns_none_for_admin(
        self, service: PermissionService, mock_conn: MagicMock
    ) -> None:
        """Returns None for admin (can see all)."""
        mock_conn.fetchval = AsyncMock(return_value="admin")

        result = await service.get_accessible_investigation_ids(uuid4(), uuid4())

        assert result is None

    async def test_returns_none_for_owner(
        self, service: PermissionService, mock_conn: MagicMock
    ) -> None:
        """Returns None for owner (can see all)."""
        mock_conn.fetchval = AsyncMock(return_value="owner")

        result = await service.get_accessible_investigation_ids(uuid4(), uuid4())

        assert result is None

    async def test_returns_ids_for_member(
        self, service: PermissionService, mock_conn: MagicMock
    ) -> None:
        """Returns list of IDs for member."""
        inv_id = uuid4()
        mock_conn.fetchval = AsyncMock(return_value="member")
        mock_conn.fetch = AsyncMock(return_value=[{"id": inv_id}])

        result = await service.get_accessible_investigation_ids(uuid4(), uuid4())

        assert result == [inv_id]


class TestIsAdminOrOwner:
    """Tests for is_admin_or_owner method."""

    async def test_returns_true_for_admin(
        self, service: PermissionService, mock_conn: MagicMock
    ) -> None:
        """Returns True for admin."""
        mock_conn.fetchval = AsyncMock(return_value="admin")

        result = await service.is_admin_or_owner(uuid4(), uuid4())

        assert result is True

    async def test_returns_true_for_owner(
        self, service: PermissionService, mock_conn: MagicMock
    ) -> None:
        """Returns True for owner."""
        mock_conn.fetchval = AsyncMock(return_value="owner")

        result = await service.is_admin_or_owner(uuid4(), uuid4())

        assert result is True

    async def test_returns_false_for_member(
        self, service: PermissionService, mock_conn: MagicMock
    ) -> None:
        """Returns False for member."""
        mock_conn.fetchval = AsyncMock(return_value="member")

        result = await service.is_admin_or_owner(uuid4(), uuid4())

        assert result is False
```

**Step 4: Run tests**

Run: `cd backend && PYTHONPATH=src uv run pytest tests/unit/core/rbac/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/src/dataing/core/rbac/
git add backend/tests/unit/core/rbac/
git commit -m "feat: add permission evaluation service"
```

---

## Task 4: Teams Repository

**Files:**
- Create: `backend/src/dataing/adapters/rbac/__init__.py`
- Create: `backend/src/dataing/adapters/rbac/teams_repository.py`
- Test: `backend/tests/unit/adapters/rbac/test_teams_repository.py`

**Step 1: Create teams repository**

```python
# backend/src/dataing/adapters/rbac/teams_repository.py
"""Teams repository."""

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.rbac import Team, TeamMember

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
```

**Step 2: Create __init__.py**

```python
# backend/src/dataing/adapters/rbac/__init__.py
"""RBAC adapters."""

from dataing.adapters.rbac.teams_repository import TeamsRepository

__all__ = [
    "TeamsRepository",
]
```

**Step 3: Write tests**

```python
# backend/tests/unit/adapters/rbac/test_teams_repository.py
"""Tests for teams repository."""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.rbac import TeamsRepository
from dataing.core.rbac import Team


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def repository(mock_conn: MagicMock) -> TeamsRepository:
    """Create repository with mock connection."""
    return TeamsRepository(mock_conn)


class TestCreate:
    """Tests for create method."""

    async def test_creates_team(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Creates a new team."""
        org_id = uuid4()
        team_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": team_id,
                "org_id": org_id,
                "name": "Engineering",
                "external_id": None,
                "is_scim_managed": False,
                "created_at": now,
                "updated_at": now,
            }
        )

        team = await repository.create(org_id, "Engineering")

        assert team.id == team_id
        assert team.name == "Engineering"
        assert team.is_scim_managed is False


class TestGetById:
    """Tests for get_by_id method."""

    async def test_returns_team(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns team when found."""
        team_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": team_id,
                "org_id": uuid4(),
                "name": "Engineering",
                "external_id": None,
                "is_scim_managed": False,
                "created_at": now,
                "updated_at": now,
            }
        )

        team = await repository.get_by_id(team_id)

        assert team is not None
        assert team.id == team_id

    async def test_returns_none_when_not_found(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when team not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        team = await repository.get_by_id(uuid4())

        assert team is None


class TestAddMember:
    """Tests for add_member method."""

    async def test_adds_member(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Adds member to team."""
        mock_conn.execute = AsyncMock()

        result = await repository.add_member(uuid4(), uuid4())

        assert result is True


class TestRemoveMember:
    """Tests for remove_member method."""

    async def test_removes_member(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Removes member from team."""
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        result = await repository.remove_member(uuid4(), uuid4())

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when member not in team."""
        mock_conn.execute = AsyncMock(return_value="DELETE 0")

        result = await repository.remove_member(uuid4(), uuid4())

        assert result is False
```

**Step 4: Create test directory**

```bash
mkdir -p backend/tests/unit/adapters/rbac
touch backend/tests/unit/adapters/rbac/__init__.py
```

**Step 5: Run tests**

Run: `cd backend && PYTHONPATH=src uv run pytest tests/unit/adapters/rbac/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/src/dataing/adapters/rbac/
git add backend/tests/unit/adapters/rbac/
git commit -m "feat: add teams repository"
```

---

## Task 5: Tags Repository

**Files:**
- Create: `backend/src/dataing/adapters/rbac/tags_repository.py`
- Modify: `backend/src/dataing/adapters/rbac/__init__.py`
- Test: `backend/tests/unit/adapters/rbac/test_tags_repository.py`

**Step 1: Create tags repository**

```python
# backend/src/dataing/adapters/rbac/tags_repository.py
"""Tags repository."""

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.rbac import ResourceTag

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class TagsRepository:
    """Repository for resource tag operations."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository."""
        self._conn = conn

    async def create(
        self, org_id: UUID, name: str, color: str = "#6366f1"
    ) -> ResourceTag:
        """Create a new tag."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO resource_tags (org_id, name, color)
            VALUES ($1, $2, $3)
            RETURNING id, org_id, name, color, created_at
            """,
            org_id,
            name,
            color,
        )
        return self._row_to_tag(row)

    async def get_by_id(self, tag_id: UUID) -> ResourceTag | None:
        """Get tag by ID."""
        row = await self._conn.fetchrow(
            "SELECT id, org_id, name, color, created_at FROM resource_tags WHERE id = $1",
            tag_id,
        )
        if not row:
            return None
        return self._row_to_tag(row)

    async def get_by_name(self, org_id: UUID, name: str) -> ResourceTag | None:
        """Get tag by name."""
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, name, color, created_at
            FROM resource_tags WHERE org_id = $1 AND name = $2
            """,
            org_id,
            name,
        )
        if not row:
            return None
        return self._row_to_tag(row)

    async def list_by_org(self, org_id: UUID) -> list[ResourceTag]:
        """List all tags in an organization."""
        rows = await self._conn.fetch(
            """
            SELECT id, org_id, name, color, created_at
            FROM resource_tags WHERE org_id = $1 ORDER BY name
            """,
            org_id,
        )
        return [self._row_to_tag(row) for row in rows]

    async def update(
        self, tag_id: UUID, name: str | None = None, color: str | None = None
    ) -> ResourceTag | None:
        """Update tag."""
        # Build dynamic update
        updates = []
        params: list[Any] = [tag_id]
        idx = 2

        if name is not None:
            updates.append(f"name = ${idx}")
            params.append(name)
            idx += 1

        if color is not None:
            updates.append(f"color = ${idx}")
            params.append(color)
            idx += 1

        if not updates:
            return await self.get_by_id(tag_id)

        query = f"""
            UPDATE resource_tags SET {', '.join(updates)}
            WHERE id = $1
            RETURNING id, org_id, name, color, created_at
        """

        row = await self._conn.fetchrow(query, *params)
        if not row:
            return None
        return self._row_to_tag(row)

    async def delete(self, tag_id: UUID) -> bool:
        """Delete a tag."""
        result: str = await self._conn.execute(
            "DELETE FROM resource_tags WHERE id = $1",
            tag_id,
        )
        return result == "DELETE 1"

    async def add_to_investigation(
        self, investigation_id: UUID, tag_id: UUID
    ) -> bool:
        """Add tag to an investigation."""
        try:
            await self._conn.execute(
                """
                INSERT INTO investigation_tags (investigation_id, tag_id)
                VALUES ($1, $2)
                ON CONFLICT (investigation_id, tag_id) DO NOTHING
                """,
                investigation_id,
                tag_id,
            )
            return True
        except Exception:
            logger.exception(f"Failed to add tag {tag_id} to investigation {investigation_id}")
            return False

    async def remove_from_investigation(
        self, investigation_id: UUID, tag_id: UUID
    ) -> bool:
        """Remove tag from an investigation."""
        result: str = await self._conn.execute(
            "DELETE FROM investigation_tags WHERE investigation_id = $1 AND tag_id = $2",
            investigation_id,
            tag_id,
        )
        return result == "DELETE 1"

    async def get_investigation_tags(self, investigation_id: UUID) -> list[ResourceTag]:
        """Get all tags on an investigation."""
        rows = await self._conn.fetch(
            """
            SELECT t.id, t.org_id, t.name, t.color, t.created_at
            FROM resource_tags t
            JOIN investigation_tags it ON t.id = it.tag_id
            WHERE it.investigation_id = $1
            ORDER BY t.name
            """,
            investigation_id,
        )
        return [self._row_to_tag(row) for row in rows]

    def _row_to_tag(self, row: dict[str, Any]) -> ResourceTag:
        """Convert database row to ResourceTag."""
        return ResourceTag(
            id=row["id"],
            org_id=row["org_id"],
            name=row["name"],
            color=row["color"],
            created_at=row["created_at"].replace(tzinfo=UTC),
        )
```

**Step 2: Update __init__.py**

```python
# backend/src/dataing/adapters/rbac/__init__.py
"""RBAC adapters."""

from dataing.adapters.rbac.tags_repository import TagsRepository
from dataing.adapters.rbac.teams_repository import TeamsRepository

__all__ = [
    "TagsRepository",
    "TeamsRepository",
]
```

**Step 3: Write tests**

```python
# backend/tests/unit/adapters/rbac/test_tags_repository.py
"""Tests for tags repository."""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.rbac import TagsRepository


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def repository(mock_conn: MagicMock) -> TagsRepository:
    """Create repository with mock connection."""
    return TagsRepository(mock_conn)


class TestCreate:
    """Tests for create method."""

    async def test_creates_tag(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Creates a new tag."""
        org_id = uuid4()
        tag_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": tag_id,
                "org_id": org_id,
                "name": "finance",
                "color": "#6366f1",
                "created_at": now,
            }
        )

        tag = await repository.create(org_id, "finance")

        assert tag.id == tag_id
        assert tag.name == "finance"


class TestAddToInvestigation:
    """Tests for add_to_investigation method."""

    async def test_adds_tag(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Adds tag to investigation."""
        mock_conn.execute = AsyncMock()

        result = await repository.add_to_investigation(uuid4(), uuid4())

        assert result is True


class TestGetInvestigationTags:
    """Tests for get_investigation_tags method."""

    async def test_returns_tags(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns tags on investigation."""
        tag_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": tag_id,
                    "org_id": uuid4(),
                    "name": "finance",
                    "color": "#6366f1",
                    "created_at": now,
                }
            ]
        )

        tags = await repository.get_investigation_tags(uuid4())

        assert len(tags) == 1
        assert tags[0].name == "finance"
```

**Step 4: Run tests**

Run: `cd backend && PYTHONPATH=src uv run pytest tests/unit/adapters/rbac/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/src/dataing/adapters/rbac/
git add backend/tests/unit/adapters/rbac/
git commit -m "feat: add tags repository"
```

---

## Task 6: Permissions Repository

**Files:**
- Create: `backend/src/dataing/adapters/rbac/permissions_repository.py`
- Modify: `backend/src/dataing/adapters/rbac/__init__.py`
- Test: `backend/tests/unit/adapters/rbac/test_permissions_repository.py`

**Step 1: Create permissions repository**

```python
# backend/src/dataing/adapters/rbac/permissions_repository.py
"""Permissions repository."""

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.rbac import Permission, PermissionGrant

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class PermissionsRepository:
    """Repository for permission grant operations."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository."""
        self._conn = conn

    async def create_user_resource_grant(
        self,
        org_id: UUID,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a direct user → resource grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, user_id, resource_type, resource_id, permission, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            org_id,
            user_id,
            resource_type,
            resource_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def create_user_tag_grant(
        self,
        org_id: UUID,
        user_id: UUID,
        tag_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a user → tag grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, user_id, resource_type, tag_id, permission, created_by)
            VALUES ($1, $2, 'investigation', $3, $4, $5)
            RETURNING *
            """,
            org_id,
            user_id,
            tag_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def create_user_datasource_grant(
        self,
        org_id: UUID,
        user_id: UUID,
        data_source_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a user → datasource grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, user_id, resource_type, data_source_id, permission, created_by)
            VALUES ($1, $2, 'investigation', $3, $4, $5)
            RETURNING *
            """,
            org_id,
            user_id,
            data_source_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def create_team_resource_grant(
        self,
        org_id: UUID,
        team_id: UUID,
        resource_type: str,
        resource_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a team → resource grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, team_id, resource_type, resource_id, permission, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            org_id,
            team_id,
            resource_type,
            resource_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def create_team_tag_grant(
        self,
        org_id: UUID,
        team_id: UUID,
        tag_id: UUID,
        permission: Permission,
        created_by: UUID | None = None,
    ) -> PermissionGrant:
        """Create a team → tag grant."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO permission_grants
                (org_id, team_id, resource_type, tag_id, permission, created_by)
            VALUES ($1, $2, 'investigation', $3, $4, $5)
            RETURNING *
            """,
            org_id,
            team_id,
            tag_id,
            permission.value,
            created_by,
        )
        return self._row_to_grant(row)

    async def delete(self, grant_id: UUID) -> bool:
        """Delete a permission grant."""
        result: str = await self._conn.execute(
            "DELETE FROM permission_grants WHERE id = $1",
            grant_id,
        )
        return result == "DELETE 1"

    async def list_by_org(self, org_id: UUID) -> list[PermissionGrant]:
        """List all grants in an organization."""
        rows = await self._conn.fetch(
            "SELECT * FROM permission_grants WHERE org_id = $1 ORDER BY created_at DESC",
            org_id,
        )
        return [self._row_to_grant(row) for row in rows]

    async def list_by_user(self, user_id: UUID) -> list[PermissionGrant]:
        """List all grants for a user."""
        rows = await self._conn.fetch(
            "SELECT * FROM permission_grants WHERE user_id = $1",
            user_id,
        )
        return [self._row_to_grant(row) for row in rows]

    async def list_by_resource(
        self, resource_type: str, resource_id: UUID
    ) -> list[PermissionGrant]:
        """List all grants for a resource."""
        rows = await self._conn.fetch(
            """
            SELECT * FROM permission_grants
            WHERE resource_type = $1 AND resource_id = $2
            """,
            resource_type,
            resource_id,
        )
        return [self._row_to_grant(row) for row in rows]

    def _row_to_grant(self, row: dict[str, Any]) -> PermissionGrant:
        """Convert database row to PermissionGrant."""
        return PermissionGrant(
            id=row["id"],
            org_id=row["org_id"],
            user_id=row["user_id"],
            team_id=row["team_id"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            tag_id=row["tag_id"],
            data_source_id=row["data_source_id"],
            permission=Permission(row["permission"]),
            created_at=row["created_at"].replace(tzinfo=UTC),
            created_by=row["created_by"],
        )
```

**Step 2: Update __init__.py**

```python
# backend/src/dataing/adapters/rbac/__init__.py
"""RBAC adapters."""

from dataing.adapters.rbac.permissions_repository import PermissionsRepository
from dataing.adapters.rbac.tags_repository import TagsRepository
from dataing.adapters.rbac.teams_repository import TeamsRepository

__all__ = [
    "PermissionsRepository",
    "TagsRepository",
    "TeamsRepository",
]
```

**Step 3: Write tests**

```python
# backend/tests/unit/adapters/rbac/test_permissions_repository.py
"""Tests for permissions repository."""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.rbac import PermissionsRepository
from dataing.core.rbac import Permission


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def repository(mock_conn: MagicMock) -> PermissionsRepository:
    """Create repository with mock connection."""
    return PermissionsRepository(mock_conn)


def make_grant_row(
    user_id: uuid4 | None = None,
    team_id: uuid4 | None = None,
    resource_id: uuid4 | None = None,
    tag_id: uuid4 | None = None,
    data_source_id: uuid4 | None = None,
) -> dict:
    """Create a mock grant row."""
    return {
        "id": uuid4(),
        "org_id": uuid4(),
        "user_id": user_id,
        "team_id": team_id,
        "resource_type": "investigation",
        "resource_id": resource_id,
        "tag_id": tag_id,
        "data_source_id": data_source_id,
        "permission": "read",
        "created_at": datetime.now(UTC),
        "created_by": None,
    }


class TestCreateUserResourceGrant:
    """Tests for create_user_resource_grant method."""

    async def test_creates_grant(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Creates a user → resource grant."""
        user_id = uuid4()
        resource_id = uuid4()

        mock_conn.fetchrow = AsyncMock(
            return_value=make_grant_row(user_id=user_id, resource_id=resource_id)
        )

        grant = await repository.create_user_resource_grant(
            org_id=uuid4(),
            user_id=user_id,
            resource_type="investigation",
            resource_id=resource_id,
            permission=Permission.READ,
        )

        assert grant.user_id == user_id
        assert grant.resource_id == resource_id


class TestDelete:
    """Tests for delete method."""

    async def test_deletes_grant(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Deletes a grant."""
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        result = await repository.delete(uuid4())

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when grant not found."""
        mock_conn.execute = AsyncMock(return_value="DELETE 0")

        result = await repository.delete(uuid4())

        assert result is False
```

**Step 4: Run tests**

Run: `cd backend && PYTHONPATH=src uv run pytest tests/unit/adapters/rbac/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/src/dataing/adapters/rbac/
git add backend/tests/unit/adapters/rbac/
git commit -m "feat: add permissions repository"
```

---

## Task 7: Wire SCIM to Create Real Users

**Files:**
- Create: `backend/src/dataing/adapters/sso/user_repository.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/scim.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_scim.py` (extend)

**Step 1: Create user repository for SCIM**

```python
# backend/src/dataing/adapters/sso/user_repository.py
"""User repository for SCIM operations."""

import logging
from datetime import UTC
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
        """Create a new user via SCIM."""
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

    async def get_user_by_id(self, user_id: UUID) -> dict[str, Any] | None:
        """Get user by ID."""
        row = await self._conn.fetchrow(
            """
            SELECT id, tenant_id, email, name, role, is_active, created_at, updated_at
            FROM users WHERE id = $1
            """,
            user_id,
        )
        if not row:
            return None
        return dict(row)

    async def get_user_by_email(
        self, org_id: UUID, email: str
    ) -> dict[str, Any] | None:
        """Get user by email in an org."""
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
        """Get user by external ID (from IdP)."""
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
        user_id: UUID,
        email: str | None = None,
        name: str | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any] | None:
        """Update a user."""
        updates = []
        params: list[Any] = [user_id]
        idx = 2

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
            return await self.get_user_by_id(user_id)

        updates.append("updated_at = NOW()")

        query = f"""
            UPDATE users SET {', '.join(updates)}
            WHERE id = $1
            RETURNING id, tenant_id, email, name, role, is_active, created_at, updated_at
        """

        row = await self._conn.fetchrow(query, *params)
        if not row:
            return None
        return dict(row)

    async def deactivate_user(self, user_id: UUID) -> bool:
        """Deactivate a user (soft delete)."""
        result: str = await self._conn.execute(
            "UPDATE users SET is_active = false, updated_at = NOW() WHERE id = $1",
            user_id,
        )
        return result == "UPDATE 1"

    async def list_users(
        self,
        org_id: UUID,
        start_index: int = 1,
        count: int = 100,
        filter_email: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List users with pagination and optional filter."""
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

        return [dict(row) for row in rows], total

    async def update_user_role(self, user_id: UUID, role: str) -> bool:
        """Update user's role."""
        result: str = await self._conn.execute(
            "UPDATE users SET role = $2, updated_at = NOW() WHERE id = $1",
            user_id,
            role,
        )
        return result == "UPDATE 1"
```

**Step 2: Update SCIM routes to use real repository**

This is a larger change - update `backend/src/dataing/entrypoints/api/routes/scim.py` to inject and use the repository. See full implementation in the codebase after this task.

**Step 3: Run tests**

Run: `cd backend && PYTHONPATH=src uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/src/dataing/adapters/sso/user_repository.py
git add backend/src/dataing/entrypoints/api/routes/scim.py
git commit -m "feat: wire SCIM endpoints to create real users"
```

---

## Task 8: Wire SCIM Groups to Create Teams

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/scim.py`
- Modify: `backend/src/dataing/adapters/rbac/teams_repository.py`

**Step 1: Update SCIM routes for Groups**

Add logic to create teams for non-role groups, and update user roles for role-* groups.

**Step 2: Run tests**

Run: `cd backend && PYTHONPATH=src uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/scim.py
git commit -m "feat: wire SCIM groups to create teams and assign roles"
```

---

## Task 9: API Routes for Teams, Tags, Permissions

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/teams.py`
- Create: `backend/src/dataing/entrypoints/api/routes/tags.py`
- Create: `backend/src/dataing/entrypoints/api/routes/permissions.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/__init__.py`

These routes follow the same pattern as existing routes. See implementation after this task.

**Step 1: Create routes**
**Step 2: Run tests**
**Step 3: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/teams.py
git add backend/src/dataing/entrypoints/api/routes/tags.py
git add backend/src/dataing/entrypoints/api/routes/permissions.py
git commit -m "feat: add API routes for teams, tags, and permissions"
```

---

## Task 10: Add Permission Filtering to Investigation Routes

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/investigations.py`

**Step 1: Update investigation list to filter by permissions**
**Step 2: Update investigation detail to check access**
**Step 3: Run tests**
**Step 4: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/investigations.py
git commit -m "feat: add permission filtering to investigation endpoints"
```

---

## Task 11: Frontend - Teams Settings Page

**Files:**
- Create: `frontend/src/features/settings/teams/teams-settings-page.tsx`
- Create: `frontend/src/features/settings/teams/index.ts`

**Step 1: Create teams settings component**
**Step 2: Run lint**
**Step 3: Commit**

```bash
git add frontend/src/features/settings/teams/
git commit -m "feat: add teams settings page"
```

---

## Task 12: Frontend - Tags Settings Page

**Files:**
- Create: `frontend/src/features/settings/tags/tags-settings-page.tsx`
- Create: `frontend/src/features/settings/tags/index.ts`

**Step 1: Create tags settings component**
**Step 2: Run lint**
**Step 3: Commit**

```bash
git add frontend/src/features/settings/tags/
git commit -m "feat: add tags settings page"
```

---

## Task 13: Frontend - Permissions Settings Page

**Files:**
- Create: `frontend/src/features/settings/permissions/permissions-settings-page.tsx`
- Create: `frontend/src/features/settings/permissions/index.ts`

**Step 1: Create permissions settings component**
**Step 2: Run lint**
**Step 3: Commit**

```bash
git add frontend/src/features/settings/permissions/
git commit -m "feat: add permissions settings page"
```

---

## Task 14: Frontend - Investigation Sharing UI

**Files:**
- Modify: `frontend/src/features/investigation/InvestigationDetail.tsx`
- Create: `frontend/src/features/investigation/components/share-dialog.tsx`
- Create: `frontend/src/features/investigation/components/tags-section.tsx`

**Step 1: Add tags section to investigation detail**
**Step 2: Add share dialog**
**Step 3: Run lint**
**Step 4: Commit**

```bash
git add frontend/src/features/investigation/
git commit -m "feat: add investigation sharing and tags UI"
```

---

## Task 15: Frontend - Update Routing and Sidebar

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/app-sidebar.tsx`

**Step 1: Add routes for new settings pages**
**Step 2: Add sidebar links**
**Step 3: Run lint**
**Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/app-sidebar.tsx
git commit -m "feat: add RBAC routes and sidebar links"
```

---

## Task 16: Final Verification

**Step 1: Run all backend tests**

Run: `cd backend && PYTHONPATH=src uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 2: Run frontend lint**

Run: `cd frontend && pnpm exec eslint src/`
Expected: No errors

**Step 3: Verify git status is clean**

Run: `git status`
Expected: Working tree clean

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Database migration for RBAC tables |
| 2 | Core domain types (Team, Tag, PermissionGrant) |
| 3 | Permission evaluation service |
| 4 | Teams repository |
| 5 | Tags repository |
| 6 | Permissions repository |
| 7 | Wire SCIM Users to create real users |
| 8 | Wire SCIM Groups to create teams/roles |
| 9 | API routes for teams, tags, permissions |
| 10 | Permission filtering on investigation routes |
| 11 | Frontend: Teams settings page |
| 12 | Frontend: Tags settings page |
| 13 | Frontend: Permissions settings page |
| 14 | Frontend: Investigation sharing UI |
| 15 | Frontend: Update routing and sidebar |
| 16 | Final verification |
