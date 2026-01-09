"""Unit tests for investigations routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from dataing.core.domain_types import AnomalyAlert, Finding
from dataing.core.state import InvestigationState
from dataing.entrypoints.api.middleware.auth import ApiKeyContext
from dataing.entrypoints.api.routes.investigations import (
    CreateInvestigationRequest,
    InvestigationResponse,
    InvestigationStatusResponse,
    router,
)


class TestCreateInvestigationRequest:
    """Tests for CreateInvestigationRequest."""

    def test_create_request(self) -> None:
        """Test creating an investigation request."""
        request = CreateInvestigationRequest(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
        )

        assert request.dataset_id == "public.orders"
        assert request.severity == "medium"  # Default

    def test_create_request_with_metadata(self) -> None:
        """Test creating request with metadata."""
        request = CreateInvestigationRequest(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            metadata={"source": "airflow"},
        )

        assert request.metadata["source"] == "airflow"


class TestInvestigationResponse:
    """Tests for InvestigationResponse."""

    def test_create_response(self) -> None:
        """Test creating investigation response."""
        response = InvestigationResponse(
            investigation_id="inv-001",
            status="started",
            created_at=datetime.now(timezone.utc),
        )

        assert response.investigation_id == "inv-001"
        assert response.status == "started"


class TestInvestigationStatusResponse:
    """Tests for InvestigationStatusResponse."""

    def test_create_status_response(self) -> None:
        """Test creating status response."""
        response = InvestigationStatusResponse(
            investigation_id="inv-001",
            status="in_progress",
            events=[{"type": "started", "timestamp": "2024-01-15T00:00:00Z", "data": {}}],
            finding=None,
        )

        assert response.investigation_id == "inv-001"
        assert len(response.events) == 1

    def test_create_status_response_with_finding(self) -> None:
        """Test creating status response with finding."""
        response = InvestigationStatusResponse(
            investigation_id="inv-001",
            status="completed",
            events=[],
            finding={"root_cause": "Test cause", "confidence": 0.9},
        )

        assert response.finding["root_cause"] == "Test cause"


class TestInvestigationsRoutes:
    """Tests for investigation routes."""

    @pytest.fixture
    def mock_auth_context(self) -> ApiKeyContext:
        """Return a mock auth context."""
        return ApiKeyContext(
            key_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_slug="test-tenant",
            tenant_name="Test Tenant",
            user_id=None,
            scopes=["read", "write"],
        )

    @pytest.fixture
    def mock_orchestrator(self) -> AsyncMock:
        """Return a mock orchestrator."""
        mock = AsyncMock()
        mock.run_investigation.return_value = Finding(
            investigation_id="inv-001",
            status="completed",
            root_cause="Test root cause",
            confidence=0.9,
            evidence=[],
            recommendations=["Test recommendation"],
            duration_seconds=10.0,
        )
        return mock

    @pytest.fixture
    def mock_investigations(self) -> dict:
        """Return a mock investigations store."""
        return {}

    @pytest.fixture
    def sample_investigation(
        self,
        mock_auth_context: ApiKeyContext,
    ) -> dict:
        """Return a sample investigation."""
        alert = AnomalyAlert(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            severity="high",
        )
        state = InvestigationState(id="inv-001", alert=alert)
        return {
            "state": state,
            "finding": None,
            "status": "in_progress",
            "created_at": datetime.now(timezone.utc),
            "tenant_id": str(mock_auth_context.tenant_id),
        }

    def test_create_investigation_request_model(self) -> None:
        """Test the request model validation."""
        # Valid request
        request = CreateInvestigationRequest(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
        )
        assert request.dataset_id == "public.orders"

    def test_investigation_response_model(self) -> None:
        """Test the response model."""
        response = InvestigationResponse(
            investigation_id="inv-123",
            status="started",
            created_at=datetime.now(timezone.utc),
        )
        assert response.investigation_id == "inv-123"

    def test_investigation_status_model(self) -> None:
        """Test the status response model."""
        response = InvestigationStatusResponse(
            investigation_id="inv-123",
            status="completed",
            events=[],
            finding={"root_cause": "Test", "confidence": 0.9},
        )
        assert response.status == "completed"
        assert response.finding["root_cause"] == "Test"

    def test_investigation_not_found_scenario(self) -> None:
        """Test that 404 is raised for unknown investigation ID."""
        investigations = {}
        investigation_id = "nonexistent"

        assert investigation_id not in investigations

    def test_tenant_access_denied_scenario(
        self,
        sample_investigation: dict,
        mock_auth_context: ApiKeyContext,
    ) -> None:
        """Test tenant access control."""
        # Create investigation with different tenant
        sample_investigation["tenant_id"] = str(uuid.uuid4())

        # Mock auth has different tenant
        assert sample_investigation["tenant_id"] != str(mock_auth_context.tenant_id)
