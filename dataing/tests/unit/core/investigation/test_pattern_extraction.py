"""Tests for PatternExtractionService."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.entities import (
    Branch,
    Investigation,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.pattern_extraction import (
    PatternExtractionService,
    PatternRepositoryProtocol,
)
from dataing.core.investigation.values import BranchStatus, BranchType, StepType


@pytest.fixture
def tenant_id() -> UUID:
    """Create a test tenant ID."""
    return uuid4()


@pytest.fixture
def investigation_id() -> UUID:
    """Create a test investigation ID."""
    return uuid4()


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create sample anomaly alert."""
    return AnomalyAlert(
        dataset_ids=["analytics.events"],
        metric_spec=MetricSpec.from_column("user_id"),
        anomaly_type="null_rate",
        expected_value=1.0,
        actual_value=15.0,
        deviation_pct=1400.0,
        anomaly_date="2025-01-10",
        severity="high",
    )


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create sample investigation context with evidence."""
    return InvestigationContext(
        alert_summary="null_rate anomaly in analytics.events: user_id NULL rate 15%",
        schema_info={"tables": ["events", "users"]},
        lineage_info={"upstream": ["raw.events"]},
        hypotheses=[
            {
                "id": "h1",
                "title": "Mobile SDK bug",
                "reasoning": "Mobile SDK versions < 2.0 send NULL user_id",
            }
        ],
        evidence=[
            {
                "hypothesis_id": "h1",
                "supports_hypothesis": True,
                "confidence": 0.92,
                "interpretation": "95% of NULL user_ids come from mobile app v1.9",
            }
        ],
    )


@pytest.fixture
def high_confidence_outcome() -> dict[str, Any]:
    """Create high-confidence investigation outcome."""
    return {
        "root_cause": "Mobile SDK v1.9 bug causing NULL user_id on first launch",
        "confidence": 0.92,
        "recommendations": [
            "Upgrade mobile SDK to v2.0",
            "Backfill affected events using device_id",
        ],
        "supporting_evidence": ["95% of NULL user_ids come from mobile app v1.9"],
    }


@pytest.fixture
def low_confidence_outcome() -> dict[str, Any]:
    """Create low-confidence investigation outcome."""
    return {
        "root_cause": "Unknown source of NULL user_id values",
        "confidence": 0.65,
        "recommendations": ["Further investigation needed"],
        "supporting_evidence": [],
    }


@pytest.fixture
def sample_investigation(
    investigation_id: UUID,
    tenant_id: UUID,
    sample_alert: AnomalyAlert,
    high_confidence_outcome: dict[str, Any],
) -> Investigation:
    """Create sample completed investigation with high confidence."""
    return Investigation(
        id=investigation_id,
        tenant_id=tenant_id,
        alert=sample_alert,
        main_branch_id=uuid4(),
        outcome=high_confidence_outcome,
    )


@pytest.fixture
def sample_branch(sample_investigation: Investigation) -> Branch:
    """Create sample main branch."""
    # main_branch_id is set in sample_investigation, so this is safe
    assert sample_investigation.main_branch_id is not None
    return Branch(
        id=sample_investigation.main_branch_id,
        investigation_id=sample_investigation.id,
        branch_type=BranchType.MAIN,
        name="main",
        head_snapshot_id=uuid4(),
        status=BranchStatus.COMPLETED,
    )


@pytest.fixture
def sample_snapshot(
    sample_investigation: Investigation,
    sample_branch: Branch,
    sample_context: InvestigationContext,
) -> Snapshot:
    """Create sample final snapshot."""
    # head_snapshot_id is set in sample_branch, so this is safe
    assert sample_branch.head_snapshot_id is not None
    return Snapshot(
        id=sample_branch.head_snapshot_id,
        investigation_id=sample_investigation.id,
        branch_id=sample_branch.id,
        step=StepType.COMPLETE,
        context=sample_context,
    )


@pytest.fixture
def mock_investigation_repository(
    sample_investigation: Investigation,
    sample_branch: Branch,
    sample_snapshot: Snapshot,
) -> AsyncMock:
    """Create mock investigation repository."""
    repo = AsyncMock()
    repo.get_investigation.return_value = sample_investigation
    repo.get_branch.return_value = sample_branch
    repo.get_snapshot.return_value = sample_snapshot
    return repo


@pytest.fixture
def mock_pattern_repository() -> AsyncMock:
    """Create mock pattern repository."""
    repo = AsyncMock(spec=PatternRepositoryProtocol)
    repo.create_pattern.return_value = uuid4()
    return repo


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Create mock LLM client."""
    llm = AsyncMock()
    llm.extract_pattern.return_value = {
        "name": "Mobile SDK NULL User ID",
        "description": "Mobile SDK versions < 2.0 send NULL user_id on first launch",
        "trigger_signals": {
            "anomaly_type": "null_rate",
            "dataset_pattern": "*.events",
            "metric_pattern": "user_id",
        },
        "typical_root_cause": "Mobile app not waiting for auth before tracking events",
        "resolution_steps": [
            "Upgrade mobile SDK to v2.0",
            "Backfill affected events using device_id",
        ],
        "affected_datasets": ["analytics.events"],
        "affected_metrics": ["user_id"],
    }
    return llm


class TestPatternExtractionServiceShouldExtractPattern:
    """Tests for should_extract_pattern method."""

    @pytest.mark.asyncio
    async def test_returns_true_for_high_confidence_completed_investigation(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        investigation_id: UUID,
    ) -> None:
        """Should return True for completed investigation with high confidence."""
        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        result = await service.should_extract_pattern(investigation_id)

        assert result is True
        mock_investigation_repository.get_investigation.assert_called_once_with(investigation_id)

    @pytest.mark.asyncio
    async def test_returns_false_for_investigation_without_outcome(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        sample_investigation: Investigation,
        investigation_id: UUID,
    ) -> None:
        """Should return False for investigation without outcome."""
        # Investigation without outcome (still in progress)
        incomplete_investigation = sample_investigation.model_copy(update={"outcome": None})
        mock_investigation_repository.get_investigation.return_value = incomplete_investigation

        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        result = await service.should_extract_pattern(investigation_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_low_confidence_investigation(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        sample_investigation: Investigation,
        low_confidence_outcome: dict[str, Any],
        investigation_id: UUID,
    ) -> None:
        """Should return False for investigation with confidence below threshold."""
        # Investigation with low confidence
        low_confidence_investigation = sample_investigation.model_copy(
            update={"outcome": low_confidence_outcome}
        )
        mock_investigation_repository.get_investigation.return_value = low_confidence_investigation

        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        result = await service.should_extract_pattern(investigation_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_missing_confidence_in_outcome(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        sample_investigation: Investigation,
        investigation_id: UUID,
    ) -> None:
        """Should return False if outcome has no confidence field."""
        # Outcome without confidence field
        no_confidence_investigation = sample_investigation.model_copy(
            update={"outcome": {"root_cause": "Some cause", "recommendations": []}}
        )
        mock_investigation_repository.get_investigation.return_value = no_confidence_investigation

        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        result = await service.should_extract_pattern(investigation_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_respects_custom_confidence_threshold(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        sample_investigation: Investigation,
        investigation_id: UUID,
    ) -> None:
        """Should respect custom confidence threshold."""
        # Investigation with 0.92 confidence
        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
            confidence_threshold=0.95,  # Higher threshold
        )

        result = await service.should_extract_pattern(investigation_id)

        assert result is False  # 0.92 < 0.95


class TestPatternExtractionServiceExtractPattern:
    """Tests for extract_pattern method."""

    @pytest.mark.asyncio
    async def test_extracts_pattern_from_completed_investigation(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        investigation_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """Should extract pattern using LLM and save to repository."""
        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        result = await service.extract_pattern(investigation_id, tenant_id)

        assert result is not None
        assert "pattern_id" in result
        assert result["name"] == "Mobile SDK NULL User ID"
        assert result["typical_root_cause"] == (
            "Mobile app not waiting for auth before tracking events"
        )

    @pytest.mark.asyncio
    async def test_calls_llm_with_correct_arguments(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        sample_investigation: Investigation,
        sample_snapshot: Snapshot,
        investigation_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """Should call LLM with alert, outcome, and evidence."""
        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        await service.extract_pattern(investigation_id, tenant_id)

        mock_llm.extract_pattern.assert_called_once_with(
            alert=sample_investigation.alert,
            outcome=sample_investigation.outcome,
            evidence=sample_snapshot.context.evidence,
        )

    @pytest.mark.asyncio
    async def test_saves_pattern_to_repository(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        investigation_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """Should save extracted pattern to pattern repository."""
        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        await service.extract_pattern(investigation_id, tenant_id)

        mock_pattern_repository.create_pattern.assert_called_once()
        call_kwargs = mock_pattern_repository.create_pattern.call_args.kwargs
        assert call_kwargs["tenant_id"] == tenant_id
        assert call_kwargs["name"] == "Mobile SDK NULL User ID"
        assert call_kwargs["created_from_investigation_id"] == investigation_id

    @pytest.mark.asyncio
    async def test_returns_none_for_investigation_without_outcome(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        sample_investigation: Investigation,
        investigation_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """Should return None if investigation has no outcome."""
        # Investigation without outcome
        incomplete_investigation = sample_investigation.model_copy(update={"outcome": None})
        mock_investigation_repository.get_investigation.return_value = incomplete_investigation

        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        result = await service.extract_pattern(investigation_id, tenant_id)

        assert result is None
        mock_llm.extract_pattern.assert_not_called()
        mock_pattern_repository.create_pattern.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_empty_affected_fields(
        self,
        mock_investigation_repository: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_llm: AsyncMock,
        investigation_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """Should handle patterns without affected_datasets or affected_metrics."""
        mock_llm.extract_pattern.return_value = {
            "name": "Simple Pattern",
            "description": "A simple pattern without affected fields",
            "trigger_signals": {"anomaly_type": "null_rate"},
            "typical_root_cause": "Unknown cause",
            "resolution_steps": ["Investigate further"],
        }

        service = PatternExtractionService(
            repository=mock_investigation_repository,
            pattern_repository=mock_pattern_repository,
            llm=mock_llm,
        )

        result = await service.extract_pattern(investigation_id, tenant_id)

        assert result is not None
        call_kwargs = mock_pattern_repository.create_pattern.call_args.kwargs
        assert call_kwargs["affected_datasets"] == []
        assert call_kwargs["affected_metrics"] == []


class TestPatternRepositoryProtocol:
    """Tests to verify PatternRepositoryProtocol contract."""

    def test_protocol_defines_create_pattern(self) -> None:
        """Protocol should define create_pattern method."""
        assert hasattr(PatternRepositoryProtocol, "create_pattern")

    def test_protocol_defines_find_matching_patterns(self) -> None:
        """Protocol should define find_matching_patterns method."""
        assert hasattr(PatternRepositoryProtocol, "find_matching_patterns")

    def test_protocol_defines_update_pattern_stats(self) -> None:
        """Protocol should define update_pattern_stats method."""
        assert hasattr(PatternRepositoryProtocol, "update_pattern_stats")
