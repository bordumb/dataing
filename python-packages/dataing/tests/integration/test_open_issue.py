"""open_issue() is the one way to insert an issue (docs/specs/0001_issue_chat.md §7.11)."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.adapters.db.issues import open_issue

pytestmark = pytest.mark.integration


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


async def _thread_messages(db: AppDatabase, issue_id: UUID) -> list[dict[str, object]]:
    threads = IssueThreadRepository(db)
    thread = await threads.ensure_shared_thread(issue_id)
    return await threads.list_messages(thread["id"])


async def test_a_person_opens_an_issue_and_its_thread_starts_with_it(
    migrated_db: AppDatabase,
) -> None:
    """The issue gets the next number and labels; the thread's first entry is the opening."""
    tenant_id = await _tenant(migrated_db)
    user_id = await _user(migrated_db)

    first = await open_issue(
        migrated_db, tenant_id=tenant_id, title="Orders dropped", created_by=user_id
    )
    second = await open_issue(
        migrated_db,
        tenant_id=tenant_id,
        title="Nulls in customer_id",
        severity="high",
        dataset_id="public.orders",
        labels=["orders", "nulls"],
        created_by=user_id,
    )

    assert (first["number"], second["number"]) == (1, 2)
    assert (second["status"], second["author_type"], second["created_by_user_id"]) == (
        "open",
        "human",
        user_id,
    )
    labels = await migrated_db.fetch_all(
        "SELECT label FROM issue_labels WHERE issue_id = $1 ORDER BY label", second["id"]
    )
    assert [row["label"] for row in labels] == ["nulls", "orders"]
    (opening,) = await _thread_messages(migrated_db, second["id"])
    assert opening["kind"] == "event"
    assert opening["author_user_id"] == user_id
    assert opening["payload"] == {"event_type": "created", "title": "Nulls in customer_id"}
    event = await migrated_db.fetch_one(
        "SELECT actor_user_id FROM issue_events WHERE issue_id = $1 AND event_type = 'created'",
        second["id"],
    )
    assert event is not None
    assert event["actor_user_id"] == user_id


async def test_an_integration_opens_an_issue_attributed_to_its_source(
    migrated_db: AppDatabase,
) -> None:
    """A webhook's issue has no person behind it; its opening names the source."""
    tenant_id = await _tenant(migrated_db)

    issue = await open_issue(
        migrated_db,
        tenant_id=tenant_id,
        title="Freshness check failed",
        author_type="integration",
        source_provider="monte_carlo",
        source_external_id="mc_incident_42",
        source_external_url="https://getmontecarlo.com/incidents/42",
        event_payload={"source": "webhook"},
    )

    assert (issue["author_type"], issue["source_external_id"]) == ("integration", "mc_incident_42")
    (opening,) = await _thread_messages(migrated_db, issue["id"])
    assert opening["author_user_id"] is None
    assert opening["payload"] == {
        "event_type": "created",
        "title": "Freshness check failed",
        "source_provider": "monte_carlo",
        "source": "webhook",
    }
    event = await migrated_db.fetch_one(
        "SELECT payload FROM issue_events WHERE issue_id = $1 AND event_type = 'created'",
        issue["id"],
    )
    assert event is not None
    assert json.loads(event["payload"])["source_provider"] == "monte_carlo"
