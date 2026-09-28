"""Integration tests for the integrations table schema (needs a migrated database)."""

from uuid import UUID, uuid4

import asyncpg
import pytest

from dataing.adapters.db.app_db import AppDatabase


@pytest.mark.integration
class TestIntegrationSigningSecret:
    """Webhook verification fails closed, so every integration must have a secret."""

    @pytest.fixture
    async def tenant_id(self, migrated_db: AppDatabase) -> UUID:
        """Create a throwaway tenant for the integration rows."""
        tenant_id = uuid4()
        await migrated_db.execute(
            "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
            tenant_id,
            "Test Tenant",
            f"test-tenant-{tenant_id.hex[:12]}",
        )
        return tenant_id

    async def test_integration_without_signing_secret_is_rejected(
        self, migrated_db: AppDatabase, tenant_id: UUID
    ) -> None:
        """An integration row cannot be stored without a signing secret."""
        with pytest.raises(asyncpg.NotNullViolationError):
            await migrated_db.execute(
                "INSERT INTO integrations (tenant_id, name, provider) VALUES ($1, $2, $3)",
                tenant_id,
                "No secret",
                "custom",
            )
