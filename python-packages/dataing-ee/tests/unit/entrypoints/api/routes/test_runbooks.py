"""Unit tests for Runbooks API routes (EE)."""

from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from dataing_ee.entrypoints.api.routes.runbooks import (
    GenerateRunbookRequest,
    LinkFeedbackRequest,
    RunbookCreate,
    RunbookUpdate,
    router,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key


@pytest.fixture
def tenant_id() -> UUID:
    """Return the caller's tenant ID."""
    return uuid4()


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock app database."""
    return MagicMock(spec=AppDatabase)


@pytest.fixture
def mock_auth_context(tenant_id: UUID) -> ApiKeyContext:
    """Create mock auth context for the caller's tenant."""
    return ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="test",
        tenant_name="Test Tenant",
        user_id=uuid4(),
        scopes=["read", "write"],
    )


@pytest.fixture
def app(mock_db: MagicMock, mock_auth_context: ApiKeyContext) -> FastAPI:
    """Create test app with runbook routes."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: mock_db
    app.dependency_overrides[verify_api_key] = lambda: mock_auth_context
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestRunbookCreateSchema:
    """Test RunbookCreate Pydantic schema."""

    def test_valid_create(self) -> None:
        """Test valid creation payload."""
        payload = RunbookCreate(
            title="Database Connection Troubleshooting",
            body="# Overview\n\nThis runbook covers database connection issues.",
            summary="How to troubleshoot database connections",
            dataset_id="warehouse.orders",
            labels=["database", "production"],
            symptoms=[{"description": "Connection timeout", "severity": "high"}],
            root_cause="Network configuration issue",
            verification_steps=[{"step": 1, "description": "Check connectivity"}],
            fix_steps=[{"step": 1, "description": "Restart connection pool"}],
            prevention_notes="Set up connection monitoring",
            is_published=True,
        )
        assert payload.title == "Database Connection Troubleshooting"
        assert payload.is_published is True
        assert len(payload.labels) == 2
        assert len(payload.symptoms) == 1

    def test_minimal_create(self) -> None:
        """Test minimal creation payload."""
        payload = RunbookCreate(
            title="Test Runbook",
            body="Test body content",
        )
        assert payload.title == "Test Runbook"
        assert payload.body == "Test body content"
        assert payload.summary is None
        assert payload.labels == []
        assert payload.symptoms == []
        assert payload.is_published is False

    def test_empty_title_invalid(self) -> None:
        """Test empty title is rejected."""
        with pytest.raises(ValueError):
            RunbookCreate(title="", body="content")

    def test_empty_body_invalid(self) -> None:
        """Test empty body is rejected."""
        with pytest.raises(ValueError):
            RunbookCreate(title="Test", body="")


class TestRunbookUpdateSchema:
    """Test RunbookUpdate Pydantic schema."""

    def test_all_none(self) -> None:
        """Test all fields can be None."""
        update = RunbookUpdate()
        assert update.title is None
        assert update.body is None
        assert update.summary is None
        assert update.labels is None
        assert update.is_published is None

    def test_partial_update(self) -> None:
        """Test partial update."""
        update = RunbookUpdate(title="New Title", is_published=True)
        assert update.title == "New Title"
        assert update.is_published is True
        assert update.body is None

    def test_update_symptoms(self) -> None:
        """Test updating symptoms."""
        update = RunbookUpdate(symptoms=[{"description": "New symptom", "severity": "medium"}])
        assert len(update.symptoms) == 1
        assert update.symptoms[0]["description"] == "New symptom"


class TestGenerateRunbookRequestSchema:
    """Test GenerateRunbookRequest Pydantic schema."""

    def test_default_not_published(self) -> None:
        """Test default is not published."""
        request = GenerateRunbookRequest()
        assert request.publish is False

    def test_publish_flag(self) -> None:
        """Test publish flag."""
        request = GenerateRunbookRequest(publish=True)
        assert request.publish is True


class TestLinkFeedbackRequestSchema:
    """Test LinkFeedbackRequest Pydantic schema."""

    def test_helpful_feedback(self) -> None:
        """Test helpful feedback."""
        feedback = LinkFeedbackRequest(
            was_helpful=True,
            feedback_notes="This runbook solved the issue",
        )
        assert feedback.was_helpful is True
        assert feedback.feedback_notes == "This runbook solved the issue"

    def test_not_helpful_feedback(self) -> None:
        """Test not helpful feedback."""
        feedback = LinkFeedbackRequest(
            was_helpful=False,
            feedback_notes="Didn't apply to my case",
        )
        assert feedback.was_helpful is False

    def test_minimal_feedback(self) -> None:
        """Test minimal feedback (no notes)."""
        feedback = LinkFeedbackRequest(was_helpful=True)
        assert feedback.was_helpful is True
        assert feedback.feedback_notes is None


class TestProvideLinkFeedback:
    """Tests for POST /runbooks/{runbook_id}/link/{issue_id}/feedback."""

    def test_own_runbook_records_feedback(self, client: TestClient, mock_db: MagicMock) -> None:
        """Test feedback on a link to the caller's own runbook is recorded."""
        runbook_id, issue_id = uuid4(), uuid4()
        mock_db.fetch_one.return_value = {"id": runbook_id}
        mock_db.execute.return_value = "UPDATE 1"

        response = client.post(
            f"/api/v1/runbooks/{runbook_id}/link/{issue_id}/feedback",
            json={"was_helpful": True},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "feedback_recorded"}
        mock_db.execute.assert_awaited()

    def test_other_tenants_runbook_returns_404_without_update(
        self, client: TestClient, mock_db: MagicMock, tenant_id: UUID
    ) -> None:
        """Test feedback on another tenant's runbook link is rejected before any write."""
        runbook_id, issue_id = uuid4(), uuid4()

        async def fetch_one(query: str, *args: Any) -> dict[str, Any] | None:
            # The runbook belongs to another tenant: a lookup scoped to the
            # caller's tenant finds nothing, an unscoped one would find it.
            return None if tenant_id in args else {"id": runbook_id}

        mock_db.fetch_one.side_effect = fetch_one
        # The link row exists, so an unscoped UPDATE would match it.
        mock_db.execute.return_value = "UPDATE 1"

        response = client.post(
            f"/api/v1/runbooks/{runbook_id}/link/{issue_id}/feedback",
            json={"was_helpful": False, "feedback_notes": "overwritten"},
        )

        assert response.status_code == 404
        mock_db.execute.assert_not_awaited()


class TestRunbookContentValidation:
    """Test runbook content edge cases."""

    def test_long_title(self) -> None:
        """Test title length limit."""
        # Should accept up to 500 chars
        long_title = "A" * 500
        payload = RunbookCreate(title=long_title, body="content")
        assert len(payload.title) == 500

        # Should reject > 500 chars
        with pytest.raises(ValueError):
            RunbookCreate(title="A" * 501, body="content")

    def test_labels_list(self) -> None:
        """Test labels as list of strings."""
        payload = RunbookCreate(
            title="Test",
            body="content",
            labels=["database", "etl", "production", "urgent"],
        )
        assert len(payload.labels) == 4
        assert "database" in payload.labels

    def test_symptoms_structure(self) -> None:
        """Test symptoms as list of dicts."""
        payload = RunbookCreate(
            title="Test",
            body="content",
            symptoms=[
                {"description": "Symptom 1", "severity": "high"},
                {"description": "Symptom 2", "severity": "low", "extra": "field"},
            ],
        )
        assert len(payload.symptoms) == 2
        assert payload.symptoms[0]["severity"] == "high"
        # Extra fields are allowed
        assert payload.symptoms[1].get("extra") == "field"

    def test_verification_steps_structure(self) -> None:
        """Test verification steps structure."""
        payload = RunbookCreate(
            title="Test",
            body="content",
            verification_steps=[
                {"step": 1, "description": "Check A", "query": "SELECT 1"},
                {"step": 2, "description": "Check B"},
            ],
        )
        assert len(payload.verification_steps) == 2
        assert payload.verification_steps[0]["query"] == "SELECT 1"

    def test_fix_steps_structure(self) -> None:
        """Test fix steps structure."""
        payload = RunbookCreate(
            title="Test",
            body="content",
            fix_steps=[
                {"step": 1, "description": "Do A", "type": "manual"},
                {"step": 2, "description": "Do B", "type": "automated"},
            ],
        )
        assert len(payload.fix_steps) == 2
        assert payload.fix_steps[1]["type"] == "automated"
