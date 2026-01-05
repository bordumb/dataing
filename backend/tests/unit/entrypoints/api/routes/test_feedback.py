"""Tests for feedback API routes."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from dataing.entrypoints.api.routes.feedback import FeedbackCreate, FeedbackResponse
from pydantic import ValidationError


class TestFeedbackSchemas:
    """Tests for feedback Pydantic schemas."""

    def test_feedback_response_valid(self) -> None:
        """FeedbackResponse accepts valid data."""
        feedback_id = uuid4()
        now = datetime.now(UTC)
        response = FeedbackResponse(id=feedback_id, created_at=now)
        assert response.id == feedback_id
        assert response.created_at == now

    def test_feedback_create_valid(self) -> None:
        """FeedbackCreate accepts valid data."""
        data = FeedbackCreate(
            target_type="hypothesis",
            target_id=uuid4(),
            investigation_id=uuid4(),
            rating=1,
            reason="Right direction",
        )
        assert data.rating == 1
        assert data.target_type == "hypothesis"

    def test_feedback_create_negative_rating(self) -> None:
        """FeedbackCreate accepts negative rating."""
        data = FeedbackCreate(
            target_type="query",
            target_id=uuid4(),
            investigation_id=uuid4(),
            rating=-1,
        )
        assert data.rating == -1

    def test_feedback_create_invalid_rating(self) -> None:
        """FeedbackCreate rejects invalid rating."""
        with pytest.raises(ValidationError):
            FeedbackCreate(
                target_type="hypothesis",
                target_id=uuid4(),
                investigation_id=uuid4(),
                rating=0,  # Invalid - must be 1 or -1
            )

    def test_feedback_create_invalid_target_type(self) -> None:
        """FeedbackCreate rejects invalid target type."""
        with pytest.raises(ValidationError):
            FeedbackCreate(
                target_type="invalid",
                target_id=uuid4(),
                investigation_id=uuid4(),
                rating=1,
            )


class TestFeedbackEndpoint:
    """Tests for POST /feedback endpoint."""

    def test_submit_feedback_success(self) -> None:
        """POST /feedback creates feedback event."""
        from unittest.mock import AsyncMock, MagicMock

        from dataing.entrypoints.api.deps import get_feedback_adapter
        from dataing.entrypoints.api.middleware.auth import verify_api_key
        from dataing.entrypoints.api.routes.feedback import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        tenant_id = uuid4()
        investigation_id = uuid4()
        target_id = uuid4()
        user_id = uuid4()
        event_id = uuid4()
        created_at = datetime.now(UTC)

        # Create mock auth context
        mock_auth_context = MagicMock(tenant_id=tenant_id, user_id=user_id)

        # Create mock feedback adapter
        mock_adapter = MagicMock()
        mock_adapter.emit = AsyncMock(return_value=MagicMock(id=event_id, created_at=created_at))

        # Override dependencies
        app.dependency_overrides[verify_api_key] = lambda: mock_auth_context
        app.dependency_overrides[get_feedback_adapter] = lambda: mock_adapter

        client = TestClient(app)
        response = client.post(
            "/api/v1/feedback/",
            json={
                "target_type": "hypothesis",
                "target_id": str(target_id),
                "investigation_id": str(investigation_id),
                "rating": 1,
                "reason": "Right direction",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "created_at" in data
