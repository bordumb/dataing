"""Unit tests for Issue models."""

from dataing.models.issue import (
    Issue,
    IssueApprovalStatus,
    IssueAuthorType,
    IssueEvent,
    IssueEventType,
    IssueExecutionProfile,
    IssueInvestigationRun,
    IssuePriority,
    IssueRelationship,
    IssueRelationshipType,
    IssueSeverity,
    IssueStatus,
    IssueTriggerType,
    IssueWatcher,
)


class TestIssueEnums:
    """Test Issue enum values."""

    def test_issue_status_values(self) -> None:
        """Test IssueStatus enum has expected values."""
        assert IssueStatus.OPEN.value == "open"
        assert IssueStatus.TRIAGED.value == "triaged"
        assert IssueStatus.IN_PROGRESS.value == "in_progress"
        assert IssueStatus.BLOCKED.value == "blocked"
        assert IssueStatus.RESOLVED.value == "resolved"
        assert IssueStatus.CLOSED.value == "closed"

    def test_issue_priority_values(self) -> None:
        """Test IssuePriority enum has expected values."""
        assert IssuePriority.P0.value == "P0"
        assert IssuePriority.P1.value == "P1"
        assert IssuePriority.P2.value == "P2"
        assert IssuePriority.P3.value == "P3"

    def test_issue_severity_values(self) -> None:
        """Test IssueSeverity enum has expected values."""
        assert IssueSeverity.LOW.value == "low"
        assert IssueSeverity.MEDIUM.value == "medium"
        assert IssueSeverity.HIGH.value == "high"
        assert IssueSeverity.CRITICAL.value == "critical"

    def test_issue_author_type_values(self) -> None:
        """Test IssueAuthorType enum has expected values."""
        assert IssueAuthorType.HUMAN.value == "human"
        assert IssueAuthorType.INTEGRATION.value == "integration"

    def test_issue_event_type_values(self) -> None:
        """Test IssueEventType enum has expected values."""
        assert IssueEventType.CREATED.value == "created"
        assert IssueEventType.STATUS_CHANGED.value == "status_changed"
        assert IssueEventType.ASSIGNED.value == "assigned"
        assert IssueEventType.COMMENT_ADDED.value == "comment_added"
        assert IssueEventType.INVESTIGATION_SPAWNED.value == "investigation_spawned"

    def test_issue_relationship_type_values(self) -> None:
        """Test IssueRelationshipType enum has expected values."""
        assert IssueRelationshipType.DUPLICATES.value == "duplicates"
        assert IssueRelationshipType.BLOCKS.value == "blocks"
        assert IssueRelationshipType.RELATES_TO.value == "relates_to"

    def test_issue_trigger_type_values(self) -> None:
        """Test IssueTriggerType enum has expected values."""
        assert IssueTriggerType.HUMAN.value == "human"
        assert IssueTriggerType.RULE.value == "rule"
        assert IssueTriggerType.WEBHOOK.value == "webhook"

    def test_issue_execution_profile_values(self) -> None:
        """Test IssueExecutionProfile enum has expected values."""
        assert IssueExecutionProfile.SAFE.value == "safe"
        assert IssueExecutionProfile.STANDARD.value == "standard"
        assert IssueExecutionProfile.DEEP.value == "deep"

    def test_issue_approval_status_values(self) -> None:
        """Test IssueApprovalStatus enum has expected values."""
        assert IssueApprovalStatus.QUEUED.value == "queued"
        assert IssueApprovalStatus.APPROVED.value == "approved"
        assert IssueApprovalStatus.REJECTED.value == "rejected"


class TestIssueModel:
    """Test Issue model attributes."""

    def test_issue_tablename(self) -> None:
        """Test Issue has correct tablename."""
        assert Issue.__tablename__ == "issues"

    def test_issue_has_required_columns(self) -> None:
        """Test Issue model has all required columns."""
        columns = {c.key for c in Issue.__table__.columns}
        required = {
            "id",
            "tenant_id",
            "number",
            "title",
            "description",
            "status",
            "priority",
            "severity",
            "due_at",
            "dataset_id",
            "assignee_user_id",
            "acknowledged_by",
            "created_by_user_id",
            "author_type",
            "source_provider",
            "source_external_id",
            "source_external_url",
            "source_fingerprint",
            "sla_policy_id",
            "resolution_note",
            "created_at",
            "updated_at",
            "closed_at",
            "search_vector",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"


class TestIssueEventModel:
    """Test IssueEvent model attributes."""

    def test_issue_event_tablename(self) -> None:
        """Test IssueEvent has correct tablename."""
        assert IssueEvent.__tablename__ == "issue_events"

    def test_issue_event_has_required_columns(self) -> None:
        """Test IssueEvent model has all required columns."""
        columns = {c.key for c in IssueEvent.__table__.columns}
        required = {"id", "issue_id", "event_type", "actor_user_id", "payload", "created_at"}
        assert required.issubset(columns), f"Missing columns: {required - columns}"


class TestIssueRelationshipModel:
    """Test IssueRelationship model attributes."""

    def test_issue_relationship_tablename(self) -> None:
        """Test IssueRelationship has correct tablename."""
        assert IssueRelationship.__tablename__ == "issue_relationships"

    def test_issue_relationship_has_required_columns(self) -> None:
        """Test IssueRelationship model has all required columns."""
        columns = {c.key for c in IssueRelationship.__table__.columns}
        required = {"id", "from_issue_id", "to_issue_id", "relationship_type", "created_at"}
        assert required.issubset(columns), f"Missing columns: {required - columns}"


class TestIssueWatcherModel:
    """Test IssueWatcher model attributes."""

    def test_issue_watcher_tablename(self) -> None:
        """Test IssueWatcher has correct tablename."""
        assert IssueWatcher.__tablename__ == "issue_watchers"

    def test_issue_watcher_has_required_columns(self) -> None:
        """Test IssueWatcher model has all required columns."""
        columns = {c.key for c in IssueWatcher.__table__.columns}
        required = {"issue_id", "user_id", "created_at"}
        assert required.issubset(columns), f"Missing columns: {required - columns}"


class TestIssueInvestigationRunModel:
    """Test IssueInvestigationRun model attributes."""

    def test_issue_investigation_run_tablename(self) -> None:
        """Test IssueInvestigationRun has correct tablename."""
        assert IssueInvestigationRun.__tablename__ == "issue_investigation_runs"

    def test_issue_investigation_run_has_required_columns(self) -> None:
        """Test IssueInvestigationRun model has all required columns."""
        columns = {c.key for c in IssueInvestigationRun.__table__.columns}
        required = {
            "id",
            "issue_id",
            "investigation_id",
            "trigger_type",
            "trigger_ref",
            "brief",
            "execution_profile",
            "approval_status",
            "confidence",
            "root_cause_tag",
            "synthesis_summary",
            "created_at",
            "completed_at",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"
