"""publish_investigation_outcome against the migrated schema (spec 0001 §7.7)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from temporalio.testing import ActivityEnvironment

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.temporal.activities.publish_outcome import make_publish_investigation_outcome_activity

pytestmark = pytest.mark.integration


async def _issue_with_run(db: AppDatabase) -> dict[str, Any]:
    tenant_id = uuid.uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, 't', $2)", tenant_id, f"t-{tenant_id.hex}"
    )
    issue_id = uuid.uuid4()
    await db.execute(
        "INSERT INTO issues (id, tenant_id, number, title) VALUES ($1, $2, 1, 'Orders dropped')",
        issue_id,
        tenant_id,
    )
    investigation_id = uuid.uuid4()
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
        "investigation_id": str(investigation_id),
        "tenant_id": str(tenant_id),
        "issue_id": str(issue_id),
        "synthesis": {
            "root_cause": "app_v2 writes COMPLETE instead of completed",
            "confidence": 0.91,
            "recommendations": ["Normalize status"],
            "supporting_evidence": ["h1"],
        },
        "hypotheses": [
            {"id": "h1", "title": "app_v2 status", "status": "supported"},
            {"id": "h2", "title": "late events", "status": "untested"},
        ],
        "counter_analysis": None,
    }


async def test_outcome_is_written_to_investigation_run_and_thread(
    migrated_db: AppDatabase,
) -> None:
    """The investigation completes, the run gets its summary, the thread gets the result."""
    payload = await _issue_with_run(migrated_db)
    publish = make_publish_investigation_outcome_activity(migrated_db)

    await ActivityEnvironment().run(publish, payload)

    investigation = await migrated_db.fetch_one(
        "SELECT status, outcome, completed_at FROM investigations WHERE id = $1",
        uuid.UUID(payload["investigation_id"]),
    )
    assert investigation is not None
    assert investigation["status"] == "completed"
    assert investigation["completed_at"] is not None
    assert json.loads(investigation["outcome"])["root_cause"].startswith("app_v2")

    run = await migrated_db.fetch_one(
        "SELECT synthesis_summary, confidence, completed_at FROM issue_investigation_runs "
        "WHERE investigation_id = $1",
        uuid.UUID(payload["investigation_id"]),
    )
    assert run is not None
    assert run["synthesis_summary"].startswith("app_v2 writes")
    assert run["confidence"] == pytest.approx(0.91)
    assert run["completed_at"] is not None

    thread = await IssueThreadRepository(migrated_db).ensure_shared_thread(
        uuid.UUID(payload["issue_id"])
    )
    messages = await IssueThreadRepository(migrated_db).list_messages(thread["id"])
    (card,) = (m for m in messages if m["kind"] == "investigation")
    assert card["author_kind"] == "agent"
    assert card["payload"]["phase"] == "outcome"
    assert card["payload"]["outcome"]["confidence"] == pytest.approx(0.91)
    assert "app_v2 writes COMPLETE" in card["body_md"]


async def test_publishing_twice_leaves_one_thread_message(migrated_db: AppDatabase) -> None:
    """A retried activity doesn't post the result twice."""
    payload = await _issue_with_run(migrated_db)
    publish = make_publish_investigation_outcome_activity(migrated_db)

    await ActivityEnvironment().run(publish, payload)
    await ActivityEnvironment().run(publish, payload)

    rows = await migrated_db.fetch_all(
        """
        SELECT m.id FROM issue_thread_messages m
        JOIN issue_threads t ON t.id = m.thread_id
        WHERE t.issue_id = $1 AND m.kind = 'investigation'
        """,
        uuid.UUID(payload["issue_id"]),
    )
    assert len(rows) == 1


async def test_runs_without_an_issue_only_complete_the_investigation(
    migrated_db: AppDatabase,
) -> None:
    """Check- or webhook-started runs have no thread to post to."""
    payload = await _issue_with_run(migrated_db)
    payload["issue_id"] = None
    publish = make_publish_investigation_outcome_activity(migrated_db)

    await ActivityEnvironment().run(publish, payload)

    investigation = await migrated_db.fetch_one(
        "SELECT status FROM investigations WHERE id = $1", uuid.UUID(payload["investigation_id"])
    )
    assert investigation is not None
    assert investigation["status"] == "completed"
