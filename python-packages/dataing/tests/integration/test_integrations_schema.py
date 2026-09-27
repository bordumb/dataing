"""Integration tests for the integrations table schema (needs a migrated database)."""

import os
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import asyncpg
import pytest

from dataing.adapters.db.app_db import AppDatabase


@pytest.mark.integration
class TestIntegrationSigningSecret:
    """Webhook verification fails closed, so every integration must have a secret."""

    @pytest.fixture
    async def db(self) -> AsyncGenerator[AppDatabase, None]:
        """Create database connection."""
        dsn = os.getenv(
            "DATABASE_URL",
            "postgresql://dataing:dataing@localhost:5432/dataing_demo",
        )
        db = AppDatabase(dsn=dsn)
        try:
            await db.connect()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")
        yield db
        await db.close()

    @pytest.fixture
    async def tenant_id(self, db: AppDatabase) -> AsyncGenerator[UUID, None]:
        """Create a throwaway tenant; deleting it cascades to its integrations."""
        tenant_id = uuid4()
        try:
            await db.execute(
                "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
                tenant_id,
                "Test Tenant",
                f"test-tenant-{tenant_id.hex[:8]}",
            )
        except Exception as e:
            pytest.skip(f"Database schema not available: {e}")
        yield tenant_id
        await db.execute("DELETE FROM tenants WHERE id = $1", tenant_id)

    async def test_integration_without_signing_secret_is_rejected(
        self, db: AppDatabase, tenant_id: UUID
    ) -> None:
        """An integration row cannot be stored without a signing secret."""
        with pytest.raises(asyncpg.NotNullViolationError):
            await db.execute(
                "INSERT INTO integrations (tenant_id, name, provider) VALUES ($1, $2, $3)",
                tenant_id,
                "No secret",
                "custom",
            )
