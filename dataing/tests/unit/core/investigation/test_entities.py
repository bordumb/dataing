"""Tests for investigation domain entities."""

from uuid import uuid4

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.entities import (
    Branch,
    Investigation,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    StepType,
    VersionId,
)


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create a sample anomaly alert for testing."""
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
    """Create a sample investigation context."""
    return InvestigationContext(
        alert_summary="NULL rate anomaly in analytics.events",
        schema_info={"tables": ["events"], "columns": ["user_id", "event_type"]},
    )


class TestInvestigation:
    """Tests for Investigation entity."""

    def test_create_investigation(self, sample_alert: AnomalyAlert) -> None:
        """Can create investigation with alert."""
        tenant_id = uuid4()
        inv = Investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
        )
        assert inv.id is not None
        assert inv.tenant_id == tenant_id
        assert inv.alert == sample_alert
        assert inv.main_branch_id is None
        assert inv.outcome is None

    def test_investigation_is_active_when_no_outcome(self, sample_alert: AnomalyAlert) -> None:
        """Investigation is active when outcome is None."""
        inv = Investigation(tenant_id=uuid4(), alert=sample_alert)
        assert inv.is_active is True

    def test_investigation_is_not_active_when_outcome_set(self, sample_alert: AnomalyAlert) -> None:
        """Investigation is not active when outcome is set."""
        inv = Investigation(
            tenant_id=uuid4(),
            alert=sample_alert,
            outcome={"root_cause": "ETL failure", "confidence": 0.9},
        )
        assert inv.is_active is False


class TestBranch:
    """Tests for Branch entity."""

    def test_create_main_branch(self) -> None:
        """Can create a main branch."""
        inv_id = uuid4()
        branch = Branch(
            investigation_id=inv_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        assert branch.id is not None
        assert branch.investigation_id == inv_id
        assert branch.branch_type == BranchType.MAIN
        assert branch.status == BranchStatus.ACTIVE
        assert branch.parent_branch_id is None
        assert branch.owner_user_id is None

    def test_create_user_branch(self) -> None:
        """Can create a user branch with owner."""
        inv_id = uuid4()
        parent_id = uuid4()
        user_id = uuid4()
        branch = Branch(
            investigation_id=inv_id,
            branch_type=BranchType.USER,
            name="alice_exploration",
            parent_branch_id=parent_id,
            owner_user_id=user_id,
        )
        assert branch.branch_type == BranchType.USER
        assert branch.parent_branch_id == parent_id
        assert branch.owner_user_id == user_id

    def test_branch_can_accept_input(self) -> None:
        """Branch can accept input when suspended or completed."""
        branch = Branch(
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="test",
            status=BranchStatus.SUSPENDED,
        )
        assert branch.can_accept_input is True

        branch_completed = Branch(
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="test",
            status=BranchStatus.COMPLETED,
        )
        assert branch_completed.can_accept_input is True

        branch_active = Branch(
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="test",
            status=BranchStatus.ACTIVE,
        )
        assert branch_active.can_accept_input is False


class TestSnapshot:
    """Tests for Snapshot entity."""

    def test_create_snapshot(self, sample_context: InvestigationContext) -> None:
        """Can create a snapshot with context."""
        inv_id = uuid4()
        branch_id = uuid4()
        snapshot = Snapshot(
            investigation_id=inv_id,
            branch_id=branch_id,
            version=VersionId(major=1, minor=0, patch=0),
            step=StepType.GATHER_CONTEXT,
            context=sample_context,
        )
        assert snapshot.id is not None
        assert snapshot.investigation_id == inv_id
        assert snapshot.branch_id == branch_id
        assert snapshot.version.major == 1
        assert snapshot.step == StepType.GATHER_CONTEXT
        assert snapshot.parent_snapshot_id is None
        assert snapshot.trigger == "system"

    def test_snapshot_with_parent(self, sample_context: InvestigationContext) -> None:
        """Snapshot can reference parent snapshot."""
        parent_id = uuid4()
        snapshot = Snapshot(
            investigation_id=uuid4(),
            branch_id=uuid4(),
            version=VersionId(major=1, minor=0, patch=1),
            step=StepType.GENERATE_HYPOTHESES,
            context=sample_context,
            parent_snapshot_id=parent_id,
        )
        assert snapshot.parent_snapshot_id == parent_id

    def test_snapshot_is_terminal(self, sample_context: InvestigationContext) -> None:
        """Snapshot is terminal when step is COMPLETE or FAIL."""
        complete_snapshot = Snapshot(
            investigation_id=uuid4(),
            branch_id=uuid4(),
            version=VersionId(),
            step=StepType.COMPLETE,
            context=sample_context,
        )
        assert complete_snapshot.is_terminal is True

        fail_snapshot = Snapshot(
            investigation_id=uuid4(),
            branch_id=uuid4(),
            version=VersionId(),
            step=StepType.FAIL,
            context=sample_context,
        )
        assert fail_snapshot.is_terminal is True

        active_snapshot = Snapshot(
            investigation_id=uuid4(),
            branch_id=uuid4(),
            version=VersionId(),
            step=StepType.SYNTHESIZE,
            context=sample_context,
        )
        assert active_snapshot.is_terminal is False


class TestInvestigationContext:
    """Tests for InvestigationContext value object."""

    def test_create_minimal_context(self) -> None:
        """Can create context with minimal fields."""
        ctx = InvestigationContext(alert_summary="Test anomaly")
        assert ctx.alert_summary == "Test anomaly"
        assert ctx.schema_info is None
        assert ctx.hypotheses == []
        assert ctx.evidence == []

    def test_context_with_all_fields(self) -> None:
        """Can create context with all fields populated."""
        ctx = InvestigationContext(
            alert_summary="NULL rate spike",
            schema_info={"tables": ["events"]},
            lineage_info={"upstream": ["raw.events"]},
            hypotheses=[{"id": "h1", "title": "ETL bug"}],
            evidence=[{"hypothesis_id": "h1", "supports": True}],
            current_synthesis={"root_cause": "ETL bug", "confidence": 0.85},
            total_tokens_used=1500,
            total_queries_executed=3,
        )
        assert ctx.schema_info == {"tables": ["events"]}
        assert len(ctx.hypotheses) == 1
        assert ctx.total_tokens_used == 1500
