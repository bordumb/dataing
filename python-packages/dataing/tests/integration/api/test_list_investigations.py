"""Integration tests for GET /investigations on the migrated schema."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.investigations import router

pytestmark = pytest.mark.integration

CREATED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


async def _create_tenant(db: AppDatabase) -> UUID:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    return tenant_id


async def _create_investigation(
    db: AppDatabase,
    tenant_id: UUID,
    dataset_ids: list[str],
    *,
    created_at: datetime = CREATED_AT,
) -> UUID:
    """Store an investigation exactly as POST /investigations does."""
    alert = AnomalyAlert(
        dataset_ids=dataset_ids,
        metric_spec=MetricSpec.from_column("customer_id"),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.25,
        deviation_pct=2400.0,
        anomaly_date="2026-09-01",
        severity="high",
    )
    alert_dict = alert.model_dump(mode="json")
    alert_dict["datasource_id"] = str(uuid4())

    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert, created_at) VALUES ($1, $2, $3, $4)",
        investigation_id,
        tenant_id,
        json.dumps(alert_dict),
        created_at,
    )
    return investigation_id


async def _list_investigations(db: AppDatabase, tenant_id: UUID) -> list[dict[str, Any]]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.app_db = db
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="test",
        tenant_name="Test Tenant",
        user_id=None,
        scopes=["read"],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/investigations")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()
    return items


async def test_lists_the_primary_dataset_of_each_investigation(migrated_db: AppDatabase) -> None:
    """dataset_id is the alert's first dataset; reference tables after it are not listed."""
    tenant_id = await _create_tenant(migrated_db)
    older = await _create_investigation(
        migrated_db, tenant_id, ["public.orders", "public.customers"], created_at=CREATED_AT
    )
    newer_created_at = CREATED_AT + timedelta(hours=1)
    newer = await _create_investigation(
        migrated_db, tenant_id, ["public.customers"], created_at=newer_created_at
    )

    items = await _list_investigations(migrated_db, tenant_id)

    assert items == [
        {
            "investigation_id": str(newer),
            "status": "active",
            "created_at": newer_created_at.isoformat(),
            "dataset_id": "public.customers",
        },
        {
            "investigation_id": str(older),
            "status": "active",
            "created_at": CREATED_AT.isoformat(),
            "dataset_id": "public.orders",
        },
    ]


async def test_alert_without_datasets_lists_unknown_dataset(migrated_db: AppDatabase) -> None:
    """An alert with no dataset_ids lists as "unknown", like AnomalyAlert.dataset_id."""
    tenant_id = await _create_tenant(migrated_db)
    await _create_investigation(migrated_db, tenant_id, [])

    items = await _list_investigations(migrated_db, tenant_id)

    assert [item["dataset_id"] for item in items] == ["unknown"]
