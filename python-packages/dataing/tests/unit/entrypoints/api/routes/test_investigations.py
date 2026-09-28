"""Unit tests for investigations routes."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.entrypoints.api.middleware.auth import ApiKeyContext


@pytest.fixture
def mock_auth_context() -> ApiKeyContext:
    """Return a mock auth context."""
    return ApiKeyContext(
        key_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        tenant_slug="test-tenant",
        tenant_name="Test Tenant",
        user_id=uuid.uuid4(),
        scopes=["read", "write"],
    )


@pytest.fixture
def sample_alert() -> dict[str, Any]:
    """Return a sample alert dict for requests."""
    return {
        "dataset_ids": ["analytics.events"],
        "metric_spec": {
            "metric_type": "column",
            "expression": "user_id",
            "display_name": "NULL rate",
            "columns_referenced": ["user_id"],
        },
        "anomaly_type": "null_rate",
        "expected_value": 0.01,
        "actual_value": 0.15,
        "deviation_pct": 1400.0,
        "anomaly_date": "2026-01-10",
        "severity": "high",
    }


class TestStartInvestigationRoute:
    """Tests for POST /investigations."""

    def test_request_model_validation(self, sample_alert: dict[str, Any]) -> None:
        """Test that the request model validates correctly."""
        from dataing.entrypoints.api.routes.investigations import (
            StartInvestigationRequest,
        )

        request = StartInvestigationRequest(alert=sample_alert)
        assert request.alert is not None
        assert request.alert.dataset_ids == ["analytics.events"]
        assert request.alert.anomaly_type == "null_rate"
        assert (request.execution_profile, request.issue_id) == ("standard", None)

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({}, id="neither"),
            pytest.param({"brief": {"symptom": "Orders dropped"}, "alert": None}, id="brief-only"),
        ],
    )
    def test_request_needs_exactly_one_of_brief_and_alert(
        self, body: dict[str, Any], sample_alert: dict[str, Any]
    ) -> None:
        """A run starts from a brief or from an alert, never both or neither."""
        from pydantic import ValidationError

        from dataing.entrypoints.api.routes.investigations import StartInvestigationRequest

        if "brief" in body:
            assert StartInvestigationRequest.model_validate(body).brief is not None
            with pytest.raises(ValidationError):
                StartInvestigationRequest.model_validate({**body, "alert": sample_alert})
        else:
            with pytest.raises(ValidationError):
                StartInvestigationRequest.model_validate(body)

    def test_response_model(self) -> None:
        """Test response model structure."""
        from dataing.entrypoints.api.routes.investigations import (
            StartInvestigationResponse,
        )

        investigation_id = uuid.uuid4()
        branch_id = uuid.uuid4()

        issue_id = uuid.uuid4()
        response = StartInvestigationResponse(
            investigation_id=investigation_id,
            main_branch_id=branch_id,
            run_id=uuid.uuid4(),
            issue_id=issue_id,
            issue_number=42,
        )

        assert response.investigation_id == investigation_id
        assert response.main_branch_id == branch_id
        assert (response.issue_id, response.issue_number, response.status) == (
            issue_id,
            42,
            "queued",
        )


class TestGetInvestigationRoute:
    """Tests for GET /investigations/{investigation_id}."""

    def test_response_model_with_main_branch(self) -> None:
        """Test response model with main branch only."""
        from dataing.entrypoints.api.routes.investigations import (
            BranchStateResponse,
            InvestigationStateResponse,
        )

        investigation_id = uuid.uuid4()
        branch_id = uuid.uuid4()

        response = InvestigationStateResponse(
            investigation_id=investigation_id,
            status="active",
            main_branch=BranchStateResponse(
                branch_id=branch_id,
                status="active",
                current_step="gather_context",
                synthesis=None,
                evidence=[],
            ),
            user_branch=None,
        )

        assert response.investigation_id == investigation_id
        assert response.status == "active"
        assert response.main_branch.branch_id == branch_id
        assert response.user_branch is None

    def test_response_model_with_user_branch(self) -> None:
        """Test response model with both main and user branches."""
        from dataing.entrypoints.api.routes.investigations import (
            BranchStateResponse,
            InvestigationStateResponse,
        )

        investigation_id = uuid.uuid4()
        main_branch_id = uuid.uuid4()
        user_branch_id = uuid.uuid4()

        response = InvestigationStateResponse(
            investigation_id=investigation_id,
            status="active",
            main_branch=BranchStateResponse(
                branch_id=main_branch_id,
                status="active",
                current_step="synthesize",
                synthesis={"root_cause": "Test", "confidence": 0.9},
                evidence=[{"hypothesis_id": "h1", "supports": True}],
            ),
            user_branch=BranchStateResponse(
                branch_id=user_branch_id,
                status="suspended",
                current_step="await_user",
                synthesis=None,
                evidence=[],
            ),
        )

        assert response.main_branch.synthesis["root_cause"] == "Test"
        assert response.user_branch is not None
        assert response.user_branch.status == "suspended"


class TestStreamUpdatesRoute:
    """Tests for GET /investigations/{investigation_id}/stream."""

    def test_sse_response_format(self) -> None:
        """Test that SSE events have correct format."""
        # SSE events should be formatted as "data: {json}\n\n"
        event_data = {"type": "step_started", "step": "gather_context"}
        formatted = f"data: {event_data}\n\n"
        assert formatted.startswith("data:")
        assert formatted.endswith("\n\n")


class TestBranchStateResponse:
    """Tests for BranchStateResponse model."""

    def test_branch_state_with_synthesis(self) -> None:
        """Test branch state with synthesis data."""
        from dataing.entrypoints.api.routes.investigations import (
            BranchStateResponse,
        )

        branch_id = uuid.uuid4()
        response = BranchStateResponse(
            branch_id=branch_id,
            status="completed",
            current_step="complete",
            synthesis={
                "root_cause": "ETL job failed",
                "confidence": 0.95,
                "recommendations": ["Check job logs", "Verify source data"],
            },
            evidence=[
                {
                    "hypothesis_id": "h1",
                    "query": "SELECT COUNT(*) FROM events",
                    "supports_hypothesis": True,
                }
            ],
        )

        assert response.synthesis is not None
        assert response.synthesis["confidence"] == 0.95
        assert len(response.evidence) == 1

    def test_branch_state_minimal(self) -> None:
        """Test branch state with minimal data."""
        from dataing.entrypoints.api.routes.investigations import (
            BranchStateResponse,
        )

        branch_id = uuid.uuid4()
        response = BranchStateResponse(
            branch_id=branch_id,
            status="active",
            current_step="gather_context",
        )

        assert response.synthesis is None
        assert response.evidence == []


class TestChainVerificationResponse:
    """Tests for ChainVerificationResponse model."""

    def test_valid_chain_response(self) -> None:
        """Test response for a valid chain."""
        from dataing.entrypoints.api.routes.investigations import (
            ChainVerificationResponse,
        )

        investigation_id = uuid.uuid4()
        response = ChainVerificationResponse(
            investigation_id=investigation_id,
            is_valid=True,
            evidence_count=5,
            root_hash="a" * 64,
            root_hash_matches=True,
            chain_available=True,
        )
        assert response.is_valid is True
        assert response.evidence_count == 5
        assert response.root_hash_matches is True
        assert response.chain_available is True
        assert response.first_broken_seq is None
        assert response.error is None

    def test_broken_chain_response(self) -> None:
        """Test response for a broken chain."""
        from dataing.entrypoints.api.routes.investigations import (
            ChainVerificationResponse,
        )

        investigation_id = uuid.uuid4()
        response = ChainVerificationResponse(
            investigation_id=investigation_id,
            is_valid=False,
            evidence_count=3,
            root_hash="b" * 64,
            root_hash_matches=False,
            first_broken_seq=2,
            error="Item seq=2 content_hash mismatch",
            chain_available=True,
        )
        assert response.is_valid is False
        assert response.first_broken_seq == 2
        assert "content_hash mismatch" in response.error

    def test_no_evidence_response(self) -> None:
        """Test response when no evidence exists."""
        from dataing.entrypoints.api.routes.investigations import (
            ChainVerificationResponse,
        )

        investigation_id = uuid.uuid4()
        response = ChainVerificationResponse(
            investigation_id=investigation_id,
            is_valid=True,
            evidence_count=0,
            chain_available=False,
        )
        assert response.is_valid is True
        assert response.evidence_count == 0
        assert response.chain_available is False

    def test_pre_feature_investigation(self) -> None:
        """Test response for investigation without hash chain data."""
        from dataing.entrypoints.api.routes.investigations import (
            ChainVerificationResponse,
        )

        investigation_id = uuid.uuid4()
        response = ChainVerificationResponse(
            investigation_id=investigation_id,
            is_valid=True,
            evidence_count=10,
            chain_available=False,
        )
        assert response.chain_available is False
        assert response.root_hash_matches is None


class TestRouterConfiguration:
    """Tests for router configuration."""

    def test_router_prefix(self) -> None:
        """Test that router has correct prefix."""
        from dataing.entrypoints.api.routes.investigations import router

        assert router.prefix == "/investigations"

    def test_router_tags(self) -> None:
        """Test that router has correct tags."""
        from dataing.entrypoints.api.routes.investigations import router

        assert "investigations" in router.tags


class TestStartInvestigationRequestParsing:
    """POST /investigations parses an SDK alert into an AnomalyAlert."""

    @pytest.mark.asyncio
    async def test_start_investigation_parses_alert(
        self,
        mock_auth_context: ApiKeyContext,
        sample_alert: dict[str, Any],
    ) -> None:
        """Test that start_investigation request parses alert correctly."""
        from dataing.entrypoints.api.routes.investigations import (
            StartInvestigationRequest,
        )

        request = StartInvestigationRequest(alert=sample_alert)

        alert = request.alert
        assert isinstance(alert, AnomalyAlert)
        assert alert.dataset_id == "analytics.events"
        assert alert.metric_spec == MetricSpec(
            metric_type="column",
            expression="user_id",
            display_name="NULL rate",
            columns_referenced=["user_id"],
        )


class TestSnapshotModels:
    """Tests for snapshot-related models."""

    def test_snapshot_checkpoint_param_values(self) -> None:
        """Test that all checkpoint values are valid."""
        from dataing.entrypoints.api.routes.investigations import (
            SnapshotCheckpointParam,
        )

        assert SnapshotCheckpointParam.START.value == "start"
        assert SnapshotCheckpointParam.HYPOTHESIS_GENERATED.value == "hypothesis_generated"
        assert SnapshotCheckpointParam.EVIDENCE_COLLECTED.value == "evidence_collected"
        assert SnapshotCheckpointParam.COMPLETE.value == "complete"
        assert SnapshotCheckpointParam.FAILED.value == "failed"

    def test_snapshot_list_item_model(self) -> None:
        """Test SnapshotListItem model."""
        from dataing.entrypoints.api.routes.investigations import SnapshotListItem

        item = SnapshotListItem(
            checkpoint="complete",
            captured_at="2026-01-28T10:00:00Z",
            storage_path="/snapshots/tenant/investigation/complete.snapshot",
            size_bytes=1024,
        )
        assert item.checkpoint == "complete"
        assert item.size_bytes == 1024

    def test_snapshot_list_item_optional_size(self) -> None:
        """Test SnapshotListItem with optional size_bytes."""
        from dataing.entrypoints.api.routes.investigations import SnapshotListItem

        item = SnapshotListItem(
            checkpoint="start",
            captured_at="",
            storage_path="/path/to/snapshot",
        )
        assert item.size_bytes is None

    def test_snapshot_list_response_model(self) -> None:
        """Test SnapshotListResponse model."""
        from dataing.entrypoints.api.routes.investigations import (
            SnapshotListItem,
            SnapshotListResponse,
        )

        investigation_id = uuid.uuid4()
        response = SnapshotListResponse(
            investigation_id=investigation_id,
            snapshots=[
                SnapshotListItem(
                    checkpoint="start",
                    captured_at="",
                    storage_path="/path/start.snapshot",
                ),
                SnapshotListItem(
                    checkpoint="complete",
                    captured_at="",
                    storage_path="/path/complete.snapshot",
                ),
            ],
        )
        assert response.investigation_id == investigation_id
        assert len(response.snapshots) == 2

    def test_snapshot_list_response_empty(self) -> None:
        """Test SnapshotListResponse with no snapshots."""
        from dataing.entrypoints.api.routes.investigations import (
            SnapshotListResponse,
        )

        investigation_id = uuid.uuid4()
        response = SnapshotListResponse(
            investigation_id=investigation_id,
            snapshots=[],
        )
        assert len(response.snapshots) == 0
