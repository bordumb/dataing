"""Integration tests for PermissionService datasource grants on the migrated schema."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.rbac.permission_service import PermissionService

pytestmark = pytest.mark.integration


async def _create_org(db: AppDatabase) -> UUID:
    """An org is a tenant and an organization with the same id (the JWT org_id)."""
    org_id = uuid4()
    slug = f"test-{org_id.hex[:12]}"
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, 'Test Org', $2)", org_id, slug
    )
    await db.execute(
        "INSERT INTO organizations (id, name, slug) VALUES ($1, 'Test Org', $2)", org_id, slug
    )
    return org_id


async def _create_member(db: AppDatabase, org_id: UUID) -> UUID:
    user_id = uuid4()
    await db.execute(
        "INSERT INTO users (id, email) VALUES ($1, $2)", user_id, f"{user_id.hex[:12]}@example.com"
    )
    await db.execute(
        "INSERT INTO org_memberships (user_id, org_id, role) VALUES ($1, $2, 'member')",
        user_id,
        org_id,
    )
    return user_id


async def _create_datasource(db: AppDatabase, org_id: UUID) -> UUID:
    datasource_id = uuid4()
    await db.execute(
        """INSERT INTO data_sources (id, tenant_id, name, type, connection_config_encrypted)
           VALUES ($1, $2, $3, 'postgresql', 'unused')""",
        datasource_id,
        org_id,
        f"warehouse-{datasource_id.hex[:8]}",
    )
    return datasource_id


async def _create_investigation(db: AppDatabase, org_id: UUID, datasource_id: UUID) -> UUID:
    """Store an investigation the way POST /investigations does."""
    alert = AnomalyAlert(
        dataset_ids=["public.orders"],
        metric_spec=MetricSpec.from_column("customer_id"),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.25,
        deviation_pct=2400.0,
        anomaly_date="2026-09-01",
        severity="high",
    )
    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert) VALUES ($1, $2, $3)",
        investigation_id,
        org_id,
        json.dumps({**alert.model_dump(mode="json"), "datasource_id": str(datasource_id)}),
    )
    return investigation_id


async def _assert_access_follows_datasource(
    db: AppDatabase, org_id: UUID, user_id: UUID, visible: UUID, hidden: UUID
) -> None:
    async with db.acquire() as conn:
        service = PermissionService(conn)
        assert await service.can_access_investigation(user_id, visible)
        assert not await service.can_access_investigation(user_id, hidden)
        assert await service.get_accessible_investigation_ids(user_id, org_id) == [visible]


async def test_user_datasource_grant_opens_that_datasources_investigations(
    migrated_db: AppDatabase,
) -> None:
    """A member granted a datasource sees the investigations that ran against it."""
    org_id = await _create_org(migrated_db)
    user_id = await _create_member(migrated_db, org_id)
    granted = await _create_datasource(migrated_db, org_id)
    other = await _create_datasource(migrated_db, org_id)
    visible = await _create_investigation(migrated_db, org_id, granted)
    hidden = await _create_investigation(migrated_db, org_id, other)
    await migrated_db.execute(
        "INSERT INTO permission_grants (org_id, user_id, data_source_id) VALUES ($1, $2, $3)",
        org_id,
        user_id,
        granted,
    )

    await _assert_access_follows_datasource(migrated_db, org_id, user_id, visible, hidden)


async def test_team_datasource_grant_opens_that_datasources_investigations(
    migrated_db: AppDatabase,
) -> None:
    """A member of a team granted a datasource sees the investigations that ran against it."""
    org_id = await _create_org(migrated_db)
    user_id = await _create_member(migrated_db, org_id)
    granted = await _create_datasource(migrated_db, org_id)
    other = await _create_datasource(migrated_db, org_id)
    visible = await _create_investigation(migrated_db, org_id, granted)
    hidden = await _create_investigation(migrated_db, org_id, other)
    team_id = uuid4()
    await migrated_db.execute(
        "INSERT INTO teams (id, org_id, name) VALUES ($1, $2, 'Data Platform')", team_id, org_id
    )
    await migrated_db.execute(
        "INSERT INTO team_members (team_id, user_id) VALUES ($1, $2)", team_id, user_id
    )
    await migrated_db.execute(
        "INSERT INTO permission_grants (org_id, team_id, data_source_id) VALUES ($1, $2, $3)",
        org_id,
        team_id,
        granted,
    )

    await _assert_access_follows_datasource(migrated_db, org_id, user_id, visible, hidden)
