"""Integration tests for POST /runbooks/from-issue/{issue_id} on the migrated schema."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from dataing_ee.entrypoints.api.routes.runbooks import router
from fastapi import FastAPI

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

pytestmark = pytest.mark.integration

RESOLUTION_NOTE = "Re-ran the orders load after the upstream export landed"
OUTCOME = {
    "status": "completed",
    "root_cause": "The 02:00 orders load ran before the upstream export finished",
    "recommendations": [
        {
            "description": "Gate the orders load on the upstream export sensor",
            "type": "preventive",
        }
    ],
    "tags": ["late-data"],
}


async def _create_tenant(db: AppDatabase) -> UUID:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    return tenant_id


async def _create_resolved_issue(db: AppDatabase, tenant_id: UUID) -> UUID:
    issue_id = uuid4()
    await db.execute(
        """INSERT INTO issues
               (id, tenant_id, number, title, description, status, dataset_id, resolution_note)
           VALUES ($1, $2, 1, $3, $4, 'resolved', 'public.orders', $5)""",
        issue_id,
        tenant_id,
        "Null spike in orders.customer_id",
        "customer_id is null on a quarter of today's orders",
        RESOLUTION_NOTE,
    )
    for label in ("orders", "null-rate"):
        await db.execute(
            "INSERT INTO issue_labels (issue_id, label) VALUES ($1, $2)", issue_id, label
        )
    return issue_id


async def _investigate(
    db: AppDatabase,
    tenant_id: UUID,
    issue_id: UUID,
    outcome: dict[str, Any],
    *,
    spawned_at: datetime,
) -> UUID:
    """Store an investigation spawned from the issue, with its final outcome."""
    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert, outcome) VALUES ($1, $2, $3, $4)",
        investigation_id,
        tenant_id,
        json.dumps({"dataset_ids": ["public.orders"]}),
        json.dumps(outcome),
    )
    await db.execute(
        """INSERT INTO issue_investigation_runs
               (issue_id, investigation_id, trigger_type, created_at)
           VALUES ($1, $2, 'human', $3)""",
        issue_id,
        investigation_id,
        spawned_at,
    )
    return investigation_id


async def _generate(db: AppDatabase, tenant_id: UUID, issue_id: UUID) -> dict[str, Any]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: db
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="test",
        tenant_name="Test Tenant",
        user_id=None,
        scopes=["read", "write"],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/runbooks/from-issue/{issue_id}", json={"publish": False}
        )
    assert response.status_code == 201, response.text
    runbook: dict[str, Any] = response.json()
    return runbook


async def test_runbook_is_built_from_the_issue_and_its_latest_investigation(
    migrated_db: AppDatabase,
) -> None:
    """The issue's resolution and labels, and the latest run's outcome, fill the runbook."""
    tenant_id = await _create_tenant(migrated_db)
    issue_id = await _create_resolved_issue(migrated_db, tenant_id)
    now = datetime.now(UTC)
    await _investigate(
        migrated_db,
        tenant_id,
        issue_id,
        {"status": "failed", "root_cause": "inconclusive"},
        spawned_at=now - timedelta(hours=1),
    )
    investigation_id = await _investigate(migrated_db, tenant_id, issue_id, OUTCOME, spawned_at=now)

    runbook = await _generate(migrated_db, tenant_id, issue_id)

    assert runbook["created_from_issue_id"] == str(issue_id)
    assert runbook["created_from_investigation_id"] == str(investigation_id)
    assert runbook["dataset_id"] == "public.orders"
    assert runbook["root_cause"] == OUTCOME["root_cause"]
    assert [step["description"] for step in runbook["fix_steps"]] == [
        RESOLUTION_NOTE,
        "Gate the orders load on the upstream export sensor",
    ]
    assert runbook["prevention_notes"] == "Gate the orders load on the upstream export sensor"
    assert sorted(runbook["labels"]) == ["late-data", "null-rate", "orders"]


async def test_runbook_without_an_investigation_uses_the_issue_alone(
    migrated_db: AppDatabase,
) -> None:
    """An issue resolved without an investigation still yields a runbook."""
    tenant_id = await _create_tenant(migrated_db)
    issue_id = await _create_resolved_issue(migrated_db, tenant_id)

    runbook = await _generate(migrated_db, tenant_id, issue_id)

    assert runbook["created_from_investigation_id"] is None
    assert runbook["root_cause"] is None
    assert [step["description"] for step in runbook["fix_steps"]] == [RESOLUTION_NOTE]
    assert sorted(runbook["labels"]) == ["null-rate", "orders"]
