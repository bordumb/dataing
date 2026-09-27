"""Integration tests for the issue thread schema (migration 037)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

from dataing.adapters.db.app_db import AppDatabase

from .conftest import MIGRATIONS_DIR, Migrate

pytestmark = pytest.mark.integration

THREADS_MIGRATION = "037_issue_threads.sql"


def _migrations_before(target: Path, name: str) -> Path:
    """Copy every schema migration that sorts before `name` into target."""
    target.mkdir()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name < name:
            shutil.copy(path, target / path.name)
    return target


async def _seed_issue_with_run(db: AppDatabase) -> tuple[UUID, UUID, UUID]:
    """Create a tenant, an issue and an investigation run with a focus prompt."""
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    issue_id = uuid4()
    await db.execute(
        "INSERT INTO issues (id, tenant_id, number, title) VALUES ($1, $2, 1, $3)",
        issue_id,
        tenant_id,
        "Orders dropped",
    )
    investigation_id = uuid4()
    await db.execute(
        "INSERT INTO investigations (id, tenant_id, alert) VALUES ($1, $2, $3)",
        investigation_id,
        tenant_id,
        json.dumps({"dataset_ids": ["public.orders"]}),
    )
    run_id = uuid4()
    await db.execute(
        """
        INSERT INTO issue_investigation_runs
            (id, issue_id, investigation_id, trigger_type, focus_prompt)
        VALUES ($1, $2, $3, 'human', 'check app_v2')
        """,
        run_id,
        issue_id,
        investigation_id,
    )
    return tenant_id, issue_id, run_id


async def test_existing_issues_get_a_shared_thread_and_runs_get_a_brief(
    tmp_path: Path, empty_dsn: str, migrate: Migrate
) -> None:
    """Upgrading backfills one shared thread per issue and a brief per run."""
    before = _migrations_before(tmp_path / "migrations", THREADS_MIGRATION)
    assert migrate(empty_dsn, before).returncode == 0

    db = AppDatabase(dsn=empty_dsn)
    await db.connect()
    try:
        tenant_id, issue_id, run_id = await _seed_issue_with_run(db)

        upgraded = migrate(empty_dsn)
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr

        thread = await db.fetch_one(
            "SELECT tenant_id, kind, owner_user_id FROM issue_threads WHERE issue_id = $1",
            issue_id,
        )
        assert thread is not None
        assert (thread["tenant_id"], thread["kind"], thread["owner_user_id"]) == (
            tenant_id,
            "shared",
            None,
        )

        run = await db.fetch_one("SELECT brief FROM issue_investigation_runs WHERE id = $1", run_id)
        assert run is not None
        assert json.loads(run["brief"]) == {
            "version": 1,
            "symptom": "Orders dropped",
            "notes": "check app_v2",
        }
    finally:
        await db.close()


async def _new_issue(db: AppDatabase) -> tuple[UUID, UUID]:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    issue_id = uuid4()
    await db.execute(
        "INSERT INTO issues (id, tenant_id, number, title) VALUES ($1, $2, 1, 'x')",
        issue_id,
        tenant_id,
    )
    return tenant_id, issue_id


async def test_an_issue_has_at_most_one_shared_thread(migrated_db: AppDatabase) -> None:
    """The partial unique index rejects a second shared thread."""
    tenant_id, issue_id = await _new_issue(migrated_db)
    insert = "INSERT INTO issue_threads (tenant_id, issue_id, kind) VALUES ($1, $2, 'shared')"
    await migrated_db.execute(insert, tenant_id, issue_id)

    with pytest.raises(asyncpg.UniqueViolationError):
        await migrated_db.execute(insert, tenant_id, issue_id)


async def test_scratch_threads_need_an_owner(migrated_db: AppDatabase) -> None:
    """A scratch thread without an owner violates the kind/owner check."""
    tenant_id, issue_id = await _new_issue(migrated_db)

    with pytest.raises(asyncpg.CheckViolationError):
        await migrated_db.execute(
            "INSERT INTO issue_threads (tenant_id, issue_id, kind) VALUES ($1, $2, 'scratch')",
            tenant_id,
            issue_id,
        )


async def test_message_rev_increases_on_every_insert_and_update(
    migrated_db: AppDatabase,
) -> None:
    """Every write moves rev forward, because rev is the stream cursor."""
    tenant_id, issue_id = await _new_issue(migrated_db)
    thread = await migrated_db.execute_returning(
        "INSERT INTO issue_threads (tenant_id, issue_id, kind) "
        "VALUES ($1, $2, 'shared') RETURNING id",
        tenant_id,
        issue_id,
    )
    assert thread is not None
    inserted = await migrated_db.execute_returning(
        """
        INSERT INTO issue_thread_messages (tenant_id, thread_id, seq, author_kind, kind)
        VALUES ($1, $2, 1, 'agent', 'agent_reply')
        RETURNING id, rev, touched_at
        """,
        tenant_id,
        thread["id"],
    )
    assert inserted is not None
    updated = await migrated_db.execute_returning(
        "UPDATE issue_thread_messages SET body_md = 'hi' WHERE id = $1 RETURNING rev, touched_at",
        inserted["id"],
    )
    assert updated is not None
    assert updated["rev"] > inserted["rev"]
    assert updated["touched_at"] >= inserted["touched_at"]


async def test_comments_move_into_the_shared_thread_in_order(
    tmp_path: Path, empty_dsn: str, migrate: Migrate
) -> None:
    """Migration 038 copies comments into the shared thread and drops issue_comments."""
    before = _migrations_before(tmp_path / "migrations", "038_issue_comments_to_threads.sql")
    assert migrate(empty_dsn, before).returncode == 0

    db = AppDatabase(dsn=empty_dsn)
    await db.connect()
    try:
        tenant_id, issue_id = await _new_issue(db)
        user_id = uuid4()
        await db.execute(
            "INSERT INTO users (id, email) VALUES ($1, $2)", user_id, f"{user_id.hex}@x.com"
        )
        thread = await db.execute_returning(
            "INSERT INTO issue_threads (tenant_id, issue_id, kind) "
            "VALUES ($1, $2, 'shared') RETURNING id",
            tenant_id,
            issue_id,
        )
        assert thread is not None
        # An event already in the thread keeps seq 1; comments follow it
        await db.execute(
            "INSERT INTO issue_thread_messages (tenant_id, thread_id, seq, author_kind, kind) "
            "VALUES ($1, $2, 1, 'system', 'event')",
            tenant_id,
            thread["id"],
        )
        for i, minute in enumerate((5, 1, 3)):
            await db.execute(
                "INSERT INTO issue_comments (issue_id, author_user_id, body, created_at) "
                "VALUES ($1, $2, $3, NOW() - make_interval(mins => $4))",
                issue_id,
                user_id,
                f"comment {i}",
                10 - minute,
            )

        upgraded = migrate(empty_dsn)
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr

        rows = await db.fetch_all(
            "SELECT seq, author_kind, author_user_id, kind, body_md "
            "FROM issue_thread_messages WHERE thread_id = $1 ORDER BY seq",
            thread["id"],
        )
        assert [(r["seq"], r["kind"]) for r in rows] == [
            (1, "event"),
            (2, "comment"),
            (3, "comment"),
            (4, "comment"),
        ]
        assert [r["body_md"] for r in rows[1:]] == ["comment 1", "comment 2", "comment 0"]
        assert all(r["author_user_id"] == user_id for r in rows[1:])
        gone = await db.fetch_one("SELECT to_regclass('issue_comments') AS t")
        assert gone is not None and gone["t"] is None
    finally:
        await db.close()
