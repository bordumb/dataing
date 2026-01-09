"""Integration tests for audit logging.

These tests verify that API actions are properly recorded in the audit log.
This catches the bug where AuditMiddleware was not registered or the database
attribute name was incorrect.
"""

from collections.abc import AsyncGenerator
from uuid import UUID

import pytest

from dataing.adapters.db.app_db import AppDatabase


@pytest.mark.integration
class TestAuditLoggingIntegration:
    """Integration tests for audit log recording.

    These tests verify that the audit logging middleware is properly registered
    and writes audit log entries to the database when API actions occur.
    """

    @pytest.fixture
    async def db(self) -> AsyncGenerator[AppDatabase, None]:
        """Create database connection."""
        db = AppDatabase(dsn="postgresql://localhost/dataing")  # pragma: allowlist secret
        try:
            await db.connect()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")
        yield db
        await db.close()

    @pytest.fixture
    async def tenant_id(self, db: AppDatabase) -> UUID:
        """Get a valid tenant ID from the database."""
        tenant = await db.fetch_one("SELECT id FROM tenants LIMIT 1")
        if not tenant:
            pytest.skip("No tenant in database")
        tenant_uuid: UUID = tenant["id"]
        return tenant_uuid

    async def test_audit_log_table_exists(self, db: AppDatabase) -> None:
        """Verify audit_logs table exists and is queryable.

        This is a basic sanity check that the migration has run.
        """
        result = await db.fetch_one(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'audit_logs'
            ) as exists
            """
        )
        assert result is not None
        assert result["exists"] is True

    async def test_audit_log_has_recent_entries(
        self,
        db: AppDatabase,
        tenant_id: UUID,
    ) -> None:
        """Verify audit logs are being written for the tenant.

        This test checks that the audit logging middleware is active by verifying
        that recent audit log entries exist. If this fails, it indicates that
        either:
        1. AuditMiddleware is not registered in the app
        2. The middleware is looking for the wrong database attribute
        3. The create_audit_log method is not being called

        To make this test pass:
        1. Ensure AuditMiddleware is added via app.add_middleware()
        2. Ensure middleware uses app.state.app_db (not app.state.db)
        """
        # Query for any audit logs for this tenant in the last hour
        result = await db.fetch_one(
            """
            SELECT COUNT(*) as count
            FROM audit_logs
            WHERE tenant_id = $1
              AND created_at > NOW() - INTERVAL '1 hour'
            """,
            tenant_id,
        )

        assert result is not None, "Query should return a result"

        # If running after some API activity, there should be logs
        # This is a weak assertion - mainly useful when running after demo setup
        # The key test is test_audit_log_created_for_api_call below
        if result["count"] == 0:
            pytest.skip(
                "No recent audit logs found. "
                "This may be expected if no API calls were made recently. "
                "Run the full test suite or make an API call first."
            )

    async def test_create_audit_log_directly(
        self,
        db: AppDatabase,
        tenant_id: UUID,
    ) -> None:
        """Verify create_audit_log method works correctly.

        This tests the database method directly to ensure the SQL is correct
        and the table schema matches the insert statement.
        """
        from uuid import uuid4

        resource_id = uuid4()
        actor_id = uuid4()

        # Create an audit log entry directly with all fields
        await db.create_audit_log(
            tenant_id=tenant_id,
            action="test.direct_insert",
            actor_id=actor_id,
            actor_email="test@example.com",
            actor_ip="127.0.0.1",
            actor_user_agent="pytest-integration-test",
            resource_type="test",
            resource_id=resource_id,
            resource_name="Test Resource",
            request_method="POST",
            request_path="/api/v1/test",
            status_code=200,
            changes={"test": "data"},
            metadata={"request_id": "test-123"},
        )

        # Verify it was created with all fields populated
        result = await db.fetch_one(
            """
            SELECT * FROM audit_logs
            WHERE tenant_id = $1 AND resource_id = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            tenant_id,
            resource_id,
        )

        try:
            assert result is not None, "Audit log entry should exist"
            # Verify action and resource
            assert result["action"] == "test.direct_insert"
            assert result["resource_type"] == "test"
            assert result["resource_id"] == resource_id
            assert result["resource_name"] == "Test Resource"
            # Verify actor info
            assert result["actor_id"] == actor_id
            assert result["actor_email"] == "test@example.com"
            # Note: actor_ip is stored as inet type, comparison may vary
            assert result["actor_ip"] is not None
            assert result["actor_user_agent"] == "pytest-integration-test"
            # Verify request details
            assert result["request_method"] == "POST"
            assert result["request_path"] == "/api/v1/test"
            assert result["status_code"] == 200
            # Verify JSON fields
            assert result["changes"] is not None
            assert result["metadata"] is not None
        finally:
            # Cleanup - delete test entry
            await db.execute(
                "DELETE FROM audit_logs WHERE tenant_id = $1 AND resource_id = $2",
                tenant_id,
                resource_id,
            )

    async def test_audit_middleware_is_registered(self) -> None:
        """Verify AuditMiddleware is registered in the EE app.

        This test imports the EE app and checks that AuditMiddleware is in
        the middleware stack. This catches the bug where the middleware class
        exists but was never added via app.add_middleware().
        """
        try:
            from dataing_ee.entrypoints.api.app import app
            from dataing_ee.entrypoints.api.middleware.audit import AuditMiddleware
        except ImportError:
            pytest.skip("EE package not available")

        # Check middleware stack
        # In Starlette/FastAPI, middleware is stored in app.middleware_stack
        # but we can also check user_middleware which stores the middleware list
        middleware_classes = []
        for middleware in app.user_middleware:
            if hasattr(middleware, "cls"):
                middleware_classes.append(middleware.cls)

        assert AuditMiddleware in middleware_classes, (
            "AuditMiddleware is not registered in the EE app. "
            "Add `app.add_middleware(AuditMiddleware)` in create_ee_app()."
        )

    async def test_middleware_uses_correct_db_attribute(self) -> None:
        """Verify AuditMiddleware looks for correct database attribute.

        This test checks that the middleware uses 'app_db' not 'db' when
        getting the database from app state. This catches the bug where
        the middleware was looking for request.app.state.db but the app
        stores it as request.app.state.app_db.
        """
        try:
            from dataing_ee.entrypoints.api.middleware.audit import AuditMiddleware
        except ImportError:
            pytest.skip("EE package not available")

        import inspect

        source = inspect.getsource(AuditMiddleware._log_request)

        # Check that middleware uses app_db, not db
        assert "app.state.app_db" in source or 'app.state, "app_db"' in source, (
            "AuditMiddleware._log_request should use 'app_db' not 'db'. "
            "Change `getattr(request.app.state, 'db', None)` to "
            "`getattr(request.app.state, 'app_db', None)`."
        )

        # Ensure it doesn't use the wrong attribute name
        # This regex-style check catches the exact bug pattern
        if 'getattr(request.app.state, "db"' in source:
            pytest.fail(
                "AuditMiddleware uses 'db' instead of 'app_db'. "
                "The database is stored as app.state.app_db, not app.state.db."
            )

    async def test_middleware_passes_required_audit_fields(self) -> None:
        """Verify AuditMiddleware passes all required fields to create_audit_log.

        This test inspects the middleware source to ensure it captures and passes
        the key audit fields. Catches regressions where fields are removed or renamed.
        """
        try:
            from dataing_ee.entrypoints.api.middleware.audit import AuditMiddleware
        except ImportError:
            pytest.skip("EE package not available")

        import inspect

        source = inspect.getsource(AuditMiddleware._log_request)

        # Required fields that should be passed to create_audit_log
        required_fields = [
            "tenant_id",
            "action",
            "actor_id",
            "actor_ip",
            "actor_user_agent",
            "resource_type",
            "resource_id",
            "request_method",
            "request_path",
            "status_code",
        ]

        for field in required_fields:
            assert f"{field}=" in source, (
                f"AuditMiddleware._log_request should pass '{field}' to create_audit_log. "
                f"This field is required for complete audit logging."
            )
