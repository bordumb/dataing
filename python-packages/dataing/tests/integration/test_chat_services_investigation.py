"""The chat agent's view of an issue's investigation (spec 0001 §7.5)."""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.issue_chat import ThreadChatServices

pytestmark = pytest.mark.integration

LIVE = {
    "current_step": "evaluate_hypotheses",
    "hypotheses": [{"id": "h3", "title": "late events", "status": "running"}],
    "pending_steers": [],
}


async def _issue_run(db: AppDatabase, *, outcome: dict[str, Any] | None) -> dict[str, Any]:
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
        "INSERT INTO investigations (id, tenant_id, alert, outcome) VALUES ($1, $2, '{}', $3)",
        investigation_id,
        tenant_id,
        json.dumps(outcome) if outcome else None,
    )
    await db.execute(
        "INSERT INTO issue_investigation_runs (issue_id, investigation_id, trigger_type) "
        "VALUES ($1, $2, 'human')",
        issue_id,
        investigation_id,
    )
    return {"tenant_id": tenant_id, "issue_id": issue_id, "investigation_id": investigation_id}


def _services(db: AppDatabase, run: dict[str, Any], reads: list[str]) -> ThreadChatServices:
    async def read(investigation_id: str) -> dict[str, Any] | None:
        reads.append(investigation_id)
        return LIVE

    return ThreadChatServices(
        db,
        MagicMock(),
        tenant_id=run["tenant_id"],
        issue_id=run["issue_id"],
        reply_message_id=uuid.uuid4(),
        principal=None,
        investigation_status=read,
    )


async def test_a_running_investigation_includes_its_live_hypotheses(
    migrated_db: AppDatabase,
) -> None:
    """The agent sees hypothesis ids it can name in a rule_out proposal."""
    run = await _issue_run(migrated_db, outcome=None)
    reads: list[str] = []

    result = await _services(migrated_db, run, reads).get_investigation(
        str(run["investigation_id"])
    )

    assert result is not None
    assert result["live"] == LIVE
    assert reads == [str(run["investigation_id"])]


async def test_a_finished_investigation_is_read_from_its_outcome(
    migrated_db: AppDatabase,
) -> None:
    """A finished run's outcome already has the hypotheses; the workflow isn't asked."""
    run = await _issue_run(migrated_db, outcome={"root_cause": "app_v2", "hypotheses": []})
    reads: list[str] = []

    result = await _services(migrated_db, run, reads).get_investigation(
        str(run["investigation_id"])
    )

    assert result is not None
    assert "live" not in result
    assert result["outcome"]["root_cause"] == "app_v2"
    assert reads == []
