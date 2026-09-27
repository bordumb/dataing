"""Tests for auth service."""

from datetime import UTC, datetime, timedelta
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


def _user(is_active: bool = True) -> User:
    """Create a password user."""
    return User(
        id=uuid4(),
        email="test@example.com",
        name="Test",
        password_hash="hash",  # pragma: allowlist secret
        is_active=is_active,
        created_at=datetime.now(UTC),
    )


def _org() -> Organization:
    """Create an organization."""
    return Organization(id=uuid4(), name="Org", slug="org", created_at=datetime.now(UTC))


class TestAuthServicePasswordReset:
    """Test password reset functionality."""

    @pytest.fixture
    def mock_repo(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo: MagicMock) -> AuthService:
        """Create service with mock repo."""
        return AuthService(mock_repo)

    @pytest.mark.asyncio
    async def test_request_returns_user_a_link_was_issued_for(
        self, service: AuthService, mock_repo: MagicMock
    ) -> None:
        """Should return the user so the caller can audit the request."""
        user = _user()
        mock_repo.get_user_by_email = AsyncMock(return_value=user)
        mock_repo.delete_user_reset_tokens = AsyncMock(return_value=0)
        mock_repo.create_password_reset_token = AsyncMock()
        recovery_adapter = MagicMock()
        recovery_adapter.initiate_recovery = AsyncMock(return_value=True)

        result = await service.request_password_reset(
            email=user.email,
            recovery_adapter=recovery_adapter,
            frontend_url="https://app.example.com",
        )

        assert result == user
        recovery_adapter.initiate_recovery.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("user", [None, _user(is_active=False)], ids=["unknown", "inactive"])
    async def test_request_returns_none_when_no_link_is_issued(
        self, service: AuthService, mock_repo: MagicMock, user: User | None
    ) -> None:
        """Should return None for unknown emails and inactive users."""
        mock_repo.get_user_by_email = AsyncMock(return_value=user)
        recovery_adapter = MagicMock()
        recovery_adapter.initiate_recovery = AsyncMock(return_value=True)

        result = await service.request_password_reset(
            email="nobody@example.com",
            recovery_adapter=recovery_adapter,
            frontend_url="https://app.example.com",
        )

        assert result is None
        recovery_adapter.initiate_recovery.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reset_password_returns_user(
        self, service: AuthService, mock_repo: MagicMock
    ) -> None:
        """Should return the user whose password was reset."""
        user = _user()
        mock_repo.get_password_reset_token = AsyncMock(
            return_value={
                "id": uuid4(),
                "user_id": user.id,
                "used_at": None,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }
        )
        mock_repo.get_user_by_id = AsyncMock(return_value=user)
        mock_repo.update_user = AsyncMock()
        mock_repo.mark_token_used = AsyncMock()
        mock_repo.delete_user_reset_tokens = AsyncMock(return_value=0)

        result = await service.reset_password(
            token="reset-token",
            new_password="new-password-123",  # pragma: allowlist secret
        )

        assert result == user
        mock_repo.update_user.assert_awaited_once()


class TestAuthServiceOrgLookups:
    """Test organization lookups used to attribute auth events."""

    @pytest.fixture
    def mock_repo(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo: MagicMock) -> AuthService:
        """Create service with mock repo."""
        return AuthService(mock_repo)

    @pytest.mark.asyncio
    async def test_get_user_org_ids(self, service: AuthService, mock_repo: MagicMock) -> None:
        """Should return the ID of every org the user belongs to."""
        org_a, org_b = _org(), _org()
        mock_repo.get_user_orgs = AsyncMock(
            return_value=[(org_a, OrgRole.ADMIN), (org_b, OrgRole.MEMBER)]
        )

        assert await service.get_user_org_ids(uuid4()) == [org_a.id, org_b.id]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("org", "expected"), [(_org(), True), (None, False)])
    async def test_org_exists(
        self,
        service: AuthService,
        mock_repo: MagicMock,
        org: Organization | None,
        expected: bool,
    ) -> None:
        """Should report whether an org ID refers to an existing org."""
        mock_repo.get_org_by_id = AsyncMock(return_value=org)

        assert await service.org_exists(uuid4()) is expected
