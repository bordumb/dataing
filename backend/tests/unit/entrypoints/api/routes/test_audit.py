"""Tests for audit log routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dataing.adapters.audit.types import AuditLogEntry
from dataing.entrypoints.api.routes.audit import get_audit_repo, router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_audit_repo() -> AsyncMock:
    """Create mock audit repository."""
    return AsyncMock()


@pytest.fixture
def app(mock_audit_repo: AsyncMock) -> FastAPI:
    """Create test app with audit routes."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_audit_repo] = lambda: mock_audit_repo

    tenant_id = uuid4()
    user_id = uuid4()

    @app.middleware("http")
    async def add_state(request, call_next):  # type: ignore[no-untyped-def]
        request.state.tenant_id = tenant_id
        request.state.user_id = user_id
        request.state.user_email = "admin@example.com"
        return await call_next(request)

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestListAuditLogs:
    """Tests for list audit logs endpoint."""

    def test_returns_empty_list(self, client: TestClient, mock_audit_repo: AsyncMock) -> None:
        """Test listing returns empty list when no logs."""
        mock_audit_repo.list.return_value = ([], 0)

        response = client.get("/api/v1/audit-logs")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_paginated_results(
        self, client: TestClient, mock_audit_repo: AsyncMock
    ) -> None:
        """Test pagination parameters."""
        entry = AuditLogEntry(
            id=uuid4(),
            timestamp=datetime.now(UTC),
            tenant_id=uuid4(),
            action="team.create",
            resource_type="team",
        )
        mock_audit_repo.list.return_value = ([entry], 1)

        response = client.get("/api/v1/audit-logs?page=1&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["limit"] == 10

    def test_filter_by_action(self, client: TestClient, mock_audit_repo: AsyncMock) -> None:
        """Test filtering by action."""
        mock_audit_repo.list.return_value = ([], 0)

        response = client.get("/api/v1/audit-logs?action=team.create")

        assert response.status_code == 200
        # Verify the repo was called with action filter
        mock_audit_repo.list.assert_called_once()
        call_kwargs = mock_audit_repo.list.call_args.kwargs
        assert call_kwargs["action"] == "team.create"

    def test_filter_by_resource_type(self, client: TestClient, mock_audit_repo: AsyncMock) -> None:
        """Test filtering by resource type."""
        mock_audit_repo.list.return_value = ([], 0)

        response = client.get("/api/v1/audit-logs?resource_type=team")

        assert response.status_code == 200
        call_kwargs = mock_audit_repo.list.call_args.kwargs
        assert call_kwargs["resource_type"] == "team"

    def test_filter_by_date_range(self, client: TestClient, mock_audit_repo: AsyncMock) -> None:
        """Test filtering by date range."""
        mock_audit_repo.list.return_value = ([], 0)
        start = "2024-01-01T00:00:00Z"
        end = "2024-01-31T23:59:59Z"

        response = client.get(f"/api/v1/audit-logs?start_date={start}&end_date={end}")

        assert response.status_code == 200
        call_kwargs = mock_audit_repo.list.call_args.kwargs
        assert call_kwargs["start_date"] is not None
        assert call_kwargs["end_date"] is not None

    def test_search_filter(self, client: TestClient, mock_audit_repo: AsyncMock) -> None:
        """Test search filter."""
        mock_audit_repo.list.return_value = ([], 0)

        response = client.get("/api/v1/audit-logs?search=test")

        assert response.status_code == 200
        call_kwargs = mock_audit_repo.list.call_args.kwargs
        assert call_kwargs["search"] == "test"


class TestGetAuditLog:
    """Tests for get single audit log endpoint."""

    def test_returns_entry(self, client: TestClient, mock_audit_repo: AsyncMock) -> None:
        """Test getting a single entry."""
        entry_id = uuid4()
        entry = AuditLogEntry(
            id=entry_id,
            timestamp=datetime.now(UTC),
            tenant_id=uuid4(),
            action="team.create",
            resource_type="team",
            resource_name="Engineering",
        )
        mock_audit_repo.get.return_value = entry

        response = client.get(f"/api/v1/audit-logs/{entry_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(entry_id)
        assert data["action"] == "team.create"
        assert data["resource_name"] == "Engineering"

    def test_returns_404_when_not_found(
        self, client: TestClient, mock_audit_repo: AsyncMock
    ) -> None:
        """Test 404 when entry not found."""
        entry_id = uuid4()
        mock_audit_repo.get.return_value = None

        response = client.get(f"/api/v1/audit-logs/{entry_id}")

        assert response.status_code == 404


class TestExportAuditLogs:
    """Tests for export audit logs endpoint."""

    def test_exports_csv(self, client: TestClient, mock_audit_repo: AsyncMock) -> None:
        """Test exporting logs as CSV."""
        entry = AuditLogEntry(
            id=uuid4(),
            timestamp=datetime.now(UTC),
            tenant_id=uuid4(),
            action="team.create",
            resource_type="team",
            resource_name="Engineering",
            actor_email="admin@example.com",
        )
        mock_audit_repo.list.return_value = ([entry], 1)

        response = client.get("/api/v1/audit-logs/export")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        # Check CSV content
        content = response.text
        assert "Timestamp" in content
        assert "Action" in content
        assert "team.create" in content
        assert "admin@example.com" in content

    def test_export_with_filters(self, client: TestClient, mock_audit_repo: AsyncMock) -> None:
        """Test exporting with filters."""
        mock_audit_repo.list.return_value = ([], 0)

        response = client.get("/api/v1/audit-logs/export?action=team.create")

        assert response.status_code == 200
        call_kwargs = mock_audit_repo.list.call_args.kwargs
        assert call_kwargs["action"] == "team.create"
        # Export should fetch up to 10000 records
        assert call_kwargs["limit"] == 10000
