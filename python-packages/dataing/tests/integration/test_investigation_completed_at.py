"""Integration tests for investigations.completed_at on the migrated schema."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase

pytestmark = pytest.mark.integration


async def _create_investigation(db: AppDatabase) -> UUID:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert) VALUES ($1, $2, $3)",
        investigation_id,
        tenant_id,
        json.dumps({"dataset_ids": ["public.orders"]}),
    )
    return investigation_id


async def _completion(db: AppDatabase, investigation_id: UUID) -> tuple[str, object]:
    row = await db.fetch_one(
        "SELECT status, completed_at FROM investigations WHERE id = $1", investigation_id
    )
    assert row is not None
    return row["status"], row["completed_at"]


async def test_completed_at_is_stamped_when_the_outcome_is_first_set(
    migrated_db: AppDatabase,
) -> None:
    """Writers only set outcome; the database records when that first happened."""
    investigation_id = await _create_investigation(migrated_db)
    assert await _completion(migrated_db, investigation_id) == ("active", None)

    await migrated_db.execute(
        "UPDATE investigations SET outcome = $2 WHERE id = $1",
        investigation_id,
        json.dumps({"status": "completed"}),
    )
    status, completed_at = await _completion(migrated_db, investigation_id)
    assert status == "completed"
    assert completed_at is not None

    await migrated_db.execute(
        "UPDATE investigations SET outcome = $2 WHERE id = $1",
        investigation_id,
        json.dumps({"status": "completed", "root_cause": "late upstream load"}),
    )
    assert await _completion(migrated_db, investigation_id) == ("completed", completed_at)


async def test_clearing_the_outcome_reopens_the_investigation(migrated_db: AppDatabase) -> None:
    """An investigation without an outcome is active and has no completion time."""
    investigation_id = await _create_investigation(migrated_db)
    await migrated_db.execute(
        "UPDATE investigations SET outcome = $2 WHERE id = $1",
        investigation_id,
        json.dumps({"status": "completed"}),
    )

    await migrated_db.execute(
        "UPDATE investigations SET outcome = NULL WHERE id = $1", investigation_id
    )

    assert await _completion(migrated_db, investigation_id) == ("active", None)
