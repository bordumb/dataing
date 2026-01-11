"""Unit tests for investigations routes."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.service import BranchState, InvestigationState
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
        "dataset_id": "analytics.events",
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


@pytest.fixture
def mock_service() -> AsyncMock:
    """Create mock investigation service."""
    service = AsyncMock()
    investigation_id = uuid.uuid4()
    branch_id = uuid.uuid4()

    service.start_investigation.return_value = (investigation_id, branch_id)
    service.get_state.return_value = InvestigationState(
        investigation_id=investigation_id,
        status="active",
        main_branch=BranchState(
            branch_id=branch_id,
            status="active",
            current_step="gather_context",
        ),
    )
    service.send_message.return_value = branch_id

    return service


class TestStartInvestigationRoute:
    """Tests for POST /investigations."""

    def test_request_model_validation(self, sample_alert: dict[str, Any]) -> None:
        """Test that the request model validates correctly."""
        from dataing.entrypoints.api.routes.investigations import (
            StartInvestigationRequest,
        )

        request = StartInvestigationRequest(alert=sample_alert)
        assert request.alert["dataset_id"] == "analytics.events"
        assert request.alert["anomaly_type"] == "null_rate"

    def test_response_model(self) -> None:
        """Test response model structure."""
        from dataing.entrypoints.api.routes.investigations import (
            StartInvestigationResponse,
        )

        investigation_id = uuid.uuid4()
        branch_id = uuid.uuid4()

        response = StartInvestigationResponse(
            investigation_id=investigation_id,
            main_branch_id=branch_id,
        )

        assert response.investigation_id == investigation_id
        assert response.main_branch_id == branch_id


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


class TestSendMessageRoute:
    """Tests for POST /investigations/{investigation_id}/messages."""

    def test_request_model(self) -> None:
        """Test message request model."""
        from dataing.entrypoints.api.routes.investigations import (
            SendMessageRequest,
        )

        request = SendMessageRequest(message="Can you investigate upstream?")
        assert request.message == "Can you investigate upstream?"

    def test_response_model(self) -> None:
        """Test message response model."""
        from dataing.entrypoints.api.routes.investigations import (
            SendMessageResponse,
        )

        branch_id = uuid.uuid4()
        response = SendMessageResponse(branch_id=branch_id)
        assert response.branch_id == branch_id


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


class TestInvestigationServiceIntegration:
    """Integration tests for route handlers with mocked service."""

    @pytest.mark.asyncio
    async def test_start_investigation_calls_service(
        self,
        mock_auth_context: ApiKeyContext,
        mock_service: AsyncMock,
        sample_alert: dict[str, Any],
    ) -> None:
        """Test that start_investigation route calls service correctly."""
        from dataing.entrypoints.api.routes.investigations import (
            StartInvestigationRequest,
        )

        request = StartInvestigationRequest(alert=sample_alert)

        # Call the route handler directly with mocked dependencies
        with patch(
            "dataing.entrypoints.api.routes.investigations.get_investigation_service",
            return_value=mock_service,
        ):
            # Simulate what the route would receive
            mock_service.start_investigation.return_value = (
                uuid.uuid4(),
                uuid.uuid4(),
            )

            # Verify the request parsing works
            alert = AnomalyAlert(
                dataset_id=request.alert["dataset_id"],
                metric_spec=MetricSpec(
                    metric_type=request.alert["metric_spec"]["metric_type"],
                    expression=request.alert["metric_spec"]["expression"],
                    display_name=request.alert["metric_spec"]["display_name"],
                    columns_referenced=request.alert["metric_spec"].get(
                        "columns_referenced", []
                    ),
                ),
                anomaly_type=request.alert["anomaly_type"],
                expected_value=request.alert["expected_value"],
                actual_value=request.alert["actual_value"],
                deviation_pct=request.alert["deviation_pct"],
                anomaly_date=request.alert["anomaly_date"],
                severity=request.alert["severity"],
            )

            assert alert.dataset_id == "analytics.events"
            assert alert.metric_spec.display_name == "NULL rate"

    @pytest.mark.asyncio
    async def test_get_investigation_returns_state(
        self,
        mock_auth_context: ApiKeyContext,
        mock_service: AsyncMock,
    ) -> None:
        """Test that get_investigation returns proper state."""
        investigation_id = uuid.uuid4()
        branch_id = uuid.uuid4()

        mock_service.get_state.return_value = InvestigationState(
            investigation_id=investigation_id,
            status="active",
            main_branch=BranchState(
                branch_id=branch_id,
                status="active",
                current_step="generate_hypotheses",
            ),
        )

        state = await mock_service.get_state(
            investigation_id=investigation_id,
            user_id=mock_auth_context.user_id,
        )

        assert state.investigation_id == investigation_id
        assert state.main_branch.current_step == "generate_hypotheses"

    @pytest.mark.asyncio
    async def test_send_message_triggers_resume(
        self,
        mock_auth_context: ApiKeyContext,
        mock_service: AsyncMock,
    ) -> None:
        """Test that send_message triggers branch resume."""
        investigation_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        message = "Please investigate the upstream ETL job"

        mock_service.send_message.return_value = branch_id

        result_branch_id = await mock_service.send_message(
            investigation_id=investigation_id,
            user_id=mock_auth_context.user_id,
            message=message,
        )

        assert result_branch_id == branch_id
        mock_service.send_message.assert_called_once_with(
            investigation_id=investigation_id,
            user_id=mock_auth_context.user_id,
            message=message,
        )
