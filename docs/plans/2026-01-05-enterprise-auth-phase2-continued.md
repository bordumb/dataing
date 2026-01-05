# Enterprise Auth Phase 2 (Continued) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the auth system with repository layer, auth endpoints, JWT middleware, RBAC, and frontend integration.

**Architecture:** Repository pattern for database access, FastAPI dependency injection for auth middleware, role-based access control using OrgRole enum, React context for frontend auth state with JWT token storage.

**Tech Stack:** FastAPI, PostgreSQL (asyncpg), PyJWT, bcrypt, React, TypeScript

---

## Task 11: Auth Repository Protocol

**Files:**
- Create: `backend/src/dataing/core/auth/repository.py`
- Test: `backend/tests/unit/core/auth/test_repository.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/core/auth/test_repository.py
"""Tests for auth repository protocol."""

import pytest
from typing import Protocol, runtime_checkable

from dataing.core.auth.repository import AuthRepository


class TestAuthRepositoryProtocol:
    """Test AuthRepository is a proper protocol."""

    def test_protocol_has_user_methods(self) -> None:
        """Protocol should define user CRUD methods."""
        assert hasattr(AuthRepository, "get_user_by_id")
        assert hasattr(AuthRepository, "get_user_by_email")
        assert hasattr(AuthRepository, "create_user")

    def test_protocol_has_org_methods(self) -> None:
        """Protocol should define org CRUD methods."""
        assert hasattr(AuthRepository, "get_org_by_id")
        assert hasattr(AuthRepository, "get_org_by_slug")
        assert hasattr(AuthRepository, "create_org")

    def test_protocol_has_membership_methods(self) -> None:
        """Protocol should define membership methods."""
        assert hasattr(AuthRepository, "get_user_org_membership")
        assert hasattr(AuthRepository, "get_user_orgs")
        assert hasattr(AuthRepository, "add_user_to_org")
```

**Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_repository.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/core/auth/repository.py
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
    async def get_user_org_membership(
        self, user_id: UUID, org_id: UUID
    ) -> OrgMembership | None:
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
```

**Step 4: Update `__init__.py`**

```python
# backend/src/dataing/core/auth/__init__.py
"""Auth domain types and utilities."""

from dataing.core.auth.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from dataing.core.auth.password import hash_password, verify_password
from dataing.core.auth.repository import AuthRepository
from dataing.core.auth.types import (
    Organization,
    OrgMembership,
    OrgRole,
    Team,
    TeamMembership,
    TokenPayload,
    User,
)

__all__ = [
    "User",
    "Organization",
    "Team",
    "OrgMembership",
    "TeamMembership",
    "OrgRole",
    "TokenPayload",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "TokenError",
    "AuthRepository",
]
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_repository.py -v
```

Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/core/auth
git commit -m "feat(auth): add AuthRepository protocol"
```

---

## Task 12: PostgreSQL Auth Repository Implementation

**Files:**
- Create: `backend/src/dataing/adapters/auth/__init__.py`
- Create: `backend/src/dataing/adapters/auth/postgres.py`
- Test: `backend/tests/unit/adapters/auth/test_postgres.py`

**Step 1: Create test directory**

```bash
mkdir -p backend/tests/unit/adapters/auth
touch backend/tests/unit/adapters/auth/__init__.py
```

**Step 2: Write the failing test**

```python
# backend/tests/unit/adapters/auth/test_postgres.py
"""Tests for PostgreSQL auth repository."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from uuid import uuid4

from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.core.auth import AuthRepository, User, Organization, OrgRole


class TestPostgresAuthRepository:
    """Test PostgresAuthRepository implementation."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def repo(self, mock_db: MagicMock) -> PostgresAuthRepository:
        """Create repository with mock database."""
        return PostgresAuthRepository(mock_db)

    def test_implements_protocol(self, repo: PostgresAuthRepository) -> None:
        """Repository should implement AuthRepository protocol."""
        assert isinstance(repo, AuthRepository)

    @pytest.mark.asyncio
    async def test_get_user_by_email(
        self, repo: PostgresAuthRepository, mock_db: MagicMock
    ) -> None:
        """Should return user when found by email."""
        user_id = uuid4()
        mock_db.fetch_one = AsyncMock(
            return_value={
                "id": user_id,
                "email": "test@example.com",
                "name": "Test User",
                "password_hash": "hashed",  # pragma: allowlist secret
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
            }
        )

        result = await repo.get_user_by_email("test@example.com")

        assert result is not None
        assert result.email == "test@example.com"
        assert result.id == user_id

    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(
        self, repo: PostgresAuthRepository, mock_db: MagicMock
    ) -> None:
        """Should return None when user not found."""
        mock_db.fetch_one = AsyncMock(return_value=None)

        result = await repo.get_user_by_email("notfound@example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_create_user(
        self, repo: PostgresAuthRepository, mock_db: MagicMock
    ) -> None:
        """Should create user and return it."""
        user_id = uuid4()
        created_at = datetime.now(timezone.utc)
        mock_db.fetch_one = AsyncMock(
            return_value={
                "id": user_id,
                "email": "new@example.com",
                "name": "New User",
                "password_hash": "hashed",  # pragma: allowlist secret
                "is_active": True,
                "created_at": created_at,
            }
        )

        result = await repo.create_user(
            email="new@example.com",
            name="New User",
            password_hash="hashed",  # pragma: allowlist secret
        )

        assert result.email == "new@example.com"
        assert result.name == "New User"
```

**Step 3: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/adapters/auth/test_postgres.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4: Write minimal implementation**

```python
# backend/src/dataing/adapters/auth/__init__.py
"""Auth adapters."""

from dataing.adapters.auth.postgres import PostgresAuthRepository

__all__ = ["PostgresAuthRepository"]
```

```python
# backend/src/dataing/adapters/auth/postgres.py
"""PostgreSQL implementation of AuthRepository."""

from datetime import datetime, timezone
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
        params.append(datetime.now(timezone.utc))
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
        return self._row_to_team(row)

    # Membership operations
    async def get_user_org_membership(
        self, user_id: UUID, org_id: UUID
    ) -> OrgMembership | None:
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
        return TeamMembership(
            user_id=row["user_id"],
            team_id=row["team_id"],
            created_at=row["created_at"],
        )
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/adapters/auth/test_postgres.py -v
```

Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/adapters/auth backend/tests/unit/adapters/auth
git commit -m "feat(auth): add PostgresAuthRepository implementation"
```

---

## Task 13: Auth Service Layer

**Files:**
- Create: `backend/src/dataing/core/auth/service.py`
- Test: `backend/tests/unit/core/auth/test_service.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/core/auth/test_service.py
"""Tests for auth service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from uuid import uuid4

from dataing.core.auth.service import AuthService, AuthError
from dataing.core.auth.types import User, Organization, OrgRole


class TestAuthServiceLogin:
    """Test login functionality."""

    @pytest.fixture
    def mock_repo(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo: MagicMock) -> AuthService:
        """Create service with mock repo."""
        return AuthService(mock_repo)

    @pytest.mark.asyncio
    async def test_login_success(
        self, service: AuthService, mock_repo: MagicMock
    ) -> None:
        """Should return tokens on successful login."""
        from dataing.core.auth.password import hash_password

        user_id = uuid4()
        org_id = uuid4()
        password_hash = hash_password("correct_password")

        mock_repo.get_user_by_email = AsyncMock(
            return_value=User(
                id=user_id,
                email="test@example.com",
                name="Test",
                password_hash=password_hash,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        mock_repo.get_user_orgs = AsyncMock(
            return_value=[
                (
                    Organization(
                        id=org_id,
                        name="Test Org",
                        slug="test-org",
                        plan="free",
                        created_at=datetime.now(timezone.utc),
                    ),
                    OrgRole.ADMIN,
                )
            ]
        )
        mock_repo.get_user_teams = AsyncMock(return_value=[])

        result = await service.login("test@example.com", "correct_password", org_id)

        assert "access_token" in result
        assert "refresh_token" in result
        assert result["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self, service: AuthService, mock_repo: MagicMock
    ) -> None:
        """Should raise AuthError for wrong password."""
        from dataing.core.auth.password import hash_password

        mock_repo.get_user_by_email = AsyncMock(
            return_value=User(
                id=uuid4(),
                email="test@example.com",
                name="Test",
                password_hash=hash_password("correct_password"),
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )

        with pytest.raises(AuthError) as exc_info:
            await service.login("test@example.com", "wrong_password", uuid4())

        assert "invalid" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_login_user_not_found(
        self, service: AuthService, mock_repo: MagicMock
    ) -> None:
        """Should raise AuthError when user not found."""
        mock_repo.get_user_by_email = AsyncMock(return_value=None)

        with pytest.raises(AuthError) as exc_info:
            await service.login("notfound@example.com", "password", uuid4())

        assert "invalid" in str(exc_info.value).lower()


class TestAuthServiceRegister:
    """Test registration functionality."""

    @pytest.fixture
    def mock_repo(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo: MagicMock) -> AuthService:
        """Create service with mock repo."""
        return AuthService(mock_repo)

    @pytest.mark.asyncio
    async def test_register_creates_user_and_org(
        self, service: AuthService, mock_repo: MagicMock
    ) -> None:
        """Should create user and organization."""
        user_id = uuid4()
        org_id = uuid4()
        created_at = datetime.now(timezone.utc)

        mock_repo.get_user_by_email = AsyncMock(return_value=None)
        mock_repo.get_org_by_slug = AsyncMock(return_value=None)
        mock_repo.create_user = AsyncMock(
            return_value=User(
                id=user_id,
                email="new@example.com",
                name="New User",
                password_hash="hashed",  # pragma: allowlist secret
                is_active=True,
                created_at=created_at,
            )
        )
        mock_repo.create_org = AsyncMock(
            return_value=Organization(
                id=org_id,
                name="New Org",
                slug="new-org",
                plan="free",
                created_at=created_at,
            )
        )
        mock_repo.add_user_to_org = AsyncMock()

        result = await service.register(
            email="new@example.com",
            password="password123",  # pragma: allowlist secret
            name="New User",
            org_name="New Org",
        )

        assert result["user"]["email"] == "new@example.com"
        assert "access_token" in result
        mock_repo.add_user_to_org.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_existing_email_fails(
        self, service: AuthService, mock_repo: MagicMock
    ) -> None:
        """Should raise AuthError when email already exists."""
        mock_repo.get_user_by_email = AsyncMock(
            return_value=User(
                id=uuid4(),
                email="existing@example.com",
                name="Existing",
                password_hash="hash",  # pragma: allowlist secret
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )

        with pytest.raises(AuthError) as exc_info:
            await service.register(
                email="existing@example.com",
                password="password123",  # pragma: allowlist secret
                name="Name",
                org_name="Org",
            )

        assert "already exists" in str(exc_info.value).lower()
```

**Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_service.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/core/auth/service.py
"""Auth service for login, registration, and token management."""

import re
from uuid import UUID

from dataing.core.auth.jwt import create_access_token, create_refresh_token, decode_token
from dataing.core.auth.password import hash_password, verify_password
from dataing.core.auth.repository import AuthRepository
from dataing.core.auth.types import OrgRole, TokenPayload


class AuthError(Exception):
    """Raised when authentication fails."""

    pass


class AuthService:
    """Service for authentication operations."""

    def __init__(self, repo: AuthRepository) -> None:
        """Initialize with auth repository.

        Args:
            repo: Auth repository for database operations.
        """
        self._repo = repo

    async def login(
        self,
        email: str,
        password: str,
        org_id: UUID,
    ) -> dict:
        """Authenticate user and return tokens.

        Args:
            email: User's email address.
            password: Plain text password.
            org_id: Organization to log into.

        Returns:
            Dict with access_token, refresh_token, user info, and org info.

        Raises:
            AuthError: If authentication fails.
        """
        # Get user
        user = await self._repo.get_user_by_email(email)
        if not user:
            raise AuthError("Invalid email or password")

        if not user.is_active:
            raise AuthError("User account is disabled")

        if not user.password_hash:
            raise AuthError("Password login not enabled for this account")

        # Verify password
        if not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password")

        # Get user's membership in org
        membership = await self._repo.get_user_org_membership(user.id, org_id)
        if not membership:
            raise AuthError("User is not a member of this organization")

        # Get org details
        org = await self._repo.get_org_by_id(org_id)
        if not org:
            raise AuthError("Organization not found")

        # Get user's teams in this org
        teams = await self._repo.get_user_teams(user.id, org_id)
        team_ids = [str(t.id) for t in teams]

        # Create tokens
        access_token = create_access_token(
            user_id=str(user.id),
            org_id=str(org_id),
            role=membership.role.value,
            teams=team_ids,
        )
        refresh_token = create_refresh_token(user_id=str(user.id))

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
            },
            "org": {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "plan": org.plan,
            },
            "role": membership.role.value,
        }

    async def register(
        self,
        email: str,
        password: str,
        name: str,
        org_name: str,
        org_slug: str | None = None,
    ) -> dict:
        """Register new user and create organization.

        Args:
            email: User's email address.
            password: Plain text password.
            name: User's display name.
            org_name: Organization name.
            org_slug: Optional org slug (generated from name if not provided).

        Returns:
            Dict with access_token, refresh_token, user info, and org info.

        Raises:
            AuthError: If registration fails.
        """
        # Check if user already exists
        existing = await self._repo.get_user_by_email(email)
        if existing:
            raise AuthError("User with this email already exists")

        # Generate slug if not provided
        if not org_slug:
            org_slug = self._generate_slug(org_name)

        # Check if org slug is taken
        existing_org = await self._repo.get_org_by_slug(org_slug)
        if existing_org:
            raise AuthError("Organization with this slug already exists")

        # Create user
        password_hash = hash_password(password)
        user = await self._repo.create_user(
            email=email,
            name=name,
            password_hash=password_hash,
        )

        # Create org
        org = await self._repo.create_org(
            name=org_name,
            slug=org_slug,
            plan="free",
        )

        # Add user as owner
        membership = await self._repo.add_user_to_org(
            user_id=user.id,
            org_id=org.id,
            role=OrgRole.OWNER,
        )

        # Create tokens
        access_token = create_access_token(
            user_id=str(user.id),
            org_id=str(org.id),
            role=OrgRole.OWNER.value,
            teams=[],
        )
        refresh_token = create_refresh_token(user_id=str(user.id))

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
            },
            "org": {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "plan": org.plan,
            },
            "role": OrgRole.OWNER.value,
        }

    async def refresh(self, refresh_token: str, org_id: UUID) -> dict:
        """Refresh access token.

        Args:
            refresh_token: Valid refresh token.
            org_id: Organization to get new token for.

        Returns:
            Dict with new access_token.

        Raises:
            AuthError: If refresh fails.
        """
        # Decode refresh token
        try:
            payload = decode_token(refresh_token)
        except Exception as e:
            raise AuthError(f"Invalid refresh token: {e}") from None

        # Get user
        user = await self._repo.get_user_by_id(UUID(payload.sub))
        if not user or not user.is_active:
            raise AuthError("User not found or disabled")

        # Get membership
        membership = await self._repo.get_user_org_membership(user.id, org_id)
        if not membership:
            raise AuthError("User is not a member of this organization")

        # Get teams
        teams = await self._repo.get_user_teams(user.id, org_id)
        team_ids = [str(t.id) for t in teams]

        # Create new access token
        access_token = create_access_token(
            user_id=str(user.id),
            org_id=str(org_id),
            role=membership.role.value,
            teams=team_ids,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    def _generate_slug(self, name: str) -> str:
        """Generate URL-safe slug from name."""
        slug = name.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        return slug
```

**Step 4: Update `__init__.py`**

```python
# Add to backend/src/dataing/core/auth/__init__.py
from dataing.core.auth.service import AuthService, AuthError

# Add to __all__:
__all__ = [
    # ... existing exports ...
    "AuthService",
    "AuthError",
]
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/core/auth/test_service.py -v
```

Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/core/auth
git commit -m "feat(auth): add AuthService for login and registration"
```

---

## Task 14: Auth API Routes

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/auth.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_auth.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/entrypoints/api/routes/test_auth.py
"""Tests for auth API routes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from dataing.entrypoints.api.routes.auth import router


@pytest.fixture
def app() -> FastAPI:
    """Create test app with auth router."""
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestLoginEndpoint:
    """Test POST /auth/login."""

    def test_login_success(self, client: TestClient) -> None:
        """Should return tokens on successful login."""
        with patch(
            "dataing.entrypoints.api.routes.auth.get_auth_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.login = AsyncMock(
                return_value={
                    "access_token": "access.token.here",
                    "refresh_token": "refresh.token.here",
                    "token_type": "bearer",
                    "user": {"id": "user-id", "email": "test@example.com", "name": "Test"},
                    "org": {"id": "org-id", "name": "Org", "slug": "org", "plan": "free"},
                    "role": "admin",
                }
            )
            mock_get_service.return_value = mock_service

            response = client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "password123",  # pragma: allowlist secret
                    "org_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_invalid_credentials(self, client: TestClient) -> None:
        """Should return 401 for invalid credentials."""
        with patch(
            "dataing.entrypoints.api.routes.auth.get_auth_service"
        ) as mock_get_service:
            from dataing.core.auth.service import AuthError

            mock_service = MagicMock()
            mock_service.login = AsyncMock(side_effect=AuthError("Invalid credentials"))
            mock_get_service.return_value = mock_service

            response = client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "wrong",  # pragma: allowlist secret
                    "org_id": "00000000-0000-0000-0000-000000000001",
                },
            )

        assert response.status_code == 401


class TestRegisterEndpoint:
    """Test POST /auth/register."""

    def test_register_success(self, client: TestClient) -> None:
        """Should create user and return tokens."""
        with patch(
            "dataing.entrypoints.api.routes.auth.get_auth_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.register = AsyncMock(
                return_value={
                    "access_token": "access.token.here",
                    "refresh_token": "refresh.token.here",
                    "token_type": "bearer",
                    "user": {"id": "user-id", "email": "new@example.com", "name": "New User"},
                    "org": {"id": "org-id", "name": "New Org", "slug": "new-org", "plan": "free"},
                    "role": "owner",
                }
            )
            mock_get_service.return_value = mock_service

            response = client.post(
                "/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "password123",  # pragma: allowlist secret
                    "name": "New User",
                    "org_name": "New Org",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "new@example.com"
```

**Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/entrypoints/api/routes/test_auth.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/entrypoints/api/routes/auth.py
"""Auth API routes for login, registration, and token refresh."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.core.auth.service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


# Request/Response models
class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr
    password: str
    org_id: UUID


class RegisterRequest(BaseModel):
    """Registration request body."""

    email: EmailStr
    password: str
    name: str
    org_name: str
    org_slug: str | None = None


class RefreshRequest(BaseModel):
    """Token refresh request body."""

    refresh_token: str
    org_id: UUID


class TokenResponse(BaseModel):
    """Token response."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: dict | None = None
    org: dict | None = None
    role: str | None = None


def get_auth_service(request: Request) -> AuthService:
    """Get auth service from request context."""
    app_db = request.app.state.app_db
    repo = PostgresAuthRepository(app_db)
    return AuthService(repo)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Authenticate user and return tokens.

    Args:
        body: Login credentials.
        service: Auth service.

    Returns:
        Access and refresh tokens with user/org info.
    """
    try:
        result = await service.login(
            email=body.email,
            password=body.password,
            org_id=body.org_id,
        )
        return TokenResponse(**result)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Register new user and create organization.

    Args:
        body: Registration info.
        service: Auth service.

    Returns:
        Access and refresh tokens with user/org info.
    """
    try:
        result = await service.register(
            email=body.email,
            password=body.password,
            name=body.name,
            org_name=body.org_name,
            org_slug=body.org_slug,
        )
        return TokenResponse(**result)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Refresh access token.

    Args:
        body: Refresh token and org ID.
        service: Auth service.

    Returns:
        New access token.
    """
    try:
        result = await service.refresh(
            refresh_token=body.refresh_token,
            org_id=body.org_id,
        )
        return TokenResponse(**result)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None


@router.get("/me")
async def get_current_user(request: Request) -> dict:
    """Get current authenticated user info.

    Requires JWT authentication via the jwt_auth middleware.
    """
    # This will be populated by JWT middleware
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "user_id": request.state.user.sub,
        "org_id": request.state.user.org_id,
        "role": request.state.user.role,
        "teams": request.state.user.teams,
    }
```

**Step 4: Add router to routes/__init__.py**

```python
# Add to backend/src/dataing/entrypoints/api/routes/__init__.py
from dataing.entrypoints.api.routes.auth import router as auth_router

# Add to api_router:
api_router.include_router(auth_router)
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/entrypoints/api/routes/test_auth.py -v
```

Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes
git commit -m "feat(auth): add login, register, and refresh API endpoints"
```

---

## Task 15: JWT Auth Middleware

**Files:**
- Create: `backend/src/dataing/entrypoints/api/middleware/jwt_auth.py`
- Modify: `backend/src/dataing/entrypoints/api/middleware/__init__.py`
- Test: `backend/tests/unit/entrypoints/api/middleware/test_jwt_auth.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/entrypoints/api/middleware/test_jwt_auth.py
"""Tests for JWT authentication middleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from dataing.entrypoints.api.middleware.jwt_auth import (
    verify_jwt,
    JwtContext,
    require_role,
)
from dataing.core.auth.types import OrgRole


class TestVerifyJwt:
    """Test JWT verification dependency."""

    @pytest.mark.asyncio
    async def test_valid_token(self) -> None:
        """Should return JwtContext for valid token."""
        from dataing.core.auth.jwt import create_access_token

        token = create_access_token(
            user_id="user-123",
            org_id="org-456",
            role="admin",
            teams=["team-1"],
        )

        mock_request = MagicMock()

        context = await verify_jwt(mock_request, token)

        assert context.user_id == "user-123"
        assert context.org_id == "org-456"
        assert context.role == OrgRole.ADMIN

    @pytest.mark.asyncio
    async def test_missing_token(self) -> None:
        """Should raise 401 for missing token."""
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt(mock_request, None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token(self) -> None:
        """Should raise 401 for invalid token."""
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt(mock_request, "invalid.token.here")

        assert exc_info.value.status_code == 401


class TestRequireRole:
    """Test role requirement decorator."""

    @pytest.mark.asyncio
    async def test_allows_sufficient_role(self) -> None:
        """Should allow when user has required role or higher."""
        context = JwtContext(
            user_id="user-123",
            org_id="org-456",
            role=OrgRole.ADMIN,
            teams=["team-1"],
        )

        checker = require_role(OrgRole.MEMBER)
        result = await checker(context)

        assert result == context

    @pytest.mark.asyncio
    async def test_blocks_insufficient_role(self) -> None:
        """Should raise 403 when role is insufficient."""
        context = JwtContext(
            user_id="user-123",
            org_id="org-456",
            role=OrgRole.VIEWER,
            teams=[],
        )

        checker = require_role(OrgRole.ADMIN)

        with pytest.raises(HTTPException) as exc_info:
            await checker(context)

        assert exc_info.value.status_code == 403
```

**Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/entrypoints/api/middleware/test_jwt_auth.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/entrypoints/api/middleware/jwt_auth.py
"""JWT authentication middleware."""

from dataclasses import dataclass
from typing import Annotated, Any, Callable
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dataing.core.auth.jwt import TokenError, decode_token
from dataing.core.auth.types import OrgRole

logger = structlog.get_logger()

# Use Bearer token authentication
bearer_scheme = HTTPBearer(auto_error=False)

# Role hierarchy - higher index = more permissions
ROLE_HIERARCHY = [OrgRole.VIEWER, OrgRole.MEMBER, OrgRole.ADMIN, OrgRole.OWNER]


@dataclass
class JwtContext:
    """Context from a verified JWT token."""

    user_id: str
    org_id: str
    role: OrgRole
    teams: list[str]

    @property
    def user_uuid(self) -> UUID:
        """Get user ID as UUID."""
        return UUID(self.user_id)

    @property
    def org_uuid(self) -> UUID:
        """Get org ID as UUID."""
        return UUID(self.org_id)


async def verify_jwt(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> JwtContext:
    """Verify JWT token and return context.

    This dependency validates the JWT and returns user/org context.

    Args:
        request: The current request.
        credentials: Bearer token credentials.

    Returns:
        JwtContext with user info.

    Raises:
        HTTPException: 401 if token is missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except TokenError as e:
        logger.warning("jwt_validation_failed", error=str(e))
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    context = JwtContext(
        user_id=payload.sub,
        org_id=payload.org_id,
        role=OrgRole(payload.role),
        teams=payload.teams,
    )

    # Store in request state for downstream use
    request.state.user = context

    logger.debug(
        "jwt_verified",
        user_id=context.user_id,
        org_id=context.org_id,
        role=context.role.value,
    )

    return context


def require_role(min_role: OrgRole) -> Callable[..., Any]:
    """Dependency to require a minimum role level.

    Role hierarchy (lowest to highest):
    - viewer: read-only access
    - member: can create/modify own resources
    - admin: can manage team resources
    - owner: full control including billing/settings

    Usage:
        @router.delete("/{id}")
        async def delete_item(
            auth: Annotated[JwtContext, Depends(require_role(OrgRole.ADMIN))],
        ):
            ...

    Args:
        min_role: Minimum required role.

    Returns:
        Dependency function that validates role.
    """

    async def role_checker(
        auth: Annotated[JwtContext, Depends(verify_jwt)],
    ) -> JwtContext:
        user_role_idx = ROLE_HIERARCHY.index(auth.role)
        required_role_idx = ROLE_HIERARCHY.index(min_role)

        if user_role_idx < required_role_idx:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{min_role.value}' or higher required",
            )
        return auth

    return role_checker


# Common role dependencies for convenience
RequireViewer = Annotated[JwtContext, Depends(require_role(OrgRole.VIEWER))]
RequireMember = Annotated[JwtContext, Depends(require_role(OrgRole.MEMBER))]
RequireAdmin = Annotated[JwtContext, Depends(require_role(OrgRole.ADMIN))]
RequireOwner = Annotated[JwtContext, Depends(require_role(OrgRole.OWNER))]


# Optional JWT - returns None if no token provided
async def optional_jwt(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> JwtContext | None:
    """Optionally verify JWT, returning None if not provided."""
    if not credentials:
        return None

    try:
        return await verify_jwt(request, credentials)
    except HTTPException:
        return None
```

**Step 4: Update middleware/__init__.py**

```python
# backend/src/dataing/entrypoints/api/middleware/__init__.py
"""API middleware modules."""

from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    optional_api_key,
    require_scope,
    verify_api_key,
)
from dataing.entrypoints.api.middleware.jwt_auth import (
    JwtContext,
    RequireAdmin,
    RequireMember,
    RequireOwner,
    RequireViewer,
    optional_jwt,
    require_role,
    verify_jwt,
)

__all__ = [
    # API Key auth
    "ApiKeyContext",
    "verify_api_key",
    "require_scope",
    "optional_api_key",
    # JWT auth
    "JwtContext",
    "verify_jwt",
    "require_role",
    "optional_jwt",
    "RequireViewer",
    "RequireMember",
    "RequireAdmin",
    "RequireOwner",
]
```

**Step 5: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=src uv run pytest tests/unit/entrypoints/api/middleware/test_jwt_auth.py -v
```

Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/src/dataing/entrypoints/api/middleware
git commit -m "feat(auth): add JWT authentication middleware with role checking"
```

---

## Task 16: Frontend Auth Types and API

**Files:**
- Create: `frontend/src/lib/auth/types.ts`
- Create: `frontend/src/lib/auth/api.ts`
- Modify: `frontend/src/lib/auth/context.tsx`

**Step 1: Create types file**

```typescript
// frontend/src/lib/auth/types.ts
export interface User {
  id: string
  email: string
  name: string | null
}

export interface Organization {
  id: string
  name: string
  slug: string
  plan: 'free' | 'pro' | 'enterprise'
}

export type OrgRole = 'owner' | 'admin' | 'member' | 'viewer'

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface LoginResponse extends AuthTokens {
  user: User
  org: Organization
  role: OrgRole
}

export interface LoginRequest {
  email: string
  password: string
  org_id: string
}

export interface RegisterRequest {
  email: string
  password: string
  name: string
  org_name: string
  org_slug?: string
}

export interface RefreshRequest {
  refresh_token: string
  org_id: string
}

export interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
  user: User | null
  org: Organization | null
  role: OrgRole | null
  accessToken: string | null
}
```

**Step 2: Create API file**

```typescript
// frontend/src/lib/auth/api.ts
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RefreshRequest,
  AuthTokens,
} from './types'

const API_BASE = import.meta.env.VITE_API_URL || ''

export async function login(request: LoginRequest): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Login failed' }))
    throw new Error(error.detail || 'Login failed')
  }

  return response.json()
}

export async function register(request: RegisterRequest): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Registration failed' }))
    throw new Error(error.detail || 'Registration failed')
  }

  return response.json()
}

export async function refreshToken(request: RefreshRequest): Promise<AuthTokens> {
  const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new Error('Token refresh failed')
  }

  return response.json()
}
```

**Step 3: Update context.tsx**

```typescript
// frontend/src/lib/auth/context.tsx
import * as React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import type { User, Organization, OrgRole, AuthState } from './types'
import { login as apiLogin, register as apiRegister, refreshToken } from './api'

interface AuthContextType extends AuthState {
  login: (email: string, password: string, orgId: string) => Promise<void>
  register: (
    email: string,
    password: string,
    name: string,
    orgName: string
  ) => Promise<void>
  logout: () => void
  switchOrg: (orgId: string) => Promise<void>
}

const AuthContext = React.createContext<AuthContextType | null>(null)

const ACCESS_TOKEN_KEY = 'dataing_access_token'
const REFRESH_TOKEN_KEY = 'dataing_refresh_token'
const USER_KEY = 'dataing_user'
const ORG_KEY = 'dataing_org'
const ROLE_KEY = 'dataing_role'

export function useAuth() {
  const context = React.useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = React.useState(true)
  const [accessToken, setAccessToken] = React.useState<string | null>(null)
  const [refreshTokenValue, setRefreshTokenValue] = React.useState<string | null>(null)
  const [user, setUser] = React.useState<User | null>(null)
  const [org, setOrg] = React.useState<Organization | null>(null)
  const [role, setRole] = React.useState<OrgRole | null>(null)

  // Load stored auth state on mount
  React.useEffect(() => {
    const storedAccessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
    const storedUser = localStorage.getItem(USER_KEY)
    const storedOrg = localStorage.getItem(ORG_KEY)
    const storedRole = localStorage.getItem(ROLE_KEY)

    if (storedAccessToken && storedUser && storedOrg) {
      setAccessToken(storedAccessToken)
      setRefreshTokenValue(storedRefreshToken)
      try {
        setUser(JSON.parse(storedUser))
        setOrg(JSON.parse(storedOrg))
        setRole(storedRole as OrgRole)
      } catch {
        // Invalid stored data, clear it
        clearStorage()
      }
    }
    setIsLoading(false)
  }, [])

  const clearStorage = React.useCallback(() => {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(ORG_KEY)
    localStorage.removeItem(ROLE_KEY)
  }, [])

  const saveAuthState = React.useCallback(
    (
      token: string,
      refresh: string,
      userData: User,
      orgData: Organization,
      roleData: OrgRole
    ) => {
      localStorage.setItem(ACCESS_TOKEN_KEY, token)
      localStorage.setItem(REFRESH_TOKEN_KEY, refresh)
      localStorage.setItem(USER_KEY, JSON.stringify(userData))
      localStorage.setItem(ORG_KEY, JSON.stringify(orgData))
      localStorage.setItem(ROLE_KEY, roleData)

      setAccessToken(token)
      setRefreshTokenValue(refresh)
      setUser(userData)
      setOrg(orgData)
      setRole(roleData)
    },
    []
  )

  const login = React.useCallback(
    async (email: string, password: string, orgId: string) => {
      const response = await apiLogin({ email, password, org_id: orgId })
      saveAuthState(
        response.access_token,
        response.refresh_token,
        response.user,
        response.org,
        response.role
      )
    },
    [saveAuthState]
  )

  const register = React.useCallback(
    async (email: string, password: string, name: string, orgName: string) => {
      const response = await apiRegister({ email, password, name, org_name: orgName })
      saveAuthState(
        response.access_token,
        response.refresh_token,
        response.user,
        response.org,
        response.role
      )
    },
    [saveAuthState]
  )

  const logout = React.useCallback(() => {
    clearStorage()
    setAccessToken(null)
    setRefreshTokenValue(null)
    setUser(null)
    setOrg(null)
    setRole(null)
  }, [clearStorage])

  const switchOrg = React.useCallback(
    async (orgId: string) => {
      if (!refreshTokenValue) {
        throw new Error('No refresh token available')
      }

      const response = await refreshToken({
        refresh_token: refreshTokenValue,
        org_id: orgId,
      })

      // Note: switchOrg only gets new access token, need to fetch org details separately
      setAccessToken(response.access_token)
      localStorage.setItem(ACCESS_TOKEN_KEY, response.access_token)
    },
    [refreshTokenValue]
  )

  const value = React.useMemo<AuthContextType>(
    () => ({
      isAuthenticated: !!accessToken,
      isLoading,
      user,
      org,
      role,
      accessToken,
      login,
      register,
      logout,
      switchOrg,
    }),
    [isLoading, accessToken, user, org, role, login, register, logout, switchOrg]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/login', { state: { from: location }, replace: true })
    }
  }, [isAuthenticated, isLoading, navigate, location])

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return <>{children}</>
}
```

**Step 4: Update auth index.ts**

```typescript
// frontend/src/lib/auth/index.ts
export type {
  User,
  Organization,
  OrgRole,
  AuthTokens,
  LoginResponse,
  LoginRequest,
  RegisterRequest,
  RefreshRequest,
  AuthState,
} from './types'
export { login, register, refreshToken } from './api'
export { AuthProvider, useAuth, RequireAuth } from './context'
```

**Step 5: Commit**

```bash
git add frontend/src/lib/auth
git commit -m "feat(frontend): update auth context to use JWT tokens"
```

---

## Task 17: Update Login Page for JWT

**Files:**
- Modify: `frontend/src/features/auth/login-page.tsx`

**Step 1: Read current login page**

```bash
cat frontend/src/features/auth/login-page.tsx
```

**Step 2: Update login page to support JWT auth**

The login page needs to be updated to:
1. Accept email/password instead of API key
2. Show organization selection (for users in multiple orgs)
3. Handle registration flow

```typescript
// frontend/src/features/auth/login-page.tsx
import * as React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, register, isAuthenticated } = useAuth()

  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  // Login form state
  const [loginEmail, setLoginEmail] = React.useState('')
  const [loginPassword, setLoginPassword] = React.useState('')
  const [loginOrgId, setLoginOrgId] = React.useState('')

  // Register form state
  const [registerEmail, setRegisterEmail] = React.useState('')
  const [registerPassword, setRegisterPassword] = React.useState('')
  const [registerName, setRegisterName] = React.useState('')
  const [registerOrgName, setRegisterOrgName] = React.useState('')

  // Redirect if already authenticated
  React.useEffect(() => {
    if (isAuthenticated) {
      const from = (location.state as { from?: Location })?.from?.pathname || '/'
      navigate(from, { replace: true })
    }
  }, [isAuthenticated, navigate, location])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      await login(loginEmail, loginPassword, loginOrgId)
      const from = (location.state as { from?: Location })?.from?.pathname || '/'
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      await register(registerEmail, registerPassword, registerName, registerOrgName)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Dataing</CardTitle>
          <CardDescription>
            AI-powered data quality investigations
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="login" className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="login">Login</TabsTrigger>
              <TabsTrigger value="register">Register</TabsTrigger>
            </TabsList>

            <TabsContent value="login">
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="login-email">Email</Label>
                  <Input
                    id="login-email"
                    type="email"
                    placeholder="you@company.com"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="login-password">Password</Label>
                  <Input
                    id="login-password"
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="login-org">Organization ID</Label>
                  <Input
                    id="login-org"
                    type="text"
                    placeholder="org-uuid"
                    value={loginOrgId}
                    onChange={(e) => setLoginOrgId(e.target.value)}
                    required
                  />
                  <p className="text-xs text-muted-foreground">
                    For demo: use 00000000-0000-0000-0000-000000000001
                  </p>
                </div>

                {error && (
                  <div className="text-sm text-destructive">{error}</div>
                )}

                <Button type="submit" className="w-full" disabled={isLoading}>
                  {isLoading ? 'Signing in...' : 'Sign In'}
                </Button>
              </form>
            </TabsContent>

            <TabsContent value="register">
              <form onSubmit={handleRegister} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="register-email">Email</Label>
                  <Input
                    id="register-email"
                    type="email"
                    placeholder="you@company.com"
                    value={registerEmail}
                    onChange={(e) => setRegisterEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-password">Password</Label>
                  <Input
                    id="register-password"
                    type="password"
                    value={registerPassword}
                    onChange={(e) => setRegisterPassword(e.target.value)}
                    required
                    minLength={8}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-name">Your Name</Label>
                  <Input
                    id="register-name"
                    type="text"
                    placeholder="Jane Doe"
                    value={registerName}
                    onChange={(e) => setRegisterName(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-org">Organization Name</Label>
                  <Input
                    id="register-org"
                    type="text"
                    placeholder="Acme Corp"
                    value={registerOrgName}
                    onChange={(e) => setRegisterOrgName(e.target.value)}
                    required
                  />
                </div>

                {error && (
                  <div className="text-sm text-destructive">{error}</div>
                )}

                <Button type="submit" className="w-full" disabled={isLoading}>
                  {isLoading ? 'Creating account...' : 'Create Account'}
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add frontend/src/features/auth/login-page.tsx
git commit -m "feat(frontend): update login page for JWT authentication"
```

---

## Summary

This plan covers the remaining Phase 2 tasks:

| Task | Description | Files |
|------|-------------|-------|
| 11 | Auth Repository Protocol | `core/auth/repository.py` |
| 12 | PostgreSQL Auth Repository | `adapters/auth/postgres.py` |
| 13 | Auth Service Layer | `core/auth/service.py` |
| 14 | Auth API Routes | `routes/auth.py` |
| 15 | JWT Auth Middleware | `middleware/jwt_auth.py` |
| 16 | Frontend Auth Types/API | `lib/auth/*.ts` |
| 17 | Update Login Page | `features/auth/login-page.tsx` |

After completing these tasks, the system will have:
- Full user/org/team CRUD via repository pattern
- Login, register, and token refresh endpoints
- JWT-based authentication with role checking
- Frontend updated to use JWT instead of API keys

### Future Work (Phase 3+):
- Migrate existing API key routes to support both auth methods
- Add org selector for users in multiple orgs
- Implement password reset flow
- Add SSO/OIDC support
