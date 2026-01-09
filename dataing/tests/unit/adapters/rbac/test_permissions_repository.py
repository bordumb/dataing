"""Tests for permissions repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

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
    user_id: UUID | None = None,
    team_id: UUID | None = None,
    resource_id: UUID | None = None,
    tag_id: UUID | None = None,
    data_source_id: UUID | None = None,
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
        """Creates a user -> resource grant."""
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


class TestCreateUserTagGrant:
    """Tests for create_user_tag_grant method."""

    async def test_creates_grant(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Creates a user -> tag grant."""
        user_id = uuid4()
        tag_id = uuid4()

        mock_conn.fetchrow = AsyncMock(return_value=make_grant_row(user_id=user_id, tag_id=tag_id))

        grant = await repository.create_user_tag_grant(
            org_id=uuid4(),
            user_id=user_id,
            tag_id=tag_id,
            permission=Permission.WRITE,
        )

        assert grant.user_id == user_id
        assert grant.tag_id == tag_id


class TestCreateUserDatasourceGrant:
    """Tests for create_user_datasource_grant method."""

    async def test_creates_grant(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Creates a user -> datasource grant."""
        user_id = uuid4()
        data_source_id = uuid4()

        mock_conn.fetchrow = AsyncMock(
            return_value=make_grant_row(user_id=user_id, data_source_id=data_source_id)
        )

        grant = await repository.create_user_datasource_grant(
            org_id=uuid4(),
            user_id=user_id,
            data_source_id=data_source_id,
            permission=Permission.READ,
        )

        assert grant.user_id == user_id
        assert grant.data_source_id == data_source_id


class TestCreateTeamResourceGrant:
    """Tests for create_team_resource_grant method."""

    async def test_creates_grant(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Creates a team -> resource grant."""
        team_id = uuid4()
        resource_id = uuid4()

        mock_conn.fetchrow = AsyncMock(
            return_value=make_grant_row(team_id=team_id, resource_id=resource_id)
        )

        grant = await repository.create_team_resource_grant(
            org_id=uuid4(),
            team_id=team_id,
            resource_type="investigation",
            resource_id=resource_id,
            permission=Permission.ADMIN,
        )

        assert grant.team_id == team_id
        assert grant.resource_id == resource_id


class TestCreateTeamTagGrant:
    """Tests for create_team_tag_grant method."""

    async def test_creates_grant(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Creates a team -> tag grant."""
        team_id = uuid4()
        tag_id = uuid4()

        mock_conn.fetchrow = AsyncMock(return_value=make_grant_row(team_id=team_id, tag_id=tag_id))

        grant = await repository.create_team_tag_grant(
            org_id=uuid4(),
            team_id=team_id,
            tag_id=tag_id,
            permission=Permission.READ,
        )

        assert grant.team_id == team_id
        assert grant.tag_id == tag_id


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


class TestListByOrg:
    """Tests for list_by_org method."""

    async def test_returns_grants(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns list of grants for organization."""
        user_id = uuid4()

        mock_conn.fetch = AsyncMock(
            return_value=[
                make_grant_row(user_id=user_id),
                make_grant_row(user_id=user_id),
            ]
        )

        grants = await repository.list_by_org(uuid4())

        assert len(grants) == 2

    async def test_returns_empty_list_when_no_grants(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when no grants."""
        mock_conn.fetch = AsyncMock(return_value=[])

        grants = await repository.list_by_org(uuid4())

        assert grants == []


class TestListByUser:
    """Tests for list_by_user method."""

    async def test_returns_grants(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns list of grants for user."""
        user_id = uuid4()

        mock_conn.fetch = AsyncMock(
            return_value=[
                make_grant_row(user_id=user_id, resource_id=uuid4()),
                make_grant_row(user_id=user_id, tag_id=uuid4()),
            ]
        )

        grants = await repository.list_by_user(user_id)

        assert len(grants) == 2
        assert all(g.user_id == user_id for g in grants)

    async def test_returns_empty_list_when_no_grants(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when user has no grants."""
        mock_conn.fetch = AsyncMock(return_value=[])

        grants = await repository.list_by_user(uuid4())

        assert grants == []


class TestListByResource:
    """Tests for list_by_resource method."""

    async def test_returns_grants(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns list of grants for resource."""
        resource_id = uuid4()

        mock_conn.fetch = AsyncMock(
            return_value=[
                make_grant_row(user_id=uuid4(), resource_id=resource_id),
                make_grant_row(team_id=uuid4(), resource_id=resource_id),
            ]
        )

        grants = await repository.list_by_resource("investigation", resource_id)

        assert len(grants) == 2

    async def test_returns_empty_list_when_no_grants(
        self, repository: PermissionsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when resource has no grants."""
        mock_conn.fetch = AsyncMock(return_value=[])

        grants = await repository.list_by_resource("investigation", uuid4())

        assert grants == []
