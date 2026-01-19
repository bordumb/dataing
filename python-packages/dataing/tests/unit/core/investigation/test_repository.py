"""Tests for investigation repository."""

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.repository import InvestigationRepository


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create sample alert."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec.from_column("user_id", "NULL rate"),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        anomaly_date="2026-01-10",
        severity="high",
    )


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create sample context."""
    return InvestigationContext(alert_summary="Test anomaly")


class TestInvestigationRepositoryProtocol:
    """Tests that verify the repository protocol shape."""

    def test_repository_has_required_methods(self) -> None:
        """Repository protocol defines required methods."""
        # This test verifies the protocol exists and has expected methods
        assert hasattr(InvestigationRepository, "create_investigation")
        assert hasattr(InvestigationRepository, "get_investigation")
        assert hasattr(InvestigationRepository, "create_branch")
        assert hasattr(InvestigationRepository, "get_branch")
        assert hasattr(InvestigationRepository, "update_branch_status")
        assert hasattr(InvestigationRepository, "update_branch_head")
        assert hasattr(InvestigationRepository, "create_snapshot")
        assert hasattr(InvestigationRepository, "get_snapshot")
        assert hasattr(InvestigationRepository, "acquire_lock")
        assert hasattr(InvestigationRepository, "release_lock")
