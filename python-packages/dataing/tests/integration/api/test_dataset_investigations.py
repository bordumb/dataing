"""Integration tests for GET /datasets/{dataset_id}/investigations on the migrated schema."""

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
from dataing.entrypoints.api.routes.datasets import router

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


async def _create_datasource(db: AppDatabase, tenant_id: UUID) -> UUID:
    datasource_id = uuid4()
    await db.execute(
        """INSERT INTO data_sources (id, tenant_id, name, type, connection_config_encrypted)
           VALUES ($1, $2, $3, 'postgresql', 'unused')""",
        datasource_id,
        tenant_id,
        f"warehouse-{datasource_id.hex[:8]}",
    )
    return datasource_id


async def _create_dataset(
    db: AppDatabase, tenant_id: UUID, datasource_id: UUID, native_path: str
) -> UUID:
    dataset_id = uuid4()
    schema_name, name = native_path.split(".")
    await db.execute(
        """INSERT INTO datasets (id, tenant_id, datasource_id, native_path, name, schema_name)
           VALUES ($1, $2, $3, $4, $5, $6)""",
        dataset_id,
        tenant_id,
        datasource_id,
        native_path,
        name,
        schema_name,
    )
    return dataset_id


async def _create_investigation(
    db: AppDatabase,
    tenant_id: UUID,
    datasource_id: UUID,
    dataset_ids: list[str],
    *,
    display_name: str = "null_rate on customer_id",
    severity: str = "high",
    created_at: datetime = CREATED_AT,
) -> UUID:
    """Store an investigation exactly as POST /investigations does."""
    alert = AnomalyAlert(
        dataset_ids=dataset_ids,
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
    alert_dict = alert.model_dump(mode="json")
    alert_dict["datasource_id"] = str(datasource_id)

    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert, created_at) VALUES ($1, $2, $3, $4)",
        investigation_id,
        tenant_id,
        json.dumps(alert_dict),
        created_at,
    )
    return investigation_id


async def _get_dataset_investigations(
    db: AppDatabase, tenant_id: UUID, dataset_id: UUID, **params: Any
) -> dict[str, Any]:
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
        response = await client.get(f"/api/v1/datasets/{dataset_id}/investigations", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _ids(body: dict[str, Any]) -> list[str]:
    return [investigation["id"] for investigation in body["investigations"]]


async def test_returns_summaries_of_investigations_on_the_dataset(migrated_db: AppDatabase) -> None:
    """Each summary carries what the dataset page's Investigations tab renders."""
    tenant_id = await _create_tenant(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    dataset_id = await _create_dataset(migrated_db, tenant_id, datasource_id, "public.orders")
    investigation_id = await _create_investigation(
        migrated_db, tenant_id, datasource_id, ["public.orders"]
    )

    body = await _get_dataset_investigations(migrated_db, tenant_id, dataset_id)

    assert body == {
        "investigations": [
            {
                "id": str(investigation_id),
                "metric_name": "null_rate on customer_id",
                "status": "active",
                "severity": "high",
                "created_at": CREATED_AT.isoformat(),
            }
        ],
        "total": 1,
    }


@pytest.mark.parametrize(
    "dataset_ids",
    [
        pytest.param(["public.orders", "public.customers"], id="primary"),
        pytest.param(["public.customers", "public.orders"], id="reference"),
        pytest.param(["PUBLIC.Orders"], id="native-path-any-case"),
        pytest.param(["orders"], id="bare-table-name"),
    ],
)
async def test_matches_dataset_ids_the_workflow_resolves_to_the_dataset(
    migrated_db: AppDatabase, dataset_ids: list[str]
) -> None:
    """Alert dataset ids match like SchemaLookupAdapter resolves tables."""
    tenant_id = await _create_tenant(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    dataset_id = await _create_dataset(migrated_db, tenant_id, datasource_id, "public.orders")
    investigation_id = await _create_investigation(
        migrated_db, tenant_id, datasource_id, dataset_ids
    )

    body = await _get_dataset_investigations(migrated_db, tenant_id, dataset_id)

    assert _ids(body) == [str(investigation_id)]


async def test_excludes_other_datasets_datasources_and_tenants(migrated_db: AppDatabase) -> None:
    """Only investigations on this dataset, in its datasource and tenant, are listed."""
    tenant_id = await _create_tenant(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    other_datasource_id = await _create_datasource(migrated_db, tenant_id)
    dataset_id = await _create_dataset(migrated_db, tenant_id, datasource_id, "public.orders")
    await _create_dataset(migrated_db, tenant_id, other_datasource_id, "public.orders")
    other_tenant_id = await _create_tenant(migrated_db)

    expected = await _create_investigation(migrated_db, tenant_id, datasource_id, ["public.orders"])
    await _create_investigation(migrated_db, tenant_id, datasource_id, ["public.customers"])
    await _create_investigation(migrated_db, tenant_id, other_datasource_id, ["public.orders"])
    await _create_investigation(migrated_db, other_tenant_id, datasource_id, ["public.orders"])

    body = await _get_dataset_investigations(migrated_db, tenant_id, dataset_id)

    assert _ids(body) == [str(expected)]


async def test_lists_newest_first_up_to_limit(migrated_db: AppDatabase) -> None:
    """Investigations come back newest first, capped at the requested limit."""
    tenant_id = await _create_tenant(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    dataset_id = await _create_dataset(migrated_db, tenant_id, datasource_id, "public.orders")
    _oldest, middle, newest = [
        await _create_investigation(
            migrated_db,
            tenant_id,
            datasource_id,
            ["public.orders"],
            created_at=CREATED_AT + timedelta(hours=hours),
        )
        for hours in (0, 1, 2)
    ]

    body = await _get_dataset_investigations(migrated_db, tenant_id, dataset_id, limit=2)

    assert _ids(body) == [str(newest), str(middle)]


async def test_metric_name_falls_back_to_anomaly_type(migrated_db: AppDatabase) -> None:
    """An alert without a metric display name is labelled by its anomaly type."""
    tenant_id = await _create_tenant(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    dataset_id = await _create_dataset(migrated_db, tenant_id, datasource_id, "public.orders")
    await _create_investigation(
        migrated_db, tenant_id, datasource_id, ["public.orders"], display_name=""
    )

    body = await _get_dataset_investigations(migrated_db, tenant_id, dataset_id)

    assert [i["metric_name"] for i in body["investigations"]] == ["null_rate"]
