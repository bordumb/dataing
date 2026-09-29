"""POST /investigations: every run lives in an issue (docs/specs/0001_issue_chat.md §7.11)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.adapters.db.issues import open_issue
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.investigations import router

pytestmark = pytest.mark.integration

SYMPTOM = "Completed orders dropped about 30% on 2026-09-14"
SDK_ALERT: dict[str, Any] = {
    "dataset_ids": ["public.orders"],
    "metric_spec": {
        "metric_type": "column",
        "expression": "customer_id",
        "display_name": "Null rate of customer_id",
        "columns_referenced": ["customer_id"],
    },
    "anomaly_type": "null_rate",
    "expected_value": 0.01,
    "actual_value": 0.4,
    "deviation_pct": 3900.0,
    "anomaly_date": "2026-09-14",
    "severity": "high",
}


async def _tenant(db: AppDatabase) -> UUID:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, 't', $2)", tenant_id, f"t-{tenant_id.hex}"
    )
    return tenant_id


async def _user(db: AppDatabase) -> UUID:
    user_id = uuid4()
    await db.execute(
        "INSERT INTO users (id, email) VALUES ($1, $2)", user_id, f"{user_id.hex[:12]}@example.com"
    )
    return user_id


async def _datasource(db: AppDatabase, tenant_id: UUID) -> UUID:
    datasource_id = uuid4()
    await db.execute(
        """INSERT INTO data_sources (id, tenant_id, name, type, connection_config_encrypted)
           VALUES ($1, $2, $3, 'postgresql', 'unused')""",
        datasource_id,
        tenant_id,
        f"warehouse-{datasource_id.hex[:8]}",
    )
    return datasource_id


async def _post(
    db: AppDatabase,
    tenant_id: UUID,
    body: dict[str, Any],
    *,
    user_id: UUID | None,
    temporal: AsyncMock | None = None,
) -> tuple[httpx.Response, AsyncMock]:
    """POST /investigations with Temporal replaced by a mock that records the start."""
    temporal = temporal or AsyncMock()
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
        response = await client.post("/api/v1/investigations", json=body)
    return response, temporal


async def _thread(db: AppDatabase, issue_id: UUID) -> list[dict[str, Any]]:
    threads = IssueThreadRepository(db)
    thread = await threads.ensure_shared_thread(issue_id)
    return await threads.list_messages(thread["id"])


async def _alert(db: AppDatabase, investigation_id: str) -> dict[str, Any]:
    row = await db.fetch_one(
        "SELECT alert FROM investigations WHERE id = $1", UUID(investigation_id)
    )
    assert row is not None
    alert: dict[str, Any] = json.loads(row["alert"])
    return alert


async def test_a_brief_opens_an_issue_and_starts_its_run(migrated_db: AppDatabase) -> None:
    """Investigate… from any page: one call opens the issue and starts the run in its thread."""
    tenant_id = await _tenant(migrated_db)
    user_id = await _user(migrated_db)
    datasource_id = await _datasource(migrated_db, tenant_id)

    response, temporal = await _post(
        migrated_db,
        tenant_id,
        {
            "brief": {"symptom": SYMPTOM, "scope": {"tables": ["public.orders"]}},
            "datasource_id": str(datasource_id),
        },
        user_id=user_id,
    )

    assert response.status_code == 200, response.text
    started = response.json()
    assert (started["issue_number"], started["status"]) == (1, "queued")
    assert started["main_branch_id"] == started["investigation_id"]
    issue_id = UUID(started["issue_id"])
    issue = await migrated_db.fetch_one("SELECT * FROM issues WHERE id = $1", issue_id)
    assert issue is not None
    assert (issue["title"], issue["dataset_id"], issue["created_by_user_id"]) == (
        SYMPTOM,
        "public.orders",
        user_id,
    )
    run = await migrated_db.fetch_one(
        "SELECT * FROM issue_investigation_runs WHERE id = $1", UUID(started["run_id"])
    )
    assert run is not None
    assert (run["issue_id"], str(run["investigation_id"]), run["trigger_type"]) == (
        issue_id,
        started["investigation_id"],
        "human",
    )
    opening, card = await _thread(migrated_db, issue_id)
    assert opening["payload"]["event_type"] == "created"
    assert (card["kind"], card["author_kind"], card["author_user_id"]) == (
        "investigation",
        "user",
        user_id,
    )
    assert card["payload"]["run_id"] == started["run_id"]
    stored = await _alert(migrated_db, started["investigation_id"])
    assert stored["issue_id"] == str(issue_id)
    assert temporal.start_investigation.await_args.kwargs["alert_data"] == stored


async def test_an_sdk_alert_opens_an_issue_attributed_to_dataing(
    migrated_db: AppDatabase,
) -> None:
    """A run from an API key without a person opens an issue by dataing, with a brief."""
    tenant_id = await _tenant(migrated_db)
    datasource_id = await _datasource(migrated_db, tenant_id)

    response, _ = await _post(
        migrated_db,
        tenant_id,
        {"alert": SDK_ALERT, "datasource_id": str(datasource_id)},
        user_id=None,
    )

    assert response.status_code == 200, response.text
    started = response.json()
    symptom = (
        "Null rate of customer_id on public.orders: expected 0.01, got 0.4 (+3900.0%) on 2026-09-14"
    )
    issue = await migrated_db.fetch_one(
        "SELECT * FROM issues WHERE id = $1", UUID(started["issue_id"])
    )
    assert issue is not None
    assert (issue["title"], issue["severity"], issue["created_by_user_id"]) == (
        symptom,
        "high",
        None,
    )
    assert issue["author_type"] == "integration"
    run = await migrated_db.fetch_one(
        "SELECT trigger_type, brief FROM issue_investigation_runs WHERE id = $1",
        UUID(started["run_id"]),
    )
    assert run is not None
    assert run["trigger_type"] == "api"
    brief = json.loads(run["brief"])
    assert brief["symptom"] == symptom
    assert brief["scope"]["tables"] == ["public.orders"]
    assert brief["scope"]["time_window"] == {
        "from": "2026-09-13T00:00:00Z",
        "to": "2026-09-15T00:00:00Z",
    }
    _, card = await _thread(migrated_db, UUID(started["issue_id"]))
    assert (card["author_kind"], card["author_user_id"]) == ("system", None)
    stored = await _alert(migrated_db, started["investigation_id"])
    assert stored["anomaly_type"] == "null_rate"
    assert stored["actual_value"] == 0.4


async def test_an_issue_id_adds_the_run_to_that_issue(migrated_db: AppDatabase) -> None:
    """Starting on an existing issue opens nothing new."""
    tenant_id = await _tenant(migrated_db)
    user_id = await _user(migrated_db)
    datasource_id = await _datasource(migrated_db, tenant_id)
    issue = await open_issue(
        migrated_db, tenant_id=tenant_id, title="Orders dropped", dataset_id="public.orders"
    )

    response, _ = await _post(
        migrated_db,
        tenant_id,
        {"alert": SDK_ALERT, "issue_id": str(issue["id"]), "datasource_id": str(datasource_id)},
        user_id=user_id,
    )

    assert response.status_code == 200, response.text
    assert response.json()["issue_id"] == str(issue["id"])
    count = await migrated_db.fetch_one(
        "SELECT COUNT(*)::int AS n FROM issues WHERE tenant_id = $1", tenant_id
    )
    assert count is not None
    assert count["n"] == 1


async def test_an_unknown_issue_is_not_found(migrated_db: AppDatabase) -> None:
    """An issue_id from another tenant, or none at all, is a 404."""
    tenant_id = await _tenant(migrated_db)
    datasource_id = await _datasource(migrated_db, tenant_id)

    response, temporal = await _post(
        migrated_db,
        tenant_id,
        {
            "brief": {"symptom": SYMPTOM},
            "issue_id": str(uuid4()),
            "datasource_id": str(datasource_id),
        },
        user_id=None,
    )

    assert response.status_code == 404
    temporal.start_investigation.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="neither"),
        pytest.param({"brief": {"symptom": SYMPTOM}, "alert": SDK_ALERT}, id="both"),
        pytest.param(
            {"alert": {k: v for k, v in SDK_ALERT.items() if k != "anomaly_type"}},
            id="malformed-alert",
        ),
    ],
)
async def test_the_request_needs_exactly_one_valid_brief_or_alert(
    migrated_db: AppDatabase, body: dict[str, Any]
) -> None:
    """A bad request is a 422, not a 500."""
    tenant_id = await _tenant(migrated_db)

    response, _ = await _post(migrated_db, tenant_id, body, user_id=None)

    assert response.status_code == 422


async def test_a_brief_without_any_table_is_rejected(migrated_db: AppDatabase) -> None:
    """An investigation needs a table to look at."""
    tenant_id = await _tenant(migrated_db)
    datasource_id = await _datasource(migrated_db, tenant_id)

    response, _ = await _post(
        migrated_db,
        tenant_id,
        {"brief": {"symptom": SYMPTOM}, "datasource_id": str(datasource_id)},
        user_id=None,
    )

    assert response.status_code == 400
    assert "table" in response.json()["detail"]


async def test_a_run_that_cannot_start_shows_why_on_its_card(migrated_db: AppDatabase) -> None:
    """If Temporal refuses the start, the run is failed with the reason, and the API says 503."""
    tenant_id = await _tenant(migrated_db)
    user_id = await _user(migrated_db)
    datasource_id = await _datasource(migrated_db, tenant_id)
    temporal = AsyncMock()
    temporal.start_investigation.side_effect = RuntimeError("Temporal is unreachable")

    response, _ = await _post(
        migrated_db,
        tenant_id,
        {
            "brief": {"symptom": SYMPTOM, "scope": {"tables": ["public.orders"]}},
            "datasource_id": str(datasource_id),
        },
        user_id=user_id,
        temporal=temporal,
    )

    assert response.status_code == 503
    run = await migrated_db.fetch_one(
        """
        SELECT r.issue_id, i.outcome FROM issue_investigation_runs r
        JOIN investigations i ON i.id = r.investigation_id
        JOIN issues s ON s.id = r.issue_id
        WHERE s.tenant_id = $1
        """,
        tenant_id,
    )
    assert run is not None
    outcome = json.loads(run["outcome"])
    assert outcome["status"] == "failed"
    assert outcome["error"]["message"] == (
        "Couldn't start the investigation: Temporal is unreachable"
    )
    messages = await _thread(migrated_db, run["issue_id"])
    kinds = [(m["kind"], m["payload"].get("phase")) for m in messages]
    assert ("investigation", "outcome") in kinds


async def test_a_run_links_back_to_its_issue_with_its_number_and_failure(
    migrated_db: AppDatabase,
) -> None:
    """The run's details page gets the issue, the run number, the brief and why it failed."""
    from dataing.temporal.activities.publish_outcome import publish_outcome
    from dataing.temporal.client import InvestigationStatus

    tenant_id = await _tenant(migrated_db)
    user_id = await _user(migrated_db)
    datasource_id = await _datasource(migrated_db, tenant_id)
    body = {
        "brief": {"symptom": SYMPTOM, "scope": {"tables": ["public.orders"]}},
        "datasource_id": str(datasource_id),
    }
    first, temporal = await _post(migrated_db, tenant_id, body, user_id=user_id)
    issue_id = first.json()["issue_id"]
    second, _ = await _post(
        migrated_db, tenant_id, {**body, "issue_id": issue_id}, user_id=user_id, temporal=temporal
    )
    started = second.json()
    failure = {
        "code": "invalid_key",
        "message": "Anthropic rejected the API key (401).",
        "step": "synthesize",
    }
    await publish_outcome(
        migrated_db,
        {
            "investigation_id": started["investigation_id"],
            "tenant_id": str(tenant_id),
            "issue_id": issue_id,
            "failure": failure,
            "hypotheses": [{"id": "h1", "title": "late loads", "status": "untested"}],
        },
    )
    temporal.get_status.return_value = InvestigationStatus(
        workflow_id=started["investigation_id"], run_id=None, workflow_status="failed"
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.app_db = migrated_db
    app.state.temporal_client = temporal
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="test",
        tenant_name="Test Tenant",
        user_id=user_id,
        scopes=["read"],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/investigations/{started['investigation_id']}")

    assert response.status_code == 200, response.text
    state = response.json()
    assert (state["issue_id"], state["issue_number"], state["issue_title"]) == (
        issue_id,
        1,
        SYMPTOM,
    )
    assert (state["run_number"], state["execution_profile"]) == (2, "standard")
    assert state["brief"]["symptom"] == SYMPTOM
    assert state["status"] == "failed"
    assert state["error"] == failure
    assert state["hypotheses"] == [
        {"id": "h1", "title": "late loads", "status": "untested", "reasoning": None}
    ]
