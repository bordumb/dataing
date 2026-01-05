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
