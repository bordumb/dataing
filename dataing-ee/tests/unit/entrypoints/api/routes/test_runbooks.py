"""Unit tests for Runbooks API routes (EE)."""


import pytest
from dataing_ee.entrypoints.api.routes.runbooks import (
    GenerateRunbookRequest,
    LinkFeedbackRequest,
    RunbookCreate,
    RunbookUpdate,
)


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
        update = RunbookUpdate(
            symptoms=[{"description": "New symptom", "severity": "medium"}]
        )
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
