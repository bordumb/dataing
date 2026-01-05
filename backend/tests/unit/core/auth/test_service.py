"""Tests for auth service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.core.auth.service import AuthError, AuthService
from dataing.core.auth.types import Organization, OrgRole, User


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
    async def test_login_success(self, service: AuthService, mock_repo: MagicMock) -> None:
        """Should return tokens on successful login."""
        from dataing.core.auth.password import hash_password

        user_id = uuid4()
        org_id = uuid4()
        password_hash = hash_password("correct_password")  # pragma: allowlist secret

        mock_repo.get_user_by_email = AsyncMock(
            return_value=User(
                id=user_id,
                email="test@example.com",
                name="Test",
                password_hash=password_hash,
                is_active=True,
                created_at=datetime.now(UTC),
            )
        )
        mock_repo.get_user_org_membership = AsyncMock(return_value=MagicMock(role=OrgRole.ADMIN))
        mock_repo.get_org_by_id = AsyncMock(
            return_value=Organization(
                id=org_id,
                name="Test Org",
                slug="test-org",
                plan="free",
                created_at=datetime.now(UTC),
            )
        )
        mock_repo.get_user_teams = AsyncMock(return_value=[])

        result = await service.login(
            "test@example.com",
            "correct_password",
            org_id,  # pragma: allowlist secret
        )

        assert "access_token" in result
        assert "refresh_token" in result
        assert result["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, service: AuthService, mock_repo: MagicMock) -> None:
        """Should raise AuthError for wrong password."""
        from dataing.core.auth.password import hash_password

        mock_repo.get_user_by_email = AsyncMock(
            return_value=User(
                id=uuid4(),
                email="test@example.com",
                name="Test",
                password_hash=hash_password(
                    "correct_password"  # pragma: allowlist secret
                ),
                is_active=True,
                created_at=datetime.now(UTC),
            )
        )

        with pytest.raises(AuthError) as exc_info:
            await service.login(
                "test@example.com",
                "wrong_password",  # pragma: allowlist secret
                uuid4(),
            )

        assert "invalid" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_login_user_not_found(self, service: AuthService, mock_repo: MagicMock) -> None:
        """Should raise AuthError when user not found."""
        mock_repo.get_user_by_email = AsyncMock(return_value=None)

        with pytest.raises(AuthError) as exc_info:
            await service.login(
                "notfound@example.com",
                "password",  # pragma: allowlist secret
                uuid4(),
            )

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
        created_at = datetime.now(UTC)

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
                created_at=datetime.now(UTC),
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
