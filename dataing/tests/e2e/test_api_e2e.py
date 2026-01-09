"""End-to-end tests for the API.

These tests simulate real API usage patterns and verify the complete
request/response flow.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dataing.core.domain_types import Finding, QueryResult, SchemaContext, TableSchema
from dataing.entrypoints.api.app import app


class TestAPIEndToEnd:
    """End-to-end tests for the API."""

    @pytest.fixture
    def mock_state(self) -> None:
        """Set up mock app state."""
        # Mock database
        mock_db = AsyncMock()
        mock_db.get_api_key_by_hash.return_value = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "user_id": None,
            "scopes": ["read", "write"],
            "expires_at": None,
            "tenant_slug": "test-tenant",
            "tenant_name": "Test Tenant",
        }
        mock_db.update_api_key_last_used.return_value = None
        mock_db.execute_query.return_value = QueryResult(
            columns=("count",),
            rows=({"count": 500},),
            row_count=1,
        )
        mock_db.get_schema.return_value = SchemaContext(
            tables=(
                TableSchema(
                    table_name="public.orders",
                    columns=("id", "total"),
                    column_types={"id": "integer", "total": "numeric"},
                ),
            )
        )

        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_orchestrator.run_investigation.return_value = Finding(
            investigation_id="inv-001",
            status="completed",
            root_cause="Test root cause",
            confidence=0.9,
            evidence=[],
            recommendations=["Test recommendation"],
            duration_seconds=10.0,
        )

        # Set up app state
        app.state.db = mock_db
        app.state.app_db = mock_db
        app.state.orchestrator = mock_orchestrator
        app.state.investigations = {}

    @pytest.fixture
    def client(self, mock_state: None) -> TestClient:
        """Return a test client."""
        return TestClient(app)

    def test_health_check(self, client: TestClient) -> None:
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_health_check_no_auth_required(self, client: TestClient) -> None:
        """Test that health check doesn't require authentication."""
        # No API key header
        response = client.get("/health")

        assert response.status_code == 200

    def test_investigation_endpoint_requires_auth(
        self,
        client: TestClient,
    ) -> None:
        """Test that investigation endpoints require authentication."""
        # No API key
        response = client.get("/api/v1/investigations")

        assert response.status_code == 401

    def test_investigation_list_with_auth(
        self,
        client: TestClient,
    ) -> None:
        """Test listing investigations with valid auth."""
        response = client.get(
            "/api/v1/investigations",
            headers={"X-API-Key": "ddr_valid_test_key"},
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_investigation(
        self,
        client: TestClient,
    ) -> None:
        """Test creating an investigation."""
        payload = {
            "dataset_id": "public.orders",
            "metric_name": "row_count",
            "expected_value": 1000.0,
            "actual_value": 500.0,
            "deviation_pct": 50.0,
            "anomaly_date": "2024-01-15",
            "severity": "high",
        }

        response = client.post(
            "/api/v1/investigations",
            json=payload,
            headers={"X-API-Key": "ddr_valid_test_key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "investigation_id" in data
        assert data["status"] == "started"

    def test_create_investigation_validates_payload(
        self,
        client: TestClient,
    ) -> None:
        """Test that invalid payloads are rejected."""
        # Missing required fields
        payload = {
            "dataset_id": "public.orders",
            # Missing other required fields
        }

        response = client.post(
            "/api/v1/investigations",
            json=payload,
            headers={"X-API-Key": "ddr_valid_test_key"},
        )

        assert response.status_code == 422  # Validation error

    def test_get_investigation_not_found(
        self,
        client: TestClient,
    ) -> None:
        """Test getting non-existent investigation."""
        response = client.get(
            "/api/v1/investigations/nonexistent-id",
            headers={"X-API-Key": "ddr_valid_test_key"},
        )

        assert response.status_code == 404

    def test_api_key_in_different_case(
        self,
        client: TestClient,
    ) -> None:
        """Test that API key header is case-insensitive."""
        # FastAPI/Starlette handles header case insensitivity
        response = client.get(
            "/api/v1/investigations",
            headers={"x-api-key": "ddr_valid_test_key"},
        )

        assert response.status_code == 200

    def test_cors_headers(
        self,
        client: TestClient,
    ) -> None:
        """Test that CORS headers are present."""
        response = client.options(
            "/api/v1/investigations",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        # CORS preflight should succeed
        assert response.status_code in [200, 204]


class TestAPIAuthenticationFlow:
    """Tests for complete authentication flows."""

    @pytest.fixture
    def mock_state_with_expired_key(self) -> None:
        """Set up mock app state with expired key."""
        from datetime import timedelta

        mock_db = AsyncMock()
        mock_db.get_api_key_by_hash.return_value = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "user_id": None,
            "scopes": ["read", "write"],
            "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
            "tenant_slug": "test-tenant",
            "tenant_name": "Test Tenant",
        }

        app.state.db = mock_db
        app.state.app_db = mock_db
        app.state.investigations = {}

    @pytest.fixture
    def mock_state_read_only(self) -> None:
        """Set up mock app state with read-only key."""
        mock_db = AsyncMock()
        mock_db.get_api_key_by_hash.return_value = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "user_id": None,
            "scopes": ["read"],  # Read only
            "expires_at": None,
            "tenant_slug": "test-tenant",
            "tenant_name": "Test Tenant",
        }
        mock_db.update_api_key_last_used.return_value = None

        app.state.db = mock_db
        app.state.app_db = mock_db
        app.state.investigations = {}

    def test_expired_api_key_rejected(
        self,
        mock_state_with_expired_key: None,
    ) -> None:
        """Test that expired API keys are rejected."""
        client = TestClient(app)

        response = client.get(
            "/api/v1/investigations",
            headers={"X-API-Key": "ddr_expired_key"},
        )

        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_read_only_key_can_read(
        self,
        mock_state_read_only: None,
    ) -> None:
        """Test that read-only key can read."""
        client = TestClient(app)

        response = client.get(
            "/api/v1/investigations",
            headers={"X-API-Key": "ddr_readonly_key"},
        )

        assert response.status_code == 200


class TestAPIRateLimiting:
    """Tests for rate limiting behavior."""

    def test_rate_limit_headers_present(self) -> None:
        """Test that rate limit headers are present in responses."""
        # Note: This would need the middleware to be properly configured
        # For now, just verify the structure
        pass

    def test_health_check_not_rate_limited(self) -> None:
        """Test that health check is not rate limited."""
        # Health checks should bypass rate limiting
        client = TestClient(app)

        # Make many requests
        for _ in range(100):
            response = client.get("/health")
            assert response.status_code == 200
