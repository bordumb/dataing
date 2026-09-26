"""Fixtures shared by the adapter integration tests."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase


@pytest.fixture
async def tenant_id(migrated_db: AppDatabase) -> UUID:
    """A new tenant, so each test only sees the rows it creates."""
    tenant_id = uuid4()
    await migrated_db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-tenant-{tenant_id.hex[:12]}",
    )
    return tenant_id


@pytest.fixture
async def dataset_id(migrated_db: AppDatabase, tenant_id: UUID) -> UUID:
    """A dataset owned by the test tenant, registered under a new datasource."""
    datasource_id = uuid4()
    await migrated_db.execute(
        """INSERT INTO data_sources (id, tenant_id, name, type, connection_config_encrypted)
           VALUES ($1, $2, $3, 'postgresql', 'unused')""",
        datasource_id,
        tenant_id,
        f"warehouse-{datasource_id.hex[:8]}",
    )
    dataset_id = uuid4()
    table = f"dataset_{dataset_id.hex[:8]}"
    await migrated_db.execute(
        """INSERT INTO datasets (id, tenant_id, datasource_id, native_path, name, schema_name)
           VALUES ($1, $2, $3, $4, $5, 'test')""",
        dataset_id,
        tenant_id,
        datasource_id,
        f"test.{table}",
        table,
    )
    return dataset_id
