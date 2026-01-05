"""Tests for PostgreSQL auth repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.core.auth import AuthRepository, OrgRole


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
                "created_at": datetime.now(UTC),
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
    async def test_create_user(self, repo: PostgresAuthRepository, mock_db: MagicMock) -> None:
        """Should create user and return it."""
        user_id = uuid4()
        created_at = datetime.now(UTC)
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

    @pytest.mark.asyncio
    async def test_get_org_by_slug(self, repo: PostgresAuthRepository, mock_db: MagicMock) -> None:
        """Should return org when found by slug."""
        org_id = uuid4()
        mock_db.fetch_one = AsyncMock(
            return_value={
                "id": org_id,
                "name": "Test Org",
                "slug": "test-org",
                "plan": "free",
                "created_at": datetime.now(UTC),
            }
        )

        result = await repo.get_org_by_slug("test-org")

        assert result is not None
        assert result.slug == "test-org"
        assert result.id == org_id

    @pytest.mark.asyncio
    async def test_add_user_to_org(self, repo: PostgresAuthRepository, mock_db: MagicMock) -> None:
        """Should add user to org with role."""
        user_id = uuid4()
        org_id = uuid4()
        created_at = datetime.now(UTC)
        mock_db.fetch_one = AsyncMock(
            return_value={
                "user_id": user_id,
                "org_id": org_id,
                "role": "admin",
                "created_at": created_at,
            }
        )

        result = await repo.add_user_to_org(user_id, org_id, OrgRole.ADMIN)

        assert result.user_id == user_id
        assert result.org_id == org_id
        assert result.role == OrgRole.ADMIN
