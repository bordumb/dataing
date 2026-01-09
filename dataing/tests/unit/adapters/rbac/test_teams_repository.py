"""Tests for teams repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.rbac import TeamsRepository


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

    async def test_creates_team(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
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

    async def test_returns_team(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
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


class TestGetByExternalId:
    """Tests for get_by_external_id method."""

    async def test_returns_team(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
        """Returns team when found by external ID."""
        org_id = uuid4()
        team_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": team_id,
                "org_id": org_id,
                "name": "Engineering",
                "external_id": "ext-123",
                "is_scim_managed": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        team = await repository.get_by_external_id(org_id, "ext-123")

        assert team is not None
        assert team.external_id == "ext-123"
        assert team.is_scim_managed is True

    async def test_returns_none_when_not_found(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when team not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        team = await repository.get_by_external_id(uuid4(), "nonexistent")

        assert team is None


class TestListByOrg:
    """Tests for list_by_org method."""

    async def test_returns_teams(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
        """Returns list of teams for organization."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "name": "Alpha",
                    "external_id": None,
                    "is_scim_managed": False,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "name": "Beta",
                    "external_id": None,
                    "is_scim_managed": False,
                    "created_at": now,
                    "updated_at": now,
                },
            ]
        )

        teams = await repository.list_by_org(org_id)

        assert len(teams) == 2
        assert teams[0].name == "Alpha"
        assert teams[1].name == "Beta"

    async def test_returns_empty_list_when_no_teams(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when no teams."""
        mock_conn.fetch = AsyncMock(return_value=[])

        teams = await repository.list_by_org(uuid4())

        assert teams == []


class TestUpdate:
    """Tests for update method."""

    async def test_updates_team(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
        """Updates team name."""
        team_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": team_id,
                "org_id": uuid4(),
                "name": "New Name",
                "external_id": None,
                "is_scim_managed": False,
                "created_at": now,
                "updated_at": now,
            }
        )

        team = await repository.update(team_id, "New Name")

        assert team is not None
        assert team.name == "New Name"

    async def test_returns_none_when_not_found(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when team not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        team = await repository.update(uuid4(), "New Name")

        assert team is None


class TestDelete:
    """Tests for delete method."""

    async def test_deletes_team(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
        """Deletes team successfully."""
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        result = await repository.delete(uuid4())

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when team not found."""
        mock_conn.execute = AsyncMock(return_value="DELETE 0")

        result = await repository.delete(uuid4())

        assert result is False


class TestAddMember:
    """Tests for add_member method."""

    async def test_adds_member(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
        """Adds member to team."""
        mock_conn.execute = AsyncMock()

        result = await repository.add_member(uuid4(), uuid4())

        assert result is True

    async def test_returns_false_on_error(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False on database error."""
        mock_conn.execute = AsyncMock(side_effect=Exception("Database error"))

        result = await repository.add_member(uuid4(), uuid4())

        assert result is False


class TestRemoveMember:
    """Tests for remove_member method."""

    async def test_removes_member(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
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


class TestGetMembers:
    """Tests for get_members method."""

    async def test_returns_member_ids(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns list of member UUIDs."""
        user_id_1 = uuid4()
        user_id_2 = uuid4()

        mock_conn.fetch = AsyncMock(
            return_value=[
                {"user_id": user_id_1},
                {"user_id": user_id_2},
            ]
        )

        members = await repository.get_members(uuid4())

        assert len(members) == 2
        assert user_id_1 in members
        assert user_id_2 in members

    async def test_returns_empty_list_when_no_members(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when team has no members."""
        mock_conn.fetch = AsyncMock(return_value=[])

        members = await repository.get_members(uuid4())

        assert members == []


class TestGetUserTeams:
    """Tests for get_user_teams method."""

    async def test_returns_teams(self, repository: TeamsRepository, mock_conn: MagicMock) -> None:
        """Returns teams user belongs to."""
        user_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "org_id": uuid4(),
                    "name": "Team A",
                    "external_id": None,
                    "is_scim_managed": False,
                    "created_at": now,
                    "updated_at": now,
                },
            ]
        )

        teams = await repository.get_user_teams(user_id)

        assert len(teams) == 1
        assert teams[0].name == "Team A"

    async def test_returns_empty_list_when_not_in_any_team(
        self, repository: TeamsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when user not in any team."""
        mock_conn.fetch = AsyncMock(return_value=[])

        teams = await repository.get_user_teams(uuid4())

        assert teams == []
