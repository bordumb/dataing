"""Integration tests for the investigation context of fix feedback exports."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase
from dataing.services.feedback import FixFeedbackService

pytestmark = pytest.mark.integration

CREATED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


async def _create_investigation(db: AppDatabase) -> tuple[UUID, UUID]:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert, created_at) VALUES ($1, $2, $3, $4)",
        investigation_id,
        tenant_id,
        json.dumps({"dataset_ids": ["public.orders"]}),
        CREATED_AT,
    )
    return tenant_id, investigation_id


async def _spawn_from_issue(
    db: AppDatabase, tenant_id: UUID, investigation_id: UUID, number: int
) -> UUID:
    issue_id = uuid4()
    await db.execute(
        "INSERT INTO issues (id, tenant_id, number, title) VALUES ($1, $2, $3, 'Null spike')",
        issue_id,
        tenant_id,
        number,
    )
    await db.execute(
        """INSERT INTO issue_investigation_runs (issue_id, investigation_id, trigger_type)
           VALUES ($1, $2, 'human')""",
        issue_id,
        investigation_id,
    )
    return issue_id


async def test_context_names_the_issue_the_investigation_was_spawned_from(
    migrated_db: AppDatabase,
) -> None:
    """The issue comes from issue_investigation_runs."""
    tenant_id, investigation_id = await _create_investigation(migrated_db)
    issue_id = await _spawn_from_issue(migrated_db, tenant_id, investigation_id, number=1)

    context = await FixFeedbackService(db=migrated_db).investigation_context(investigation_id)

    assert context == {
        "issue_id": str(issue_id),
        "investigation_created_at": CREATED_AT.isoformat(),
    }


async def test_context_has_no_issue_for_an_investigation_started_directly(
    migrated_db: AppDatabase,
) -> None:
    """Investigations started from an alert have no issue to name."""
    _, investigation_id = await _create_investigation(migrated_db)

    context = await FixFeedbackService(db=migrated_db).investigation_context(investigation_id)

    assert context == {"investigation_created_at": CREATED_AT.isoformat()}
