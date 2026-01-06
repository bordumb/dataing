"""Tests for tags repository."""

from datetime import UTC, datetime
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

    async def test_creates_tag(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
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
        assert tag.color == "#6366f1"

    async def test_creates_tag_with_custom_color(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Creates a new tag with custom color."""
        org_id = uuid4()
        tag_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": tag_id,
                "org_id": org_id,
                "name": "urgent",
                "color": "#ef4444",
                "created_at": now,
            }
        )

        tag = await repository.create(org_id, "urgent", color="#ef4444")

        assert tag.color == "#ef4444"


class TestGetById:
    """Tests for get_by_id method."""

    async def test_returns_tag(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
        """Returns tag when found."""
        tag_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": tag_id,
                "org_id": uuid4(),
                "name": "finance",
                "color": "#6366f1",
                "created_at": now,
            }
        )

        tag = await repository.get_by_id(tag_id)

        assert tag is not None
        assert tag.id == tag_id

    async def test_returns_none_when_not_found(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when tag not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        tag = await repository.get_by_id(uuid4())

        assert tag is None


class TestGetByName:
    """Tests for get_by_name method."""

    async def test_returns_tag(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
        """Returns tag when found by name."""
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

        tag = await repository.get_by_name(org_id, "finance")

        assert tag is not None
        assert tag.name == "finance"

    async def test_returns_none_when_not_found(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when tag not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        tag = await repository.get_by_name(uuid4(), "nonexistent")

        assert tag is None


class TestListByOrg:
    """Tests for list_by_org method."""

    async def test_returns_tags(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
        """Returns list of tags for organization."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "name": "finance",
                    "color": "#6366f1",
                    "created_at": now,
                },
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "name": "urgent",
                    "color": "#ef4444",
                    "created_at": now,
                },
            ]
        )

        tags = await repository.list_by_org(org_id)

        assert len(tags) == 2
        assert tags[0].name == "finance"
        assert tags[1].name == "urgent"

    async def test_returns_empty_list_when_no_tags(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when no tags."""
        mock_conn.fetch = AsyncMock(return_value=[])

        tags = await repository.list_by_org(uuid4())

        assert tags == []


class TestUpdate:
    """Tests for update method."""

    async def test_updates_name(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
        """Updates tag name."""
        tag_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": tag_id,
                "org_id": uuid4(),
                "name": "new-name",
                "color": "#6366f1",
                "created_at": now,
            }
        )

        tag = await repository.update(tag_id, name="new-name")

        assert tag is not None
        assert tag.name == "new-name"

    async def test_updates_color(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
        """Updates tag color."""
        tag_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": tag_id,
                "org_id": uuid4(),
                "name": "finance",
                "color": "#22c55e",
                "created_at": now,
            }
        )

        tag = await repository.update(tag_id, color="#22c55e")

        assert tag is not None
        assert tag.color == "#22c55e"

    async def test_returns_existing_when_no_updates(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns existing tag when no updates provided."""
        tag_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": tag_id,
                "org_id": uuid4(),
                "name": "finance",
                "color": "#6366f1",
                "created_at": now,
            }
        )

        tag = await repository.update(tag_id)

        assert tag is not None
        # get_by_id should have been called
        mock_conn.fetchrow.assert_called_once()

    async def test_returns_none_when_not_found(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when tag not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        tag = await repository.update(uuid4(), name="new-name")

        assert tag is None


class TestDelete:
    """Tests for delete method."""

    async def test_deletes_tag(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
        """Deletes tag successfully."""
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        result = await repository.delete(uuid4())

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when tag not found."""
        mock_conn.execute = AsyncMock(return_value="DELETE 0")

        result = await repository.delete(uuid4())

        assert result is False


class TestAddToInvestigation:
    """Tests for add_to_investigation method."""

    async def test_adds_tag(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
        """Adds tag to investigation."""
        mock_conn.execute = AsyncMock()

        result = await repository.add_to_investigation(uuid4(), uuid4())

        assert result is True

    async def test_returns_false_on_error(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False on database error."""
        mock_conn.execute = AsyncMock(side_effect=Exception("Database error"))

        result = await repository.add_to_investigation(uuid4(), uuid4())

        assert result is False


class TestRemoveFromInvestigation:
    """Tests for remove_from_investigation method."""

    async def test_removes_tag(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
        """Removes tag from investigation."""
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        result = await repository.remove_from_investigation(uuid4(), uuid4())

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when tag not on investigation."""
        mock_conn.execute = AsyncMock(return_value="DELETE 0")

        result = await repository.remove_from_investigation(uuid4(), uuid4())

        assert result is False


class TestGetInvestigationTags:
    """Tests for get_investigation_tags method."""

    async def test_returns_tags(self, repository: TagsRepository, mock_conn: MagicMock) -> None:
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

    async def test_returns_empty_list_when_no_tags(
        self, repository: TagsRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when investigation has no tags."""
        mock_conn.fetch = AsyncMock(return_value=[])

        tags = await repository.get_investigation_tags(uuid4())

        assert tags == []
