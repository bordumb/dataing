"""Unit tests for PolicyService."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from dataing.adapters.db.team_policy_repository import (
    PolicyAction,
    TeamPolicy,
    TeamPolicyOverride,
    TeamQueueLimits,
)
from dataing.services.policy import (
    IssueContext,
    PolicyResult,
    PolicyService,
    QueueConfig,
    evaluate_policy_for_issue,
)


class TestQueueConfig:
    """Tests for QueueConfig."""

    def test_defaults(self) -> None:
        """Test QueueConfig default values."""
        config = QueueConfig()
        assert config.rate_limit_per_minute == 60
        assert config.burst_size == 10
        assert config.max_concurrent == 5
        assert config.batch_size == 5

    def test_from_limits(self) -> None:
        """Test creating QueueConfig from TeamQueueLimits."""
        limits = TeamQueueLimits(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            team_id=uuid.uuid4(),
            rate_limit_per_minute=120,
            burst_size=20,
            max_concurrent=10,
            batch_size=8,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        config = QueueConfig.from_limits(limits)

        assert config.rate_limit_per_minute == 120
        assert config.burst_size == 20
        assert config.max_concurrent == 10
        assert config.batch_size == 8

    def test_from_limits_none(self) -> None:
        """Test creating QueueConfig from None returns defaults."""
        config = QueueConfig.from_limits(None)
        assert config.rate_limit_per_minute == 60
        assert config.burst_size == 10


class TestPolicyService:
    """Tests for PolicyService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database."""
        return AsyncMock()

    @pytest.fixture
    def mock_repo(self) -> AsyncMock:
        """Return a mock TeamPolicyRepository."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock, mock_repo: AsyncMock) -> PolicyService:
        """Return a PolicyService with mocked repository."""
        svc = PolicyService(mock_db)
        svc.repo = mock_repo
        return svc

    @pytest.fixture
    def team_id(self) -> uuid.UUID:
        """Return a team ID for testing."""
        return uuid.uuid4()

    @pytest.fixture
    def sample_policy(self, team_id: uuid.UUID) -> TeamPolicy:
        """Return a sample team policy."""
        return TeamPolicy(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            team_id=team_id,
            sources=["dbt", "airflow"],
            default_action=PolicyAction.REVIEW,
            auto_investigate_min_severity="high",
            review_required_max_severity="medium",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_queue_limits(self, team_id: uuid.UUID) -> TeamQueueLimits:
        """Return sample queue limits."""
        return TeamQueueLimits(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            team_id=team_id,
            rate_limit_per_minute=100,
            burst_size=15,
            max_concurrent=8,
            batch_size=5,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    # =========================================================================
    # Team Default Policy Tests
    # =========================================================================

    async def test_evaluate_team_default_policy(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
        sample_policy: TeamPolicy,
        sample_queue_limits: TeamQueueLimits,
    ) -> None:
        """Test evaluation returns team default policy when no overrides match."""
        mock_repo.get_policy_by_team.return_value = sample_policy
        mock_repo.get_queue_limits.return_value = sample_queue_limits
        mock_repo.get_override_for_dataset.return_value = None
        mock_repo.get_overrides_for_team.return_value = []

        context = IssueContext(team_id=team_id, source="dbt")
        result = await service.evaluate(context)

        assert result.action == PolicyAction.REVIEW
        assert result.source == "team_default"
        assert result.policy_id == sample_policy.id
        assert result.queue_config.rate_limit_per_minute == 100

    async def test_evaluate_no_policy_returns_defaults(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
    ) -> None:
        """Test evaluation returns system defaults when no policy exists."""
        mock_repo.get_policy_by_team.return_value = None
        mock_repo.get_queue_limits.return_value = None

        context = IssueContext(team_id=team_id)
        result = await service.evaluate(context)

        assert result.action == PolicyAction.ISSUE_ONLY
        assert result.source == "system_default"
        assert result.queue_config.rate_limit_per_minute == 60

    async def test_evaluate_source_mismatch_returns_defaults(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
        sample_policy: TeamPolicy,
    ) -> None:
        """Test that source mismatch returns defaults."""
        mock_repo.get_policy_by_team.return_value = sample_policy
        mock_repo.get_queue_limits.return_value = None

        # Policy requires "dbt" or "airflow", but issue is from "snowflake"
        context = IssueContext(team_id=team_id, source="snowflake")
        result = await service.evaluate(context)

        assert result.action == PolicyAction.ISSUE_ONLY
        assert result.source == "system_default"

    # =========================================================================
    # Dataset Override Tests
    # =========================================================================

    async def test_evaluate_dataset_override(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
        sample_policy: TeamPolicy,
        sample_queue_limits: TeamQueueLimits,
    ) -> None:
        """Test that dataset override takes precedence over team default."""
        override = TeamPolicyOverride(
            id=uuid.uuid4(),
            org_id=sample_policy.org_id,
            team_id=team_id,
            dataset_id="prod.analytics.orders",
            tag_id=None,
            default_action=PolicyAction.AUTO,
            auto_investigate_min_severity=None,
            review_required_max_severity=None,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_repo.get_policy_by_team.return_value = sample_policy
        mock_repo.get_queue_limits.return_value = sample_queue_limits
        mock_repo.get_override_for_dataset.return_value = override

        context = IssueContext(
            team_id=team_id,
            dataset_id="prod.analytics.orders",
            source="dbt",
        )
        result = await service.evaluate(context)

        assert result.action == PolicyAction.AUTO
        assert result.source == "dataset_override"
        assert result.override_id == override.id

    async def test_evaluate_dataset_override_inherits_severity(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
        sample_policy: TeamPolicy,
    ) -> None:
        """Test that dataset override inherits severity settings from policy."""
        override = TeamPolicyOverride(
            id=uuid.uuid4(),
            org_id=sample_policy.org_id,
            team_id=team_id,
            dataset_id="prod.analytics.orders",
            tag_id=None,
            default_action=None,  # Inherit from policy
            auto_investigate_min_severity=None,  # Inherit from policy
            review_required_max_severity=None,  # Inherit from policy
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_repo.get_policy_by_team.return_value = sample_policy
        mock_repo.get_queue_limits.return_value = None
        mock_repo.get_override_for_dataset.return_value = override

        context = IssueContext(
            team_id=team_id,
            dataset_id="prod.analytics.orders",
            source="dbt",
        )
        result = await service.evaluate(context)

        assert result.action == sample_policy.default_action
        assert result.auto_investigate_min_severity == sample_policy.auto_investigate_min_severity

    # =========================================================================
    # Tag Override Tests
    # =========================================================================

    async def test_evaluate_tag_override(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
        sample_policy: TeamPolicy,
    ) -> None:
        """Test that tag override is applied when tag matches."""
        tag_id = uuid.uuid4()
        override = TeamPolicyOverride(
            id=uuid.uuid4(),
            org_id=sample_policy.org_id,
            team_id=team_id,
            dataset_id=None,
            tag_id=tag_id,
            default_action=PolicyAction.ISSUE_ONLY,
            auto_investigate_min_severity=None,
            review_required_max_severity=None,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_repo.get_policy_by_team.return_value = sample_policy
        mock_repo.get_queue_limits.return_value = None
        mock_repo.get_override_for_dataset.return_value = None
        mock_repo.get_overrides_for_team.return_value = [override]

        context = IssueContext(
            team_id=team_id,
            tag_ids=[tag_id],
            source="dbt",
        )
        result = await service.evaluate(context)

        assert result.action == PolicyAction.ISSUE_ONLY
        assert result.source == "tag_override"
        assert result.override_id == override.id
        assert tag_id in result.matched_tags

    async def test_evaluate_dataset_override_beats_tag_override(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
        sample_policy: TeamPolicy,
    ) -> None:
        """Test that dataset override takes precedence over tag override."""
        tag_id = uuid.uuid4()
        tag_override = TeamPolicyOverride(
            id=uuid.uuid4(),
            org_id=sample_policy.org_id,
            team_id=team_id,
            dataset_id=None,
            tag_id=tag_id,
            default_action=PolicyAction.ISSUE_ONLY,
            auto_investigate_min_severity=None,
            review_required_max_severity=None,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        dataset_override = TeamPolicyOverride(
            id=uuid.uuid4(),
            org_id=sample_policy.org_id,
            team_id=team_id,
            dataset_id="prod.analytics.orders",
            tag_id=None,
            default_action=PolicyAction.AUTO,
            auto_investigate_min_severity=None,
            review_required_max_severity=None,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_repo.get_policy_by_team.return_value = sample_policy
        mock_repo.get_queue_limits.return_value = None
        mock_repo.get_override_for_dataset.return_value = dataset_override
        mock_repo.get_overrides_for_team.return_value = [tag_override]

        context = IssueContext(
            team_id=team_id,
            dataset_id="prod.analytics.orders",
            tag_ids=[tag_id],
            source="dbt",
        )
        result = await service.evaluate(context)

        # Dataset override should win
        assert result.action == PolicyAction.AUTO
        assert result.source == "dataset_override"

    # =========================================================================
    # Severity-Based Action Tests
    # =========================================================================

    async def test_evaluate_severity_triggers_auto(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
        sample_policy: TeamPolicy,
    ) -> None:
        """Test that high severity triggers auto investigation."""
        mock_repo.get_policy_by_team.return_value = sample_policy
        mock_repo.get_queue_limits.return_value = None
        mock_repo.get_override_for_dataset.return_value = None
        mock_repo.get_overrides_for_team.return_value = []

        context = IssueContext(
            team_id=team_id,
            severity="critical",  # Above "high" threshold
            source="dbt",
        )
        result = await service.evaluate(context)

        assert result.action == PolicyAction.AUTO

    async def test_evaluate_severity_requires_review(
        self,
        service: PolicyService,
        mock_repo: AsyncMock,
        team_id: uuid.UUID,
        sample_policy: TeamPolicy,
    ) -> None:
        """Test that low severity requires review."""
        mock_repo.get_policy_by_team.return_value = sample_policy
        mock_repo.get_queue_limits.return_value = None
        mock_repo.get_override_for_dataset.return_value = None
        mock_repo.get_overrides_for_team.return_value = []

        context = IssueContext(
            team_id=team_id,
            severity="low",  # Below "medium" threshold
            source="dbt",
        )
        result = await service.evaluate(context)

        assert result.action == PolicyAction.REVIEW

    # =========================================================================
    # Helper Method Tests
    # =========================================================================

    def test_resolve_action_for_severity_auto(self, service: PolicyService) -> None:
        """Test severity resolution for auto investigation."""
        action = service._resolve_action_for_severity(
            default_action=PolicyAction.ISSUE_ONLY,
            severity="high",
            auto_investigate_min_severity="high",
            review_required_max_severity=None,
        )
        assert action == PolicyAction.AUTO

    def test_resolve_action_for_severity_review(self, service: PolicyService) -> None:
        """Test severity resolution for review."""
        action = service._resolve_action_for_severity(
            default_action=PolicyAction.ISSUE_ONLY,
            severity="low",
            auto_investigate_min_severity=None,
            review_required_max_severity="medium",
        )
        assert action == PolicyAction.REVIEW

    def test_resolve_action_for_severity_default(self, service: PolicyService) -> None:
        """Test severity resolution returns default when no thresholds match."""
        action = service._resolve_action_for_severity(
            default_action=PolicyAction.ISSUE_ONLY,
            severity="medium",
            auto_investigate_min_severity="critical",
            review_required_max_severity="low",
        )
        assert action == PolicyAction.ISSUE_ONLY

    def test_resolve_action_for_severity_unknown(self, service: PolicyService) -> None:
        """Test severity resolution with unknown severity returns default."""
        action = service._resolve_action_for_severity(
            default_action=PolicyAction.REVIEW,
            severity="unknown",
            auto_investigate_min_severity="high",
            review_required_max_severity="medium",
        )
        assert action == PolicyAction.REVIEW


class TestEvaluatePolicyForIssue:
    """Tests for the convenience function."""

    async def test_evaluate_policy_for_issue(self) -> None:
        """Test the convenience function creates service and evaluates."""
        mock_db = AsyncMock()
        team_id = uuid.uuid4()

        with patch("dataing.services.policy.PolicyService") as MockService:
            mock_service = MockService.return_value
            # Use AsyncMock for async method
            mock_service.evaluate = AsyncMock(
                return_value=PolicyResult(
                    action=PolicyAction.AUTO,
                    queue_config=QueueConfig(),
                    source="team_default",
                    team_id=team_id,
                )
            )

            result = await evaluate_policy_for_issue(
                db=mock_db,
                team_id=team_id,
                dataset_id="test.dataset",
                severity="high",
            )

            assert result.action == PolicyAction.AUTO
            mock_service.evaluate.assert_called_once()


class TestIssueContext:
    """Tests for IssueContext."""

    def test_issue_context_defaults(self) -> None:
        """Test IssueContext default values."""
        team_id = uuid.uuid4()
        context = IssueContext(team_id=team_id)

        assert context.team_id == team_id
        assert context.dataset_id is None
        assert context.tag_ids == []
        assert context.severity is None
        assert context.source is None

    def test_issue_context_full(self) -> None:
        """Test IssueContext with all fields."""
        team_id = uuid.uuid4()
        tag1 = uuid.uuid4()
        tag2 = uuid.uuid4()

        context = IssueContext(
            team_id=team_id,
            dataset_id="prod.orders",
            tag_ids=[tag1, tag2],
            severity="high",
            source="dbt",
        )

        assert context.team_id == team_id
        assert context.dataset_id == "prod.orders"
        assert len(context.tag_ids) == 2
        assert context.severity == "high"
        assert context.source == "dbt"
