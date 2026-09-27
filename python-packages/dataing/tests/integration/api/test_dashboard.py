"""Integration tests for the /dashboard routes on the migrated schema."""

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
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.dashboard import router

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


async def _create_datasource(db: AppDatabase, tenant_id: UUID, *, is_active: bool = True) -> UUID:
    datasource_id = uuid4()
    await db.execute(
        """INSERT INTO data_sources
               (id, tenant_id, name, type, connection_config_encrypted, is_active)
           VALUES ($1, $2, $3, 'postgresql', 'unused', $4)""",
        datasource_id,
        tenant_id,
        f"warehouse-{datasource_id.hex[:8]}",
        is_active,
    )
    return datasource_id


def _alert(
    datasource_id: UUID,
    *,
    dataset_ids: list[str] | None = None,
    display_name: str = "null_rate on customer_id",
    severity: str = "high",
) -> dict[str, Any]:
    """An alert as POST /investigations stores it."""
    alert = AnomalyAlert(
        dataset_ids=dataset_ids or ["public.orders"],
        metric_spec=MetricSpec(
            metric_type="column",
            expression="customer_id",
            display_name=display_name,
            columns_referenced=["customer_id"],
        ),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.25,
        deviation_pct=2400.0,
        anomaly_date="2026-09-01",
        severity=severity,
    )
    return {**alert.model_dump(mode="json"), "datasource_id": str(datasource_id)}


async def _create_investigation(
    db: AppDatabase,
    tenant_id: UUID,
    alert: dict[str, Any],
    *,
    created_at: datetime = CREATED_AT,
) -> UUID:
    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert, created_at) VALUES ($1, $2, $3, $4)",
        investigation_id,
        tenant_id,
        json.dumps(alert),
        created_at,
    )
    return investigation_id


async def _complete(
    db: AppDatabase, investigation_id: UUID, *, status: str = "completed", days_ago: int = 0
) -> None:
    """Record an outcome, as if the investigation finished `days_ago` days ago."""
    await db.execute(
        "UPDATE investigations SET outcome = $2 WHERE id = $1",
        investigation_id,
        json.dumps({"status": status}),
    )
    if days_ago:
        await db.execute(
            "UPDATE investigations SET completed_at = NOW() - make_interval(days => $2) "
            "WHERE id = $1",
            investigation_id,
            days_ago,
        )


async def _get(db: AppDatabase, tenant_id: UUID, path: str) -> dict[str, Any]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: db
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
        response = await client.get(f"/api/v1/dashboard{path}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_stats_count_the_tenants_active_and_completed_today(
    migrated_db: AppDatabase,
) -> None:
    """Active means no outcome yet; completed today means the outcome was set today."""
    tenant_id = await _create_tenant(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    await _create_datasource(migrated_db, tenant_id)
    await _create_datasource(migrated_db, tenant_id, is_active=False)
    alert = _alert(datasource_id)
    for _ in range(2):
        await _create_investigation(migrated_db, tenant_id, alert)
    await _complete(migrated_db, await _create_investigation(migrated_db, tenant_id, alert))
    await _complete(
        migrated_db,
        await _create_investigation(migrated_db, tenant_id, alert),
        status="failed",
    )
    await _complete(
        migrated_db, await _create_investigation(migrated_db, tenant_id, alert), days_ago=2
    )
    other_tenant_id = await _create_tenant(migrated_db)
    await _create_investigation(migrated_db, other_tenant_id, alert)
    await _complete(migrated_db, await _create_investigation(migrated_db, other_tenant_id, alert))

    stats = await _get(migrated_db, tenant_id, "/stats")

    assert stats == {"active_investigations": 2, "completed_today": 2, "data_sources": 2}


async def test_dashboard_lists_recent_investigations_from_their_alerts(
    migrated_db: AppDatabase,
) -> None:
    """Recent investigations are summarised from the alert JSONB, newest first."""
    tenant_id = await _create_tenant(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    active = await _create_investigation(
        migrated_db,
        tenant_id,
        _alert(datasource_id, dataset_ids=["public.orders", "public.customers"]),
    )
    failed = await _create_investigation(
        migrated_db,
        tenant_id,
        _alert(datasource_id, display_name="", severity="low"),
        created_at=CREATED_AT + timedelta(hours=1),
    )
    await _complete(migrated_db, failed, status="failed")
    # POST /investigations/import stores replays with an alert that is not an AnomalyAlert
    replay = await _create_investigation(
        migrated_db,
        tenant_id,
        {"replay_of": str(uuid4()), "is_replay": True},
        created_at=CREATED_AT + timedelta(hours=2),
    )
    await _complete(migrated_db, replay)

    body = await _get(migrated_db, tenant_id, "/")

    assert body["recent_investigations"] == [
        {
            "id": str(replay),
            "dataset_id": "unknown",
            "metric_name": "unknown",
            "status": "completed",
            "severity": None,
            "created_at": (CREATED_AT + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        },
        {
            "id": str(failed),
            "dataset_id": "public.orders",
            "metric_name": "null_rate",
            "status": "failed",
            "severity": "low",
            "created_at": (CREATED_AT + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        },
        {
            "id": str(active),
            "dataset_id": "public.orders",
            "metric_name": "null_rate on customer_id",
            "status": "active",
            "severity": "high",
            "created_at": CREATED_AT.isoformat().replace("+00:00", "Z"),
        },
    ]
    assert body["stats"] == {"active_investigations": 1, "completed_today": 2, "data_sources": 1}
