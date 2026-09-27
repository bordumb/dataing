"""Integration tests for POST /issues/{issue_id}/investigation-runs on the migrated schema."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.domain_types import AnomalyAlert
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.issues import router

pytestmark = pytest.mark.integration

ISSUE_CREATED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
FOCUS_PROMPT = "Did the checkout service stop sending customer ids?"


async def _create_tenant(db: AppDatabase) -> UUID:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    return tenant_id


async def _create_user(db: AppDatabase) -> UUID:
    user_id = uuid4()
    await db.execute(
        "INSERT INTO users (id, email) VALUES ($1, $2)",
        user_id,
        f"{user_id.hex[:12]}@example.com",
    )
    return user_id


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


async def _create_issue(
    db: AppDatabase,
    tenant_id: UUID,
    *,
    title: str = "Orders missing customer ids",
    severity: str | None = "high",
    dataset_id: str = "public.orders",
) -> UUID:
    issue_id = uuid4()
    await db.execute(
        """INSERT INTO issues (id, tenant_id, number, title, severity, dataset_id, created_at)
           VALUES ($1, $2, 1, $3, $4, $5, $6)""",
        issue_id,
        tenant_id,
        title,
        severity,
        dataset_id,
        ISSUE_CREATED_AT,
    )
    return issue_id


async def _spawn_investigation(
    db: AppDatabase, tenant_id: UUID, user_id: UUID, issue_id: UUID, body: dict[str, Any]
) -> tuple[dict[str, Any], AsyncMock]:
    """POST the investigation run with Temporal replaced by a mock that records the start."""
    temporal = AsyncMock()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.app_db = db
    app.state.temporal_client = temporal
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="test",
        tenant_name="Test Tenant",
        user_id=user_id,
        scopes=["read", "write"],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/issues/{issue_id}/investigation-runs", json=body)
    assert response.status_code == 201, response.text
    run: dict[str, Any] = response.json()
    return run, temporal


async def _stored_alert(db: AppDatabase, investigation_id: str) -> dict[str, Any]:
    row = await db.fetch_one(
        "SELECT alert FROM investigations WHERE id = $1", UUID(investigation_id)
    )
    assert row is not None
    alert = row["alert"]
    stored: dict[str, Any] = json.loads(alert) if isinstance(alert, str) else alert
    return stored


@pytest.mark.parametrize(
    ("request_dataset_id", "expected_dataset_ids"),
    [
        pytest.param(None, ["public.orders"], id="issue-dataset"),
        pytest.param("public.customers", ["public.customers"], id="request-dataset"),
    ],
)
async def test_spawned_investigation_runs_on_a_valid_anomaly_alert(
    migrated_db: AppDatabase,
    request_dataset_id: str | None,
    expected_dataset_ids: list[str],
) -> None:
    """The workflow gets the stored alert, which gather_context validates as an AnomalyAlert."""
    tenant_id = await _create_tenant(migrated_db)
    user_id = await _create_user(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    issue_id = await _create_issue(migrated_db, tenant_id, dataset_id="public.orders")
    body: dict[str, Any] = {"focus_prompt": FOCUS_PROMPT, "datasource_id": str(datasource_id)}
    if request_dataset_id is not None:
        body["dataset_id"] = request_dataset_id

    run, temporal = await _spawn_investigation(migrated_db, tenant_id, user_id, issue_id, body)

    stored = await _stored_alert(migrated_db, run["investigation_id"])
    temporal.start_investigation.assert_awaited_once()
    assert temporal.start_investigation.await_args.kwargs["alert_data"] == stored
    alert = AnomalyAlert.model_validate(stored)
    assert alert.dataset_ids == expected_dataset_ids
    assert stored["datasource_id"] == str(datasource_id)


@pytest.mark.parametrize(
    ("issue_severity", "alert_severity"),
    [
        pytest.param("critical", "critical", id="issue-severity"),
        pytest.param(None, "medium", id="no-issue-severity"),
    ],
)
async def test_spawned_alert_describes_the_issue_and_focus(
    migrated_db: AppDatabase, issue_severity: str | None, alert_severity: str
) -> None:
    """The focus prompt is the metric description the agents investigate; the issue is linked."""
    tenant_id = await _create_tenant(migrated_db)
    user_id = await _create_user(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    issue_id = await _create_issue(
        migrated_db, tenant_id, title="Orders missing customer ids", severity=issue_severity
    )

    run, _ = await _spawn_investigation(
        migrated_db,
        tenant_id,
        user_id,
        issue_id,
        {"focus_prompt": FOCUS_PROMPT, "datasource_id": str(datasource_id)},
    )

    assert await _stored_alert(migrated_db, run["investigation_id"]) == {
        "dataset_ids": ["public.orders"],
        "metric_spec": {
            "metric_type": "description",
            "expression": FOCUS_PROMPT,
            "display_name": "Orders missing customer ids",
            "columns_referenced": [],
            "source_url": None,
        },
        "anomaly_type": "custom",
        "expected_value": 0.0,
        "actual_value": 0.0,
        "deviation_pct": 0.0,
        "anomaly_date": "2026-09-01",
        "severity": alert_severity,
        "source_system": None,
        "source_alert_id": None,
        "source_url": None,
        "metadata": None,
        "datasource_id": str(datasource_id),
        "issue_id": str(issue_id),
        "focus_prompt": FOCUS_PROMPT,
    }
