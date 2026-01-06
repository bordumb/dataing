"""Tests for SCIM group repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dataing.adapters.sso import SCIMGroupRepository


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def repository(mock_conn: MagicMock) -> SCIMGroupRepository:
    """Create repository with mock connection."""
    return SCIMGroupRepository(mock_conn)


class TestIsRoleGroup:
    """Tests for _is_role_group method."""

    def test_returns_true_for_role_prefix(self, repository: SCIMGroupRepository) -> None:
        """Returns True for role-prefixed groups."""
        assert repository._is_role_group("role-admin") is True
        assert repository._is_role_group("role-owner") is True
        assert repository._is_role_group("Role-Admin") is True

    def test_returns_false_for_non_role(self, repository: SCIMGroupRepository) -> None:
        """Returns False for non-role groups."""
        assert repository._is_role_group("Engineering") is False
        assert repository._is_role_group("admin") is False
        assert repository._is_role_group("role") is False


class TestExtractRole:
    """Tests for _extract_role method."""

    def test_extracts_role_name(self, repository: SCIMGroupRepository) -> None:
        """Extracts role name from display name."""
        assert repository._extract_role("role-admin") == "admin"
        assert repository._extract_role("role-owner") == "owner"
        assert repository._extract_role("Role-Admin") == "admin"
        assert repository._extract_role("role-member") == "member"


class TestCreateGroup:
    """Tests for create_group method."""

    async def test_creates_team_for_non_role_group(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Creates team for non-role groups."""
        org_id = uuid4()
        team_id = uuid4()

        # Mock teams_repo.create - use configure_mock for 'name' attribute
        mock_team = MagicMock()
        mock_team.id = team_id
        mock_team.configure_mock(name="Engineering")
        mock_team.external_id = "ext-123"

        with (
            patch.object(
                repository._teams_repo,
                "create",
                new=AsyncMock(return_value=mock_team),
            ),
            patch.object(
                repository._teams_repo,
                "add_member",
                new=AsyncMock(return_value=True),
            ),
        ):
            result = await repository.create_group(
                org_id=org_id,
                display_name="Engineering",
                external_id="ext-123",
            )

        assert result["display_name"] == "Engineering"
        assert result["is_role_group"] is False
        assert result["id"] == str(team_id)
        assert result["external_id"] == "ext-123"

    async def test_creates_team_with_members(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Creates team and adds members."""
        org_id = uuid4()
        team_id = uuid4()
        user_id1 = uuid4()
        user_id2 = uuid4()

        mock_team = MagicMock()
        mock_team.id = team_id
        mock_team.configure_mock(name="Engineering")
        mock_team.external_id = "ext-123"

        add_member_mock = AsyncMock(return_value=True)
        with (
            patch.object(
                repository._teams_repo,
                "create",
                new=AsyncMock(return_value=mock_team),
            ),
            patch.object(
                repository._teams_repo,
                "add_member",
                new=add_member_mock,
            ),
        ):
            result = await repository.create_group(
                org_id=org_id,
                display_name="Engineering",
                external_id="ext-123",
                member_ids=[user_id1, user_id2],
            )

        assert result["member_count"] == 2
        assert add_member_mock.call_count == 2

    async def test_creates_role_group_for_role_prefix(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Creates role group for role-prefixed names."""
        org_id = uuid4()
        group_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": group_id,
                "org_id": org_id,
                "external_id": "role-admin",
                "role_name": "admin",
                "created_at": now,
            }
        )
        mock_conn.execute = AsyncMock()

        result = await repository.create_group(
            org_id=org_id,
            display_name="role-admin",
        )

        assert result["is_role_group"] is True
        assert result["role"] == "admin"
        assert result["id"] == str(group_id)

    async def test_creates_role_group_with_members(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Creates role group and assigns role to members."""
        org_id = uuid4()
        group_id = uuid4()
        user_id1 = uuid4()
        user_id2 = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": group_id,
                "org_id": org_id,
                "external_id": "role-owner",
                "role_name": "owner",
                "created_at": now,
            }
        )
        mock_conn.execute = AsyncMock()

        result = await repository.create_group(
            org_id=org_id,
            display_name="role-owner",
            member_ids=[user_id1, user_id2],
        )

        assert result["role"] == "owner"
        assert result["member_count"] == 2
        # Verify role was assigned to users
        assert mock_conn.execute.call_count == 2

    async def test_raises_for_invalid_role(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Raises ValueError for invalid role."""
        org_id = uuid4()

        with pytest.raises(ValueError, match="Invalid role"):
            await repository.create_group(
                org_id=org_id,
                display_name="role-superadmin",
            )


class TestGetGroup:
    """Tests for get_group method."""

    async def test_returns_team_group(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns team when found."""
        org_id = uuid4()
        team_id = uuid4()
        user_id = uuid4()

        with (
            patch.object(
                repository._teams_repo,
                "get_by_id",
                new=AsyncMock(
                    return_value=MagicMock(
                        id=team_id,
                        org_id=org_id,
                        name="Engineering",
                        external_id="ext-123",
                    )
                ),
            ),
            patch.object(
                repository._teams_repo,
                "get_members",
                new=AsyncMock(return_value=[user_id]),
            ),
        ):
            result = await repository.get_group(org_id, team_id)

        assert result is not None
        assert result["id"] == str(team_id)
        assert result["is_role_group"] is False
        assert result["member_ids"] == [str(user_id)]

    async def test_returns_role_group(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns role group when found."""
        org_id = uuid4()
        group_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.fetchrow = AsyncMock(
                return_value={
                    "id": group_id,
                    "org_id": org_id,
                    "external_id": "role-admin",
                    "role_name": "admin",
                    "created_at": now,
                }
            )
            mock_conn.fetch = AsyncMock(return_value=[{"id": user_id}])

            result = await repository.get_group(org_id, group_id)

        assert result is not None
        assert result["id"] == str(group_id)
        assert result["is_role_group"] is True
        assert result["role"] == "admin"
        assert result["member_ids"] == [str(user_id)]

    async def test_returns_none_when_not_found(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when group not found."""
        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.fetchrow = AsyncMock(return_value=None)

            result = await repository.get_group(uuid4(), uuid4())

        assert result is None

    async def test_returns_none_for_wrong_org(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when team belongs to different org."""
        org_id = uuid4()
        other_org_id = uuid4()
        team_id = uuid4()

        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(
                return_value=MagicMock(
                    id=team_id,
                    org_id=other_org_id,  # Different org
                    name="Engineering",
                )
            ),
        ):
            mock_conn.fetchrow = AsyncMock(return_value=None)

            result = await repository.get_group(org_id, team_id)

        assert result is None


class TestGetGroupByExternalId:
    """Tests for get_group_by_external_id method."""

    async def test_returns_team_by_external_id(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns team when found by external ID."""
        org_id = uuid4()
        team_id = uuid4()
        user_id = uuid4()

        with (
            patch.object(
                repository._teams_repo,
                "get_by_external_id",
                new=AsyncMock(
                    return_value=MagicMock(
                        id=team_id,
                        org_id=org_id,
                        name="Engineering",
                        external_id="ext-123",
                    )
                ),
            ),
            patch.object(
                repository._teams_repo,
                "get_members",
                new=AsyncMock(return_value=[user_id]),
            ),
        ):
            result = await repository.get_group_by_external_id(org_id, "ext-123")

        assert result is not None
        assert result["external_id"] == "ext-123"
        assert result["is_role_group"] is False

    async def test_returns_role_group_by_external_id(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns role group when found by external ID."""
        org_id = uuid4()
        group_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        with patch.object(
            repository._teams_repo,
            "get_by_external_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.fetchrow = AsyncMock(
                return_value={
                    "id": group_id,
                    "org_id": org_id,
                    "external_id": "role-ext-123",
                    "role_name": "admin",
                    "created_at": now,
                }
            )
            mock_conn.fetch = AsyncMock(return_value=[{"id": user_id}])

            result = await repository.get_group_by_external_id(org_id, "role-ext-123")

        assert result is not None
        assert result["is_role_group"] is True
        assert result["role"] == "admin"


class TestDeleteGroup:
    """Tests for delete_group method."""

    async def test_deletes_team(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Deletes team group."""
        org_id = uuid4()
        team_id = uuid4()

        with (
            patch.object(
                repository._teams_repo,
                "get_by_id",
                new=AsyncMock(
                    return_value=MagicMock(
                        id=team_id,
                        org_id=org_id,
                    )
                ),
            ),
            patch.object(
                repository._teams_repo,
                "delete",
                new=AsyncMock(return_value=True),
            ),
        ):
            result = await repository.delete_group(org_id, team_id)

        assert result is True

    async def test_deletes_role_group(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Deletes role group."""
        org_id = uuid4()
        group_id = uuid4()

        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.execute = AsyncMock(return_value="DELETE 1")

            result = await repository.delete_group(org_id, group_id)

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when group not found."""
        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.execute = AsyncMock(return_value="DELETE 0")

            result = await repository.delete_group(uuid4(), uuid4())

        assert result is False


class TestListGroups:
    """Tests for list_groups method."""

    async def test_lists_all_groups(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Lists both teams and role groups."""
        org_id = uuid4()
        team_id = uuid4()
        role_group_id = uuid4()
        user_id = uuid4()

        mock_team = MagicMock()
        mock_team.id = team_id
        mock_team.configure_mock(name="Engineering")
        mock_team.external_id = "team-ext"

        with (
            patch.object(
                repository._teams_repo,
                "list_by_org",
                new=AsyncMock(return_value=[mock_team]),
            ),
            patch.object(
                repository._teams_repo,
                "get_members",
                new=AsyncMock(return_value=[user_id]),
            ),
        ):
            mock_conn.fetch = AsyncMock(
                side_effect=[
                    [{"id": role_group_id, "external_id": "role-ext", "role_name": "admin"}],
                    [{"id": user_id}],
                ]
            )

            groups, total = await repository.list_groups(org_id)

        assert total == 2
        assert len(groups) == 2
        # First should be team
        assert groups[0]["is_role_group"] is False
        assert groups[0]["display_name"] == "Engineering"
        # Second should be role group
        assert groups[1]["is_role_group"] is True
        assert groups[1]["role"] == "admin"

    async def test_paginates_results(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Applies pagination to results."""
        org_id = uuid4()
        team_id1 = uuid4()
        team_id2 = uuid4()

        mock_team1 = MagicMock()
        mock_team1.id = team_id1
        mock_team1.configure_mock(name="Team 1")
        mock_team1.external_id = None

        mock_team2 = MagicMock()
        mock_team2.id = team_id2
        mock_team2.configure_mock(name="Team 2")
        mock_team2.external_id = None

        with (
            patch.object(
                repository._teams_repo,
                "list_by_org",
                new=AsyncMock(return_value=[mock_team1, mock_team2]),
            ),
            patch.object(
                repository._teams_repo,
                "get_members",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_conn.fetch = AsyncMock(return_value=[])

            groups, total = await repository.list_groups(org_id, start_index=2, count=1)

        assert total == 2
        assert len(groups) == 1
        assert groups[0]["display_name"] == "Team 2"


class TestUpdateGroup:
    """Tests for update_group method."""

    async def test_updates_team_name(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Updates team display name."""
        org_id = uuid4()
        team_id = uuid4()
        user_id = uuid4()

        with (
            patch.object(
                repository._teams_repo,
                "get_by_id",
                new=AsyncMock(
                    return_value=MagicMock(
                        id=team_id,
                        org_id=org_id,
                        name="Engineering",
                        external_id="ext-123",
                    )
                ),
            ),
            patch.object(
                repository._teams_repo,
                "get_members",
                new=AsyncMock(return_value=[user_id]),
            ),
            patch.object(
                repository._teams_repo,
                "update",
                new=AsyncMock(
                    return_value=MagicMock(
                        id=team_id,
                        org_id=org_id,
                        name="Platform",
                        external_id="ext-123",
                    )
                ),
            ),
        ):
            result = await repository.update_group(org_id, team_id, display_name="Platform")

        assert result is not None

    async def test_returns_none_when_not_found(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when group not found."""
        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.fetchrow = AsyncMock(return_value=None)

            result = await repository.update_group(uuid4(), uuid4(), display_name="New Name")

        assert result is None


class TestUpdateGroupMembers:
    """Tests for update_group_members method."""

    async def test_updates_team_members(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Updates team membership."""
        org_id = uuid4()
        team_id = uuid4()
        old_user = uuid4()
        new_user = uuid4()

        mock_team = MagicMock()
        mock_team.id = team_id
        mock_team.org_id = org_id
        mock_team.configure_mock(name="Engineering")
        mock_team.external_id = "ext-123"

        # get_members is called 3 times:
        # 1. First get_group call (initial state)
        # 2. During update to get current members
        # 3. Final get_group call (returns updated state)
        get_by_id_mock = AsyncMock(return_value=mock_team)
        get_members_mock = AsyncMock(side_effect=[[old_user], [old_user], [new_user]])
        remove_member_mock = AsyncMock(return_value=True)
        add_member_mock = AsyncMock(return_value=True)

        with (
            patch.object(repository._teams_repo, "get_by_id", new=get_by_id_mock),
            patch.object(repository._teams_repo, "get_members", new=get_members_mock),
            patch.object(repository._teams_repo, "remove_member", new=remove_member_mock),
            patch.object(repository._teams_repo, "add_member", new=add_member_mock),
        ):
            result = await repository.update_group_members(org_id, team_id, [new_user])

        assert result is not None
        remove_member_mock.assert_called_once_with(team_id, old_user)
        add_member_mock.assert_called_once_with(team_id, new_user)

    async def test_updates_role_group_members(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Updates role group membership (assigns/removes role)."""
        org_id = uuid4()
        group_id = uuid4()
        old_user = uuid4()
        new_user = uuid4()
        now = datetime.now(UTC)

        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            # First fetchrow gets role group, second gets updated group
            mock_conn.fetchrow = AsyncMock(
                return_value={
                    "id": group_id,
                    "org_id": org_id,
                    "external_id": "role-admin",
                    "role_name": "admin",
                    "created_at": now,
                }
            )
            # First fetch gets current members, second gets new members
            mock_conn.fetch = AsyncMock(
                side_effect=[
                    [{"id": old_user}],  # Current members
                    [{"id": new_user}],  # New members after update
                ]
            )
            mock_conn.execute = AsyncMock()

            result = await repository.update_group_members(org_id, group_id, [new_user])

        assert result is not None
        # Should have called execute twice: once to remove old user role, once to add new
        assert mock_conn.execute.call_count == 2


class TestAddGroupMember:
    """Tests for add_group_member method."""

    async def test_adds_member_to_team(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Adds member to team group."""
        org_id = uuid4()
        team_id = uuid4()
        user_id = uuid4()

        with (
            patch.object(
                repository._teams_repo,
                "get_by_id",
                new=AsyncMock(
                    return_value=MagicMock(
                        id=team_id,
                        org_id=org_id,
                        name="Engineering",
                        external_id="ext-123",
                    )
                ),
            ),
            patch.object(
                repository._teams_repo,
                "get_members",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                repository._teams_repo,
                "add_member",
                new=AsyncMock(return_value=True),
            ) as add_mock,
        ):
            result = await repository.add_group_member(org_id, team_id, user_id)

        assert result is True
        add_mock.assert_called_once_with(team_id, user_id)

    async def test_adds_member_to_role_group(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Adds member to role group (assigns role)."""
        org_id = uuid4()
        group_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.fetchrow = AsyncMock(
                return_value={
                    "id": group_id,
                    "org_id": org_id,
                    "external_id": "role-admin",
                    "role_name": "admin",
                    "created_at": now,
                }
            )
            mock_conn.fetch = AsyncMock(return_value=[])
            mock_conn.execute = AsyncMock()

            result = await repository.add_group_member(org_id, group_id, user_id)

        assert result is True
        # Should have updated user role to admin
        mock_conn.execute.assert_called_once()

    async def test_returns_false_when_group_not_found(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when group not found."""
        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.fetchrow = AsyncMock(return_value=None)

            result = await repository.add_group_member(uuid4(), uuid4(), uuid4())

        assert result is False


class TestRemoveGroupMember:
    """Tests for remove_group_member method."""

    async def test_removes_member_from_team(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Removes member from team group."""
        org_id = uuid4()
        team_id = uuid4()
        user_id = uuid4()

        with (
            patch.object(
                repository._teams_repo,
                "get_by_id",
                new=AsyncMock(
                    return_value=MagicMock(
                        id=team_id,
                        org_id=org_id,
                        name="Engineering",
                        external_id="ext-123",
                    )
                ),
            ),
            patch.object(
                repository._teams_repo,
                "get_members",
                new=AsyncMock(return_value=[user_id]),
            ),
            patch.object(
                repository._teams_repo,
                "remove_member",
                new=AsyncMock(return_value=True),
            ) as remove_mock,
        ):
            result = await repository.remove_group_member(org_id, team_id, user_id)

        assert result is True
        remove_mock.assert_called_once_with(team_id, user_id)

    async def test_removes_member_from_role_group(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Removes member from role group (resets to member role)."""
        org_id = uuid4()
        group_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.fetchrow = AsyncMock(
                return_value={
                    "id": group_id,
                    "org_id": org_id,
                    "external_id": "role-admin",
                    "role_name": "admin",
                    "created_at": now,
                }
            )
            mock_conn.fetch = AsyncMock(return_value=[{"id": user_id}])
            mock_conn.execute = AsyncMock()

            result = await repository.remove_group_member(org_id, group_id, user_id)

        assert result is True
        # Should have reset user role to member
        mock_conn.execute.assert_called_once()

    async def test_returns_false_when_group_not_found(
        self, repository: SCIMGroupRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when group not found."""
        with patch.object(
            repository._teams_repo,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            mock_conn.fetchrow = AsyncMock(return_value=None)

            result = await repository.remove_group_member(uuid4(), uuid4(), uuid4())

        assert result is False
