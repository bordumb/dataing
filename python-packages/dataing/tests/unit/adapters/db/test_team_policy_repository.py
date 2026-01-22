"""Unit tests for TeamPolicyRepository."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.team_policy_repository import (
    PolicyAction,
    TeamPolicy,
    TeamPolicyOverride,
    TeamPolicyRepository,
    TeamQueueLimits,
)


class TestTeamPolicyRepository:
    """Tests for TeamPolicyRepository."""

    @pytest.fixture
    def mock_conn(self) -> AsyncMock:
        """Return a mock connection."""
        return AsyncMock()

    @pytest.fixture
    def mock_db(self, mock_conn: AsyncMock) -> AppDatabase:
        """Return an AppDatabase instance with a mocked pool."""
        db = AppDatabase(dsn="postgresql://localhost/test")

        mock_pool = MagicMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool.acquire = mock_acquire
        mock_pool.close = AsyncMock()
        db.pool = mock_pool
        return db

    @pytest.fixture
    def repo(self, mock_db: AppDatabase) -> TeamPolicyRepository:
        """Return a TeamPolicyRepository instance."""
        return TeamPolicyRepository(mock_db)

    @pytest.fixture
    def sample_policy_row(self) -> dict:
        """Return a sample policy row from the database."""
        return {
            "id": uuid.uuid4(),
            "org_id": uuid.uuid4(),
            "team_id": uuid.uuid4(),
            "sources": ["dbt", "airflow"],
            "default_action": "auto",
            "auto_investigate_min_severity": "high",
            "review_required_max_severity": "critical",
            "is_active": True,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    @pytest.fixture
    def sample_override_row(self) -> dict:
        """Return a sample override row from the database."""
        return {
            "id": uuid.uuid4(),
            "org_id": uuid.uuid4(),
            "team_id": uuid.uuid4(),
            "dataset_id": "prod.analytics.orders",
            "tag_id": None,
            "default_action": "review",
            "auto_investigate_min_severity": None,
            "review_required_max_severity": None,
            "is_active": True,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    @pytest.fixture
    def sample_queue_limits_row(self) -> dict:
        """Return a sample queue limits row from the database."""
        return {
            "id": uuid.uuid4(),
            "org_id": uuid.uuid4(),
            "team_id": uuid.uuid4(),
            "rate_limit_per_minute": 120,
            "burst_size": 20,
            "max_concurrent": 10,
            "batch_size": 5,
            "is_active": True,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    # =========================================================================
    # Team Policy Tests
    # =========================================================================

    async def test_create_policy(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_policy_row: dict,
    ) -> None:
        """Test creating a team policy."""
        mock_conn.fetchrow.return_value = sample_policy_row

        org_id = sample_policy_row["org_id"]
        team_id = sample_policy_row["team_id"]

        policy = await repo.create_policy(
            org_id=org_id,
            team_id=team_id,
            sources=["dbt", "airflow"],
            default_action=PolicyAction.AUTO,
            auto_investigate_min_severity="high",
        )

        assert isinstance(policy, TeamPolicy)
        assert policy.org_id == org_id
        assert policy.team_id == team_id
        assert policy.default_action == PolicyAction.AUTO
        assert policy.sources == ["dbt", "airflow"]
        mock_conn.fetchrow.assert_called_once()

    async def test_get_policy(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_policy_row: dict,
    ) -> None:
        """Test getting a team policy by ID."""
        mock_conn.fetchrow.return_value = sample_policy_row

        policy = await repo.get_policy(sample_policy_row["id"])

        assert isinstance(policy, TeamPolicy)
        assert policy.id == sample_policy_row["id"]
        mock_conn.fetchrow.assert_called_once()

    async def test_get_policy_not_found(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test getting a non-existent policy returns None."""
        mock_conn.fetchrow.return_value = None

        policy = await repo.get_policy(uuid.uuid4())

        assert policy is None

    async def test_get_policy_by_team(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_policy_row: dict,
    ) -> None:
        """Test getting policy by team ID."""
        mock_conn.fetchrow.return_value = sample_policy_row

        policy = await repo.get_policy_by_team(sample_policy_row["team_id"])

        assert isinstance(policy, TeamPolicy)
        assert policy.team_id == sample_policy_row["team_id"]

    async def test_list_policies(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_policy_row: dict,
    ) -> None:
        """Test listing policies for an organization."""
        mock_conn.fetch.return_value = [sample_policy_row]

        policies = await repo.list_policies(sample_policy_row["org_id"])

        assert len(policies) == 1
        assert isinstance(policies[0], TeamPolicy)

    async def test_update_policy(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_policy_row: dict,
    ) -> None:
        """Test updating a team policy."""
        updated_row = {**sample_policy_row, "default_action": "review"}
        mock_conn.fetchrow.return_value = updated_row

        policy = await repo.update_policy(
            sample_policy_row["id"],
            default_action=PolicyAction.REVIEW,
        )

        assert policy is not None
        assert policy.default_action == PolicyAction.REVIEW

    async def test_update_policy_no_changes(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_policy_row: dict,
    ) -> None:
        """Test updating a policy with no changes returns existing policy."""
        mock_conn.fetchrow.return_value = sample_policy_row

        policy = await repo.update_policy(sample_policy_row["id"])

        assert policy is not None
        # Should call get_policy instead of update
        mock_conn.fetchrow.assert_called_once()

    async def test_delete_policy(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test deleting a team policy."""
        mock_conn.execute.return_value = "DELETE 1"

        result = await repo.delete_policy(uuid.uuid4())

        assert result is True

    async def test_delete_policy_not_found(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test deleting a non-existent policy returns False."""
        mock_conn.execute.return_value = "DELETE 0"

        result = await repo.delete_policy(uuid.uuid4())

        assert result is False

    # =========================================================================
    # Policy Override Tests
    # =========================================================================

    async def test_create_override_with_dataset(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_override_row: dict,
    ) -> None:
        """Test creating an override for a dataset."""
        mock_conn.fetchrow.return_value = sample_override_row

        override = await repo.create_override(
            org_id=sample_override_row["org_id"],
            team_id=sample_override_row["team_id"],
            dataset_id="prod.analytics.orders",
            default_action=PolicyAction.REVIEW,
        )

        assert isinstance(override, TeamPolicyOverride)
        assert override.dataset_id == "prod.analytics.orders"
        assert override.tag_id is None

    async def test_create_override_with_tag(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test creating an override for a tag."""
        tag_id = uuid.uuid4()
        override_row = {
            "id": uuid.uuid4(),
            "org_id": uuid.uuid4(),
            "team_id": uuid.uuid4(),
            "dataset_id": None,
            "tag_id": tag_id,
            "default_action": "issue_only",
            "auto_investigate_min_severity": None,
            "review_required_max_severity": None,
            "is_active": True,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        mock_conn.fetchrow.return_value = override_row

        override = await repo.create_override(
            org_id=override_row["org_id"],
            team_id=override_row["team_id"],
            tag_id=tag_id,
            default_action=PolicyAction.ISSUE_ONLY,
        )

        assert isinstance(override, TeamPolicyOverride)
        assert override.tag_id == tag_id
        assert override.dataset_id is None

    async def test_create_override_requires_one_selector(
        self,
        repo: TeamPolicyRepository,
    ) -> None:
        """Test that exactly one of dataset_id or tag_id must be set."""
        with pytest.raises(ValueError, match="Exactly one"):
            await repo.create_override(
                org_id=uuid.uuid4(),
                team_id=uuid.uuid4(),
                # Neither dataset_id nor tag_id provided
            )

        with pytest.raises(ValueError, match="Exactly one"):
            await repo.create_override(
                org_id=uuid.uuid4(),
                team_id=uuid.uuid4(),
                dataset_id="some.dataset",
                tag_id=uuid.uuid4(),  # Both provided
            )

    async def test_get_override(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_override_row: dict,
    ) -> None:
        """Test getting an override by ID."""
        mock_conn.fetchrow.return_value = sample_override_row

        override = await repo.get_override(sample_override_row["id"])

        assert isinstance(override, TeamPolicyOverride)
        assert override.id == sample_override_row["id"]

    async def test_get_overrides_for_team(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_override_row: dict,
    ) -> None:
        """Test getting all overrides for a team."""
        mock_conn.fetch.return_value = [sample_override_row]

        overrides = await repo.get_overrides_for_team(sample_override_row["team_id"])

        assert len(overrides) == 1
        assert isinstance(overrides[0], TeamPolicyOverride)

    async def test_get_override_for_dataset(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_override_row: dict,
    ) -> None:
        """Test getting override for a specific dataset."""
        mock_conn.fetchrow.return_value = sample_override_row

        override = await repo.get_override_for_dataset(
            team_id=sample_override_row["team_id"],
            dataset_id="prod.analytics.orders",
        )

        assert override is not None
        assert override.dataset_id == "prod.analytics.orders"

    async def test_update_override(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_override_row: dict,
    ) -> None:
        """Test updating a policy override."""
        updated_row = {**sample_override_row, "default_action": "auto"}
        mock_conn.fetchrow.return_value = updated_row

        override = await repo.update_override(
            sample_override_row["id"],
            default_action=PolicyAction.AUTO,
        )

        assert override is not None
        assert override.default_action == PolicyAction.AUTO

    async def test_delete_override(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test deleting a policy override."""
        mock_conn.execute.return_value = "DELETE 1"

        result = await repo.delete_override(uuid.uuid4())

        assert result is True

    # =========================================================================
    # Queue Limits Tests
    # =========================================================================

    async def test_create_queue_limits(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_queue_limits_row: dict,
    ) -> None:
        """Test creating queue limits for a team."""
        mock_conn.fetchrow.return_value = sample_queue_limits_row

        limits = await repo.create_queue_limits(
            org_id=sample_queue_limits_row["org_id"],
            team_id=sample_queue_limits_row["team_id"],
            rate_limit_per_minute=120,
            burst_size=20,
            max_concurrent=10,
        )

        assert isinstance(limits, TeamQueueLimits)
        assert limits.rate_limit_per_minute == 120
        assert limits.burst_size == 20
        assert limits.max_concurrent == 10

    async def test_get_queue_limits(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_queue_limits_row: dict,
    ) -> None:
        """Test getting queue limits for a team."""
        mock_conn.fetchrow.return_value = sample_queue_limits_row

        limits = await repo.get_queue_limits(sample_queue_limits_row["team_id"])

        assert isinstance(limits, TeamQueueLimits)
        assert limits.team_id == sample_queue_limits_row["team_id"]

    async def test_get_queue_limits_not_found(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test getting queue limits when none exist."""
        mock_conn.fetchrow.return_value = None

        limits = await repo.get_queue_limits(uuid.uuid4())

        assert limits is None

    async def test_update_queue_limits(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
        sample_queue_limits_row: dict,
    ) -> None:
        """Test updating queue limits."""
        updated_row = {**sample_queue_limits_row, "rate_limit_per_minute": 200}
        mock_conn.fetchrow.return_value = updated_row

        limits = await repo.update_queue_limits(
            team_id=sample_queue_limits_row["team_id"],
            rate_limit_per_minute=200,
        )

        assert limits is not None
        assert limits.rate_limit_per_minute == 200

    # =========================================================================
    # Dataset Tags Tests
    # =========================================================================

    async def test_add_dataset_tag(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test adding a tag to a dataset."""
        mock_conn.execute.return_value = "INSERT 0 1"

        dataset_id = uuid.uuid4()
        tag_id = uuid.uuid4()

        await repo.add_dataset_tag(dataset_id, tag_id)

        mock_conn.execute.assert_called_once()

    async def test_remove_dataset_tag(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test removing a tag from a dataset."""
        mock_conn.execute.return_value = "DELETE 1"

        result = await repo.remove_dataset_tag(uuid.uuid4(), uuid.uuid4())

        assert result is True

    async def test_remove_dataset_tag_not_found(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test removing a non-existent tag returns False."""
        mock_conn.execute.return_value = "DELETE 0"

        result = await repo.remove_dataset_tag(uuid.uuid4(), uuid.uuid4())

        assert result is False

    async def test_get_dataset_tags(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test getting all tags for a dataset."""
        tag1 = uuid.uuid4()
        tag2 = uuid.uuid4()
        mock_conn.fetch.return_value = [{"tag_id": tag1}, {"tag_id": tag2}]

        tags = await repo.get_dataset_tags(uuid.uuid4())

        assert len(tags) == 2
        assert tag1 in tags
        assert tag2 in tags

    async def test_get_datasets_by_tag(
        self,
        repo: TeamPolicyRepository,
        mock_conn: AsyncMock,
    ) -> None:
        """Test getting all datasets with a specific tag."""
        ds1 = uuid.uuid4()
        ds2 = uuid.uuid4()
        mock_conn.fetch.return_value = [{"dataset_id": ds1}, {"dataset_id": ds2}]

        datasets = await repo.get_datasets_by_tag(uuid.uuid4())

        assert len(datasets) == 2
        assert ds1 in datasets
        assert ds2 in datasets


class TestPolicyAction:
    """Tests for PolicyAction enum."""

    def test_policy_action_values(self) -> None:
        """Test PolicyAction enum has expected values."""
        assert PolicyAction.AUTO.value == "auto"
        assert PolicyAction.REVIEW.value == "review"
        assert PolicyAction.ISSUE_ONLY.value == "issue_only"

    def test_policy_action_from_string(self) -> None:
        """Test creating PolicyAction from string value."""
        assert PolicyAction("auto") == PolicyAction.AUTO
        assert PolicyAction("review") == PolicyAction.REVIEW
        assert PolicyAction("issue_only") == PolicyAction.ISSUE_ONLY
