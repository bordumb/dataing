"""Tests for SCIM user repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing_ee.adapters.sso import SCIMUserRepository


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def repository(mock_conn: MagicMock) -> SCIMUserRepository:
    """Create repository with mock connection."""
    return SCIMUserRepository(mock_conn)


class TestCreateUser:
    """Tests for create_user method."""

    async def test_creates_user(self, repository: SCIMUserRepository, mock_conn: MagicMock) -> None:
        """Creates a new user."""
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": user_id,
                "tenant_id": org_id,
                "email": "test@example.com",
                "name": "Test User",
                "role": "member",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        user = await repository.create_user(
            org_id=org_id,
            email="test@example.com",
            name="Test User",
        )

        assert user["id"] == user_id
        assert user["email"] == "test@example.com"
        assert user["role"] == "member"

    async def test_creates_user_with_external_id(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Creates user and links SSO identity when external_id provided."""
        org_id = uuid4()
        user_id = uuid4()
        sso_config_id = uuid4()
        now = datetime.now(UTC)

        # First call returns user, second call returns SSO config
        mock_conn.fetchrow = AsyncMock(
            side_effect=[
                {
                    "id": user_id,
                    "tenant_id": org_id,
                    "email": "test@example.com",
                    "name": "Test User",
                    "role": "member",
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                },
                {"id": sso_config_id},  # SSO config row
            ]
        )
        mock_conn.execute = AsyncMock(return_value="INSERT 0 1")

        user = await repository.create_user(
            org_id=org_id,
            email="test@example.com",
            name="Test User",
            external_id="ext-123",
        )

        assert user["id"] == user_id
        # Verify SSO identity was created
        assert mock_conn.execute.called


class TestGetUserById:
    """Tests for get_user_by_id method."""

    async def test_returns_user(self, repository: SCIMUserRepository, mock_conn: MagicMock) -> None:
        """Returns user when found."""
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": user_id,
                "tenant_id": org_id,
                "email": "test@example.com",
                "name": "Test User",
                "role": "member",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        user = await repository.get_user_by_id(org_id, user_id)

        assert user is not None
        assert user["id"] == user_id

    async def test_returns_none_when_not_found(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when user not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        user = await repository.get_user_by_id(uuid4(), uuid4())

        assert user is None


class TestGetUserByEmail:
    """Tests for get_user_by_email method."""

    async def test_returns_user(self, repository: SCIMUserRepository, mock_conn: MagicMock) -> None:
        """Returns user when found by email."""
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": user_id,
                "tenant_id": org_id,
                "email": "test@example.com",
                "name": "Test User",
                "role": "member",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        user = await repository.get_user_by_email(org_id, "test@example.com")

        assert user is not None
        assert user["email"] == "test@example.com"

    async def test_returns_none_when_not_found(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when user not found by email."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        user = await repository.get_user_by_email(uuid4(), "unknown@example.com")

        assert user is None


class TestGetUserByExternalId:
    """Tests for get_user_by_external_id method."""

    async def test_returns_user(self, repository: SCIMUserRepository, mock_conn: MagicMock) -> None:
        """Returns user when found by external ID."""
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": user_id,
                "tenant_id": org_id,
                "email": "test@example.com",
                "name": "Test User",
                "role": "member",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        user = await repository.get_user_by_external_id(org_id, "ext-123")

        assert user is not None
        assert user["id"] == user_id

    async def test_returns_none_when_not_found(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when user not found by external ID."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        user = await repository.get_user_by_external_id(uuid4(), "unknown-ext")

        assert user is None


class TestUpdateUser:
    """Tests for update_user method."""

    async def test_updates_user(self, repository: SCIMUserRepository, mock_conn: MagicMock) -> None:
        """Updates user fields."""
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": user_id,
                "tenant_id": org_id,
                "email": "new@example.com",
                "name": "New Name",
                "role": "member",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        user = await repository.update_user(
            org_id, user_id, email="new@example.com", name="New Name"
        )

        assert user is not None
        assert user["email"] == "new@example.com"
        assert user["name"] == "New Name"

    async def test_returns_none_when_not_found(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when user not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        user = await repository.update_user(uuid4(), uuid4(), email="new@example.com")

        assert user is None


class TestDeactivateUser:
    """Tests for deactivate_user method."""

    async def test_deactivates_user(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Deactivates a user."""
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await repository.deactivate_user(uuid4(), uuid4())

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when user not found."""
        mock_conn.execute = AsyncMock(return_value="UPDATE 0")

        result = await repository.deactivate_user(uuid4(), uuid4())

        assert result is False


class TestListUsers:
    """Tests for list_users method."""

    async def test_lists_users(self, repository: SCIMUserRepository, mock_conn: MagicMock) -> None:
        """Lists users with pagination."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchval = AsyncMock(return_value=2)
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "tenant_id": org_id,
                    "email": "user1@example.com",
                    "name": "User 1",
                    "role": "member",
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": uuid4(),
                    "tenant_id": org_id,
                    "email": "user2@example.com",
                    "name": "User 2",
                    "role": "admin",
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                },
            ]
        )

        users, total = await repository.list_users(org_id)

        assert len(users) == 2
        assert total == 2
        assert users[0]["email"] == "user1@example.com"
        assert users[1]["email"] == "user2@example.com"

    async def test_lists_users_with_filter(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Lists users with email filter."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "tenant_id": org_id,
                    "email": "specific@example.com",
                    "name": "Specific User",
                    "role": "member",
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                }
            ]
        )

        users, total = await repository.list_users(org_id, filter_email="specific@example.com")

        assert len(users) == 1
        assert total == 1
        assert users[0]["email"] == "specific@example.com"


class TestUpdateUserRole:
    """Tests for update_user_role method."""

    async def test_updates_role(self, repository: SCIMUserRepository, mock_conn: MagicMock) -> None:
        """Updates user's role."""
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await repository.update_user_role(uuid4(), uuid4(), "admin")

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: SCIMUserRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when user not found."""
        mock_conn.execute = AsyncMock(return_value="UPDATE 0")

        result = await repository.update_user_role(uuid4(), uuid4(), "admin")

        assert result is False
