"""Tests for audit types."""

from uuid import uuid4

from dataing.adapters.audit import AuditLogCreate


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
