"""Unit tests for SQLAlchemy models."""

from __future__ import annotations

from dataing.models.base import BaseModel


class TestTenantModel:
    """Tests for Tenant model."""

    def test_model_imported(self) -> None:
        """Test that model can be imported."""
        from dataing.models.tenant import Tenant

        assert Tenant.__tablename__ == "tenants"

    def test_tenant_has_columns(self) -> None:
        """Test tenant has required columns."""
        from dataing.models.tenant import Tenant

        columns = [c.name for c in Tenant.__table__.columns]
        assert "id" in columns
        assert "name" in columns
        assert "slug" in columns


class TestUserModel:
    """Tests for User model."""

    def test_model_imported(self) -> None:
        """Test that model can be imported."""
        from dataing.models.user import User

        assert User.__tablename__ == "users"

    def test_user_has_columns(self) -> None:
        """Test user has required columns."""
        from dataing.models.user import User

        columns = [c.name for c in User.__table__.columns]
        assert "id" in columns
        assert "email" in columns


class TestApiKeyModel:
    """Tests for ApiKey model."""

    def test_model_imported(self) -> None:
        """Test that model can be imported."""
        from dataing.models.api_key import ApiKey

        assert ApiKey.__tablename__ == "api_keys"

    def test_api_key_has_columns(self) -> None:
        """Test api_key has required columns."""
        from dataing.models.api_key import ApiKey

        columns = [c.name for c in ApiKey.__table__.columns]
        assert "id" in columns
        assert "key_hash" in columns
        assert "tenant_id" in columns


class TestDataSourceModel:
    """Tests for DataSource model."""

    def test_model_imported(self) -> None:
        """Test that model can be imported."""
        from dataing.models.data_source import DataSource

        assert DataSource.__tablename__ == "data_sources"

    def test_data_source_has_columns(self) -> None:
        """Test data_source has required columns."""
        from dataing.models.data_source import DataSource

        columns = [c.name for c in DataSource.__table__.columns]
        assert "id" in columns
        assert "name" in columns
        assert "type" in columns


class TestAuditLogModel:
    """Tests for AuditLog model."""

    def test_model_imported(self) -> None:
        """Test that model can be imported."""
        from dataing.models.audit_log import AuditLog

        assert AuditLog.__tablename__ == "audit_logs"

    def test_audit_log_has_columns(self) -> None:
        """Test audit_log has required columns."""
        from dataing.models.audit_log import AuditLog

        columns = [c.name for c in AuditLog.__table__.columns]
        assert "id" in columns
        assert "action" in columns


class TestWebhookModel:
    """Tests for Webhook model."""

    def test_model_imported(self) -> None:
        """Test that model can be imported."""
        from dataing.models.webhook import Webhook

        assert Webhook.__tablename__ == "webhooks"

    def test_webhook_has_columns(self) -> None:
        """Test webhook has required columns."""
        from dataing.models.webhook import Webhook

        columns = [c.name for c in Webhook.__table__.columns]
        assert "id" in columns
        assert "url" in columns
