"""Confirming or rejecting an investigation's outcome (spec 0001 §7.10)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from temporalio.testing import ActivityEnvironment

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_feedback_adapter
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.investigation_outcomes import router as outcomes_router
from dataing.entrypoints.api.routes.issues import router as issues_router
from dataing.temporal.activities.publish_outcome import make_publish_investigation_outcome_activity

pytestmark = pytest.mark.integration


async def _completed_run(db: AppDatabase, *, completed: bool = True) -> dict[str, Any]:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, 't', $2)", tenant_id, f"t-{tenant_id.hex}"
    )
    user_id = uuid4()
    await db.execute("INSERT INTO users (id, email) VALUES ($1, $2)", user_id, f"{user_id.hex}@x")
    issue_id = uuid4()
    await db.execute(
        "INSERT INTO issues (id, tenant_id, number, title, status, assignee_user_id) "
        "VALUES ($1, $2, 1, 'Orders dropped', 'in_progress', $3)",
        issue_id,
        tenant_id,
        user_id,
    )
    investigation_id = uuid4()
    outcome = json.dumps({"root_cause": "app_v2 writes COMPLETE", "confidence": 0.9})
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert, outcome) VALUES ($1, $2, '{}', $3)",
        investigation_id,
        tenant_id,
        outcome if completed else None,
    )
    await db.execute(
        "INSERT INTO issue_investigation_runs "
        "(issue_id, investigation_id, trigger_type, synthesis_summary, confidence) "
        "VALUES ($1, $2, 'human', $3, 0.9)",
        issue_id,
        investigation_id,
        "app_v2 writes COMPLETE" if completed else None,
    )
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "issue_id": issue_id,
        "investigation_id": investigation_id,
    }


def _client(db: AppDatabase, run: dict[str, Any], feedback: Any) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(outcomes_router)
    app.include_router(issues_router)
    app.state.app_db = db
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=run["tenant_id"],
        tenant_slug="t",
        tenant_name="T",
        user_id=run["user_id"],
        scopes=["read", "write"],
    )
    app.dependency_overrides[get_feedback_adapter] = lambda: feedback
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _feedback() -> MagicMock:
    adapter = MagicMock()
    adapter.emit = AsyncMock(return_value=MagicMock(id=uuid4(), created_at=None))
    return adapter


async def test_confirming_records_the_verdict_feedback_and_a_thread_event(
    migrated_db: AppDatabase,
) -> None:
    """A confirmed outcome is stored on the run, sent as feedback and shown in the thread."""
    run = await _completed_run(migrated_db)
    feedback = _feedback()

    async with _client(migrated_db, run, feedback) as client:
        response = await client.post(
            f"/investigations/{run['investigation_id']}/outcome-review",
            json={"verdict": "confirmed"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["outcome_verdict"] == "confirmed"
    stored = await migrated_db.fetch_one(
        "SELECT outcome_verdict, outcome_reviewed_by FROM issue_investigation_runs "
        "WHERE investigation_id = $1",
        run["investigation_id"],
    )
    assert stored is not None
    assert (stored["outcome_verdict"], stored["outcome_reviewed_by"]) == (
        "confirmed",
        run["user_id"],
    )
    feedback.emit.assert_awaited_once()
    assert feedback.emit.await_args.kwargs["event_data"]["rating"] == 1
    event = await migrated_db.fetch_one(
        """
        SELECT m.body_md FROM issue_thread_messages m
        JOIN issue_threads t ON t.id = m.thread_id
        WHERE t.issue_id = $1 AND m.kind = 'event'
        """,
        run["issue_id"],
    )
    assert event is not None
    assert "confirmed" in event["body_md"].lower()


async def test_rejecting_needs_a_reason(migrated_db: AppDatabase) -> None:
    """Rejecting without a note is refused."""
    run = await _completed_run(migrated_db)

    async with _client(migrated_db, run, _feedback()) as client:
        response = await client.post(
            f"/investigations/{run['investigation_id']}/outcome-review",
            json={"verdict": "rejected"},
        )

    assert response.status_code == 422


async def test_a_running_investigation_cannot_be_reviewed(migrated_db: AppDatabase) -> None:
    """There is no outcome to confirm yet."""
    run = await _completed_run(migrated_db, completed=False)

    async with _client(migrated_db, run, _feedback()) as client:
        response = await client.post(
            f"/investigations/{run['investigation_id']}/outcome-review",
            json={"verdict": "confirmed"},
        )

    assert response.status_code == 409


async def test_another_tenants_investigation_is_not_found(migrated_db: AppDatabase) -> None:
    """Tenants can't review each other's runs."""
    run = await _completed_run(migrated_db)
    other = {**run, "tenant_id": uuid4()}

    async with _client(migrated_db, other, _feedback()) as client:
        response = await client.post(
            f"/investigations/{run['investigation_id']}/outcome-review",
            json={"verdict": "confirmed"},
        )

    assert response.status_code == 404


async def test_resolving_with_a_confirmed_cause_emits_resolved_with_cause(
    migrated_db: AppDatabase,
) -> None:
    """Resolving an issue whose run was confirmed records the cause it was resolved with."""
    run = await _completed_run(migrated_db)
    async with _client(migrated_db, run, _feedback()) as client:
        await client.post(
            f"/investigations/{run['investigation_id']}/outcome-review",
            json={"verdict": "confirmed"},
        )
        response = await client.patch(
            f"/issues/{run['issue_id']}",
            json={"status": "resolved", "resolution_note": "Normalized status in the loader"},
        )

    assert response.status_code == 200, response.text
    event = await migrated_db.fetch_one(
        "SELECT payload FROM issue_events "
        "WHERE issue_id = $1 AND event_type = 'resolved_with_cause'",
        run["issue_id"],
    )
    assert event is not None
    payload = json.loads(event["payload"])
    assert payload["investigation_id"] == str(run["investigation_id"])
    assert payload["root_cause"] == "app_v2 writes COMPLETE"


async def test_a_published_outcome_lets_the_issue_resolve_without_a_note(
    migrated_db: AppDatabase,
) -> None:
    """The resolve guard accepts a run whose outcome the workflow published."""
    run = await _completed_run(migrated_db, completed=False)
    publish = make_publish_investigation_outcome_activity(migrated_db)
    await ActivityEnvironment().run(
        publish,
        {
            "investigation_id": str(run["investigation_id"]),
            "tenant_id": str(run["tenant_id"]),
            "issue_id": str(run["issue_id"]),
            "synthesis": {"root_cause": "app_v2 writes COMPLETE", "confidence": 0.9},
            "hypotheses": [],
        },
    )

    async with _client(migrated_db, run, _feedback()) as client:
        response = await client.patch(f"/issues/{run['issue_id']}", json={"status": "resolved"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"
