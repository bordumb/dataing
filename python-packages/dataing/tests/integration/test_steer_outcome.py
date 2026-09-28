"""record_steer_outcome against the migrated schema (spec 0001 §7.8)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from temporalio.testing import ActivityEnvironment

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.temporal.activities.steering import make_record_steer_outcome_activity

pytestmark = pytest.mark.integration


async def _pending_steer(db: AppDatabase) -> dict[str, Any]:
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
    steer_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO investigation_steers
            (id, tenant_id, investigation_id, issue_id, kind, text, hypothesis_id)
        VALUES ($1, $2, $3, $4, 'rule_out', 'Events land within minutes', 'h3')
        """,
        steer_id,
        tenant_id,
        investigation_id,
        issue_id,
    )
    return {
        "issue_id": issue_id,
        "payload": {
            "steer_id": str(steer_id),
            "investigation_id": str(investigation_id),
            "kind": "rule_out",
            "hypothesis_id": "h3",
            "status": "applied",
            "phase": "evaluation",
            "outcome": "Cancelled h3 'late-arriving events'",
        },
    }


async def test_outcome_is_stored_and_posted_once(migrated_db: AppDatabase) -> None:
    """The steer row records its outcome; the thread says what happened, once."""
    steer = await _pending_steer(migrated_db)
    record = make_record_steer_outcome_activity(migrated_db)

    await ActivityEnvironment().run(record, steer["payload"])
    await ActivityEnvironment().run(record, steer["payload"])

    row = await migrated_db.fetch_one(
        "SELECT status, applied_phase, outcome, applied_at FROM investigation_steers "
        "WHERE id = $1",
        uuid.UUID(steer["payload"]["steer_id"]),
    )
    assert row is not None
    assert (row["status"], row["applied_phase"]) == ("applied", "evaluation")
    assert row["outcome"] == "Cancelled h3 'late-arriving events'"
    assert row["applied_at"] is not None

    thread = await IssueThreadRepository(migrated_db).ensure_shared_thread(steer["issue_id"])
    messages = await IssueThreadRepository(migrated_db).list_messages(thread["id"])
    (message,) = (m for m in messages if m["kind"] == "steer")
    assert message["author_kind"] == "system"
    assert message["body_md"] == "Applied during evaluation: Cancelled h3 'late-arriving events'"


async def test_a_recorded_outcome_is_not_overwritten(migrated_db: AppDatabase) -> None:
    """Only a pending steer changes; a late duplicate can't flip its status."""
    steer = await _pending_steer(migrated_db)
    record = make_record_steer_outcome_activity(migrated_db)

    await ActivityEnvironment().run(record, steer["payload"])
    await ActivityEnvironment().run(
        record, {**steer["payload"], "status": "rejected", "outcome": "late"}
    )

    row = await migrated_db.fetch_one(
        "SELECT status FROM investigation_steers WHERE id = $1",
        uuid.UUID(steer["payload"]["steer_id"]),
    )
    assert row is not None
    assert row["status"] == "applied"
