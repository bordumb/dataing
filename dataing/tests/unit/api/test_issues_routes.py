"""Unit tests for Issues API routes."""

from datetime import UTC
from uuid import uuid4

import pytest

from dataing.entrypoints.api.routes.issues import (
    STATE_TRANSITIONS,
    IssueCreate,
    IssueUpdate,
    _decode_cursor,
    _encode_cursor,
    validate_state_transition,
)
from dataing.models.issue import IssueStatus


class TestStateTransitions:
    """Test state machine transitions."""

    def test_all_states_have_transitions(self) -> None:
        """Test all IssueStatus values have defined transitions."""
        for status in IssueStatus:
            assert status.value in STATE_TRANSITIONS, f"Missing transitions for {status.value}"

    def test_open_to_triaged_valid(self) -> None:
        """Test OPEN -> TRIAGED is valid without assignee."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.OPEN.value,
            new_status=IssueStatus.TRIAGED.value,
            assignee_user_id=None,
            acknowledged_by=None,
            resolution_note=None,
        )
        assert is_valid
        assert error == ""

    def test_open_to_closed_valid(self) -> None:
        """Test OPEN -> CLOSED is valid (skip triage)."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.OPEN.value,
            new_status=IssueStatus.CLOSED.value,
            assignee_user_id=None,
            acknowledged_by=None,
            resolution_note=None,
        )
        assert is_valid

    def test_open_to_in_progress_invalid(self) -> None:
        """Test OPEN -> IN_PROGRESS is invalid (must go through TRIAGED)."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.OPEN.value,
            new_status=IssueStatus.IN_PROGRESS.value,
            assignee_user_id=uuid4(),
            acknowledged_by=None,
            resolution_note=None,
        )
        assert not is_valid
        assert "Cannot transition" in error

    def test_triaged_to_in_progress_with_assignee(self) -> None:
        """Test TRIAGED -> IN_PROGRESS requires assignee."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.TRIAGED.value,
            new_status=IssueStatus.IN_PROGRESS.value,
            assignee_user_id=uuid4(),
            acknowledged_by=None,
            resolution_note=None,
        )
        assert is_valid

    def test_triaged_to_in_progress_with_acknowledged_by(self) -> None:
        """Test TRIAGED -> IN_PROGRESS valid with acknowledged_by instead of assignee."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.TRIAGED.value,
            new_status=IssueStatus.IN_PROGRESS.value,
            assignee_user_id=None,
            acknowledged_by=uuid4(),
            resolution_note=None,
        )
        assert is_valid

    def test_triaged_to_in_progress_without_owner_fails(self) -> None:
        """Test TRIAGED -> IN_PROGRESS fails without assignee or acknowledged_by."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.TRIAGED.value,
            new_status=IssueStatus.IN_PROGRESS.value,
            assignee_user_id=None,
            acknowledged_by=None,
            resolution_note=None,
        )
        assert not is_valid
        assert "requires an assignee or acknowledged_by" in error

    def test_triaged_to_blocked_requires_owner(self) -> None:
        """Test TRIAGED -> BLOCKED requires assignee or acknowledged_by."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.TRIAGED.value,
            new_status=IssueStatus.BLOCKED.value,
            assignee_user_id=None,
            acknowledged_by=None,
            resolution_note=None,
        )
        assert not is_valid
        assert "requires an assignee or acknowledged_by" in error

    def test_in_progress_to_resolved_with_note(self) -> None:
        """Test IN_PROGRESS -> RESOLVED valid with resolution_note."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.IN_PROGRESS.value,
            new_status=IssueStatus.RESOLVED.value,
            assignee_user_id=uuid4(),
            acknowledged_by=None,
            resolution_note="Fixed the issue",
        )
        assert is_valid

    def test_in_progress_to_resolved_with_investigation(self) -> None:
        """Test IN_PROGRESS -> RESOLVED valid with linked investigation."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.IN_PROGRESS.value,
            new_status=IssueStatus.RESOLVED.value,
            assignee_user_id=uuid4(),
            acknowledged_by=None,
            resolution_note=None,
            has_linked_investigation=True,
        )
        assert is_valid

    def test_in_progress_to_resolved_without_resolution_fails(self) -> None:
        """Test IN_PROGRESS -> RESOLVED fails without resolution_note or investigation."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.IN_PROGRESS.value,
            new_status=IssueStatus.RESOLVED.value,
            assignee_user_id=uuid4(),
            acknowledged_by=None,
            resolution_note=None,
            has_linked_investigation=False,
        )
        assert not is_valid
        assert "requires resolution_note or a linked investigation" in error

    def test_resolved_to_closed_valid(self) -> None:
        """Test RESOLVED -> CLOSED is valid."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.RESOLVED.value,
            new_status=IssueStatus.CLOSED.value,
            assignee_user_id=None,
            acknowledged_by=None,
            resolution_note=None,
        )
        assert is_valid

    def test_closed_to_open_reopen_valid(self) -> None:
        """Test CLOSED -> OPEN (reopen) is valid."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.CLOSED.value,
            new_status=IssueStatus.OPEN.value,
            assignee_user_id=None,
            acknowledged_by=None,
            resolution_note=None,
        )
        assert is_valid

    def test_closed_to_in_progress_invalid(self) -> None:
        """Test CLOSED -> IN_PROGRESS is invalid (must reopen first)."""
        is_valid, error = validate_state_transition(
            current_status=IssueStatus.CLOSED.value,
            new_status=IssueStatus.IN_PROGRESS.value,
            assignee_user_id=uuid4(),
            acknowledged_by=None,
            resolution_note=None,
        )
        assert not is_valid
        assert "Cannot transition" in error

    def test_in_progress_blocked_bidirectional(self) -> None:
        """Test IN_PROGRESS <-> BLOCKED transitions are valid."""
        # IN_PROGRESS -> BLOCKED
        is_valid, _ = validate_state_transition(
            current_status=IssueStatus.IN_PROGRESS.value,
            new_status=IssueStatus.BLOCKED.value,
            assignee_user_id=uuid4(),
            acknowledged_by=None,
            resolution_note=None,
        )
        assert is_valid

        # BLOCKED -> IN_PROGRESS
        is_valid, _ = validate_state_transition(
            current_status=IssueStatus.BLOCKED.value,
            new_status=IssueStatus.IN_PROGRESS.value,
            assignee_user_id=uuid4(),
            acknowledged_by=None,
            resolution_note=None,
        )
        assert is_valid


class TestCursorEncoding:
    """Test cursor encoding and decoding."""

    def test_encode_decode_roundtrip(self) -> None:
        """Test cursor encodes and decodes correctly."""
        from datetime import datetime

        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        issue_id = uuid4()

        encoded = _encode_cursor(ts, issue_id)
        decoded = _decode_cursor(encoded)

        assert decoded is not None
        decoded_ts, decoded_id = decoded
        assert decoded_ts == ts
        assert decoded_id == issue_id

    def test_decode_invalid_cursor(self) -> None:
        """Test invalid cursor returns None."""
        assert _decode_cursor("invalid") is None
        assert _decode_cursor("") is None
        assert _decode_cursor("abc123") is None


class TestPydanticSchemas:
    """Test Pydantic request/response schemas."""

    def test_issue_create_valid(self) -> None:
        """Test IssueCreate with valid data."""
        data = IssueCreate(
            title="Test issue",
            description="Test description",
            priority="P1",
            severity="high",
            labels=["bug", "urgent"],
        )
        assert data.title == "Test issue"
        assert data.priority == "P1"
        assert len(data.labels) == 2

    def test_issue_create_minimal(self) -> None:
        """Test IssueCreate with only required fields."""
        data = IssueCreate(title="Minimal issue")
        assert data.title == "Minimal issue"
        assert data.description is None
        assert data.priority is None
        assert data.labels == []

    def test_issue_create_invalid_priority(self) -> None:
        """Test IssueCreate rejects invalid priority."""
        with pytest.raises(ValueError):
            IssueCreate(title="Test", priority="P5")

    def test_issue_create_invalid_severity(self) -> None:
        """Test IssueCreate rejects invalid severity."""
        with pytest.raises(ValueError):
            IssueCreate(title="Test", severity="extreme")

    def test_issue_update_valid(self) -> None:
        """Test IssueUpdate with valid data."""
        data = IssueUpdate(
            status="in_progress",
            assignee_user_id=uuid4(),
        )
        assert data.status == "in_progress"
        assert data.assignee_user_id is not None

    def test_issue_update_all_none(self) -> None:
        """Test IssueUpdate with no fields set."""
        data = IssueUpdate()
        assert data.title is None
        assert data.status is None

    def test_issue_update_invalid_status(self) -> None:
        """Test IssueUpdate rejects invalid status."""
        with pytest.raises(ValueError):
            IssueUpdate(status="invalid_status")
