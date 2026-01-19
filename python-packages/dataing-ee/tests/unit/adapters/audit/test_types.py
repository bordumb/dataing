"""Tests for audit types."""

from datetime import UTC, datetime
from uuid import uuid4

from dataing_ee.adapters.audit.types import AuditLogCreate, AuditLogEntry


class TestAuditLogEntry:
    """Tests for AuditLogEntry model."""

    def test_create_audit_log_entry(self) -> None:
        """Test creating an audit log entry."""
        entry = AuditLogEntry(
            id=uuid4(),
            timestamp=datetime.now(UTC),
            tenant_id=uuid4(),
            actor_id=uuid4(),
            actor_email="test@example.com",
            action="team.create",
            resource_type="team",
            resource_id=uuid4(),
            resource_name="Engineering",
        )
        assert entry.action == "team.create"
        assert entry.resource_type == "team"

    def test_audit_log_entry_optional_fields(self) -> None:
        """Test audit log entry with optional fields as None."""
        entry = AuditLogEntry(
            id=uuid4(),
            timestamp=datetime.now(UTC),
            tenant_id=uuid4(),
            action="auth.login",
        )
        assert entry.actor_id is None
        assert entry.resource_type is None
        assert entry.changes is None


class TestAuditLogCreate:
    """Tests for AuditLogCreate model."""

    def test_create_audit_log_create(self) -> None:
        """Test creating an audit log create request."""
        create = AuditLogCreate(
            tenant_id=uuid4(),
            actor_id=uuid4(),
            actor_email="test@example.com",
            action="datasource.create",
            resource_type="datasource",
        )
        assert create.action == "datasource.create"
