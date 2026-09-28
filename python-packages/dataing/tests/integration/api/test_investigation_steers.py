"""Sending steers to a running investigation (spec 0001 §7.8)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.investigation_steers import NOT_RUNNING
from dataing.entrypoints.api.routes.investigation_steers import router as steers_router

pytestmark = pytest.mark.integration


class FakeTemporal:
    """Records steer signals; with running=False the workflow has already finished."""

    def __init__(self, running: bool = True) -> None:
        self.running = running
        self.signals: list[tuple[str, dict[str, Any]]] = []

    async def steer_investigation(self, investigation_id: str, steer: dict[str, Any]) -> None:
        if not self.running:
            raise RuntimeError("workflow execution already completed")
        self.signals.append((investigation_id, steer))


async def _running_investigation(db: AppDatabase) -> dict[str, Any]:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, 't', $2)", tenant_id, f"t-{tenant_id.hex}"
    )
    user_id = uuid4()
    await db.execute("INSERT INTO users (id, email) VALUES ($1, $2)", user_id, f"{user_id.hex}@x")
    issue_id = uuid4()
    await db.execute(
        "INSERT INTO issues (id, tenant_id, number, title) VALUES ($1, $2, 1, 'Orders dropped')",
        issue_id,
        tenant_id,
    )
    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert) VALUES ($1, $2, '{}')",
        investigation_id,
        tenant_id,
    )
    await db.execute(
        "INSERT INTO issue_investigation_runs (issue_id, investigation_id, trigger_type) "
        "VALUES ($1, $2, 'human')",
        issue_id,
        investigation_id,
    )
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "issue_id": issue_id,
        "investigation_id": investigation_id,
    }


def _client(
    db: AppDatabase, run: dict[str, Any], temporal: FakeTemporal, tenant_id: UUID | None = None
) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(steers_router)
    app.state.app_db = db
    app.state.temporal_client = temporal
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id or run["tenant_id"],
        tenant_slug="t",
        tenant_name="T",
        user_id=run["user_id"],
        scopes=["read", "write"],
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _thread_messages(db: AppDatabase, issue_id: UUID) -> list[dict[str, Any]]:
    rows = await db.fetch_all(
        """
        SELECT m.author_kind, m.kind, m.body_md, m.payload FROM issue_thread_messages m
        JOIN issue_threads t ON t.id = m.thread_id
        WHERE t.issue_id = $1 AND m.kind = 'steer' ORDER BY m.seq
        """,
        issue_id,
    )
    return [{**r, "payload": json.loads(r["payload"])} for r in rows]


async def test_a_steer_is_stored_pending_shown_and_signalled(migrated_db: AppDatabase) -> None:
    """The steer is pending until the workflow applies it; the thread shows who sent it."""
    run = await _running_investigation(migrated_db)
    temporal = FakeTemporal()

    async with _client(migrated_db, run, temporal) as client:
        response = await client.post(
            f"/investigations/{run['investigation_id']}/steers",
            json={"kind": "rule_out", "text": "Events land within minutes", "hypothesis_id": "h3"},
        )

    assert response.status_code == 201, response.text
    steer = response.json()
    assert (steer["status"], steer["kind"], steer["hypothesis_id"]) == ("pending", "rule_out", "h3")
    (investigation_id, signal) = temporal.signals[0]
    assert investigation_id == str(run["investigation_id"])
    assert signal == {
        "steer_id": steer["id"],
        "kind": "rule_out",
        "text": "Events land within minutes",
        "hypothesis_id": "h3",
        "actor_user_id": str(run["user_id"]),
    }
    (message,) = await _thread_messages(migrated_db, run["issue_id"])
    assert message["author_kind"] == "user"
    assert message["body_md"] == "**Rule out h3**: Events land within minutes"
    assert steer["message_id"] is not None


async def test_a_steer_to_a_finished_run_is_rejected(migrated_db: AppDatabase) -> None:
    """When the signal can't be delivered, the steer ends rejected and the thread says so."""
    run = await _running_investigation(migrated_db)

    async with _client(migrated_db, run, FakeTemporal(running=False)) as client:
        response = await client.post(
            f"/investigations/{run['investigation_id']}/steers",
            json={"kind": "add_context", "text": "app_v2 shipped at 09:00"},
        )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "rejected"
    assert response.json()["outcome"] == NOT_RUNNING
    request, outcome = await _thread_messages(migrated_db, run["issue_id"])
    assert request["author_kind"] == "user"
    assert (outcome["author_kind"], outcome["body_md"]) == ("system", f"Not applied: {NOT_RUNNING}")


async def test_sending_a_proposal_twice_sends_one_steer(migrated_db: AppDatabase) -> None:
    """A double click on an agent's proposal doesn't steer the run twice."""
    run = await _running_investigation(migrated_db)
    temporal = FakeTemporal()
    body = {
        "kind": "add_context",
        "text": "app_v2 shipped at 09:00",
        "proposal_message_id": str(uuid4()),
    }

    async with _client(migrated_db, run, temporal) as client:
        first = await client.post(f"/investigations/{run['investigation_id']}/steers", json=body)
        second = await client.post(f"/investigations/{run['investigation_id']}/steers", json=body)
        listed = await client.get(f"/investigations/{run['investigation_id']}/steers")

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    assert len(temporal.signals) == 1
    assert [s["id"] for s in listed.json()["items"]] == [first.json()["id"]]


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "add_context", "text": "  "},
        {"kind": "add_hypothesis"},
        {"kind": "rule_out"},
        {"kind": "reroute", "text": "x"},
    ],
)
async def test_a_steer_needs_what_it_acts_on(
    migrated_db: AppDatabase, body: dict[str, Any]
) -> None:
    """Empty context, a hypothesis without text or a rule-out of nothing is refused."""
    run = await _running_investigation(migrated_db)

    async with _client(migrated_db, run, FakeTemporal()) as client:
        response = await client.post(f"/investigations/{run['investigation_id']}/steers", json=body)

    assert response.status_code == 422


async def test_another_tenants_investigation_is_not_found(migrated_db: AppDatabase) -> None:
    """Tenants can't steer each other's runs."""
    run = await _running_investigation(migrated_db)
    temporal = FakeTemporal()

    async with _client(migrated_db, run, temporal, tenant_id=uuid4()) as client:
        response = await client.post(
            f"/investigations/{run['investigation_id']}/steers",
            json={"kind": "stop_and_synthesize"},
        )

    assert response.status_code == 404
    assert temporal.signals == []
