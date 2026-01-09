"""Tests for permission service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.core.rbac import PermissionService


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
