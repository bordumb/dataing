"""Integration tests for IssueThreadRepository on the migrated schema."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository

pytestmark = pytest.mark.integration


async def _issue(db: AppDatabase) -> tuple[UUID, UUID, UUID]:
    """Create a tenant, a user and an issue; return their ids."""
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    user_id = uuid4()
    await db.execute(
        "INSERT INTO users (id, email, name) VALUES ($1, $2, 'Maya')",
        user_id,
        f"{user_id.hex[:12]}@example.com",
    )
    issue_id = uuid4()
    await db.execute(
        "INSERT INTO issues (id, tenant_id, number, title) VALUES ($1, $2, 1, 'x')",
        issue_id,
        tenant_id,
    )
    return tenant_id, user_id, issue_id


async def test_ensure_shared_thread_is_idempotent(migrated_db: AppDatabase) -> None:
    """Racing callers get the same shared thread."""
    tenant_id, _, issue_id = await _issue(migrated_db)
    repo = IssueThreadRepository(migrated_db)

    threads = await asyncio.gather(*(repo.ensure_shared_thread(issue_id) for _ in range(5)))

    assert len({t["id"] for t in threads}) == 1
    assert threads[0]["tenant_id"] == tenant_id
    assert threads[0]["kind"] == "shared"


async def test_concurrent_appends_get_unique_increasing_seq(migrated_db: AppDatabase) -> None:
    """Seq is assigned under the thread row lock, so concurrent posts never collide."""
    _, user_id, issue_id = await _issue(migrated_db)
    repo = IssueThreadRepository(migrated_db)
    thread = await repo.ensure_shared_thread(issue_id)

    messages = await asyncio.gather(
        *(
            repo.append_message(
                thread["id"],
                author_kind="user",
                kind="comment",
                author_user_id=user_id,
                body_md=f"comment {i}",
            )
            for i in range(20)
        )
    )

    assert sorted(m["seq"] for m in messages) == list(range(1, 21))
    listed = await repo.list_messages(thread["id"], after_seq=0, limit=100)
    assert [m["seq"] for m in listed] == list(range(1, 21))


async def test_changes_since_returns_updates_and_recent_rows(migrated_db: AppDatabase) -> None:
    """Rows updated after the cursor come back, as do rows touched in the overlap window."""
    _, user_id, issue_id = await _issue(migrated_db)
    repo = IssueThreadRepository(migrated_db)
    thread = await repo.ensure_shared_thread(issue_id)
    first = await repo.append_message(
        thread["id"], author_kind="agent", kind="agent_reply", status="streaming"
    )
    second = await repo.append_message(
        thread["id"], author_kind="user", kind="comment", author_user_id=user_id, body_md="hi"
    )
    cursor = second["rev"]

    updated = await repo.update_message(first["id"], body_md="partial answer")
    assert updated is not None

    no_overlap = await repo.changes_since(thread["id"], after_rev=cursor, overlap_seconds=0)
    assert [m["id"] for m in no_overlap] == [first["id"]]
    assert no_overlap[0]["body_md"] == "partial answer"

    with_overlap = await repo.changes_since(thread["id"], after_rev=cursor, overlap_seconds=60)
    assert {m["id"] for m in with_overlap} == {first["id"], second["id"]}


async def test_payload_round_trips_as_a_dict(migrated_db: AppDatabase) -> None:
    """JSONB has no codec here, so the repository decodes payloads."""
    _, _, issue_id = await _issue(migrated_db)
    repo = IssueThreadRepository(migrated_db)
    thread = await repo.ensure_shared_thread(issue_id)

    message = await repo.append_message(
        thread["id"],
        author_kind="system",
        kind="event",
        payload={"event_type": "status_changed", "to": "triaged"},
    )

    assert message["payload"] == {"event_type": "status_changed", "to": "triaged"}
    fetched = await repo.get_message(message["id"])
    assert fetched is not None
    assert fetched["payload"]["to"] == "triaged"


async def test_append_event_creates_the_shared_thread(migrated_db: AppDatabase) -> None:
    """Issue events land in the shared thread even if nobody opened it yet."""
    _, user_id, issue_id = await _issue(migrated_db)
    await migrated_db.execute("DELETE FROM issue_threads WHERE issue_id = $1", issue_id)
    repo = IssueThreadRepository(migrated_db)

    message = await repo.append_event(
        issue_id, "status_changed", user_id, {"from": "open", "to": "triaged"}
    )

    assert message["kind"] == "event"
    assert message["author_kind"] == "system"
    assert "triaged" in message["body_md"]


async def test_scratch_threads_are_listed_only_for_their_owner(migrated_db: AppDatabase) -> None:
    """list_threads returns the shared thread plus the caller's own scratch threads."""
    tenant_id, user_id, issue_id = await _issue(migrated_db)
    other_id = uuid4()
    await migrated_db.execute(
        "INSERT INTO users (id, email) VALUES ($1, $2)", other_id, f"{other_id.hex}@x.com"
    )
    repo = IssueThreadRepository(migrated_db)
    await repo.ensure_shared_thread(issue_id)
    mine = await repo.create_scratch_thread(tenant_id, issue_id, user_id, "enum check")
    await repo.create_scratch_thread(tenant_id, issue_id, other_id, "theirs")

    threads = await repo.list_threads(issue_id, user_id)

    assert [t["kind"] for t in threads] == ["shared", "scratch"]
    assert threads[1]["id"] == mine["id"]


async def test_running_turns_are_counted_per_person(migrated_db: AppDatabase) -> None:
    """Queued and streaming agent replies count toward the per-person limit."""
    _, user_id, issue_id = await _issue(migrated_db)
    repo = IssueThreadRepository(migrated_db)
    thread = await repo.ensure_shared_thread(issue_id)
    for status in ("queued", "streaming", "complete"):
        await repo.append_message(
            thread["id"],
            author_kind="agent",
            kind="agent_reply",
            requested_by_user_id=user_id,
            status=status,
        )

    assert await repo.count_running_turns(user_id) == 2


async def _snapshot(db: AppDatabase, tenant_id: UUID, message_id: UUID, sql: str) -> UUID:
    row = await db.execute_returning(
        """
        INSERT INTO agent_query_results (
            tenant_id, message_id, tool_call_id, sql, dialect, columns, rows, row_count
        )
        VALUES ($1, $2, 'call-1', $3, 'postgres', '[{"name": "n"}]', '[{"n": 7}]', 1)
        RETURNING id
        """,
        tenant_id,
        message_id,
        sql,
    )
    assert row is not None
    result_id: UUID = row["id"]
    return result_id


async def test_publish_copies_messages_and_snapshots(migrated_db: AppDatabase) -> None:
    """The published message carries copies of the snapshots, so the scratch chat can go."""
    tenant_id, user_id, issue_id = await _issue(migrated_db)
    repo = IssueThreadRepository(migrated_db)
    shared = await repo.ensure_shared_thread(issue_id)
    scratch = await repo.create_scratch_thread(tenant_id, issue_id, user_id, "enum check")
    question = await repo.append_message(
        scratch["id"], author_kind="user", kind="comment", author_user_id=user_id, body_md="q"
    )
    answer = await repo.append_message(
        scratch["id"], author_kind="agent", kind="agent_reply", body_md="seven"
    )
    original = await _snapshot(migrated_db, tenant_id, answer["id"], "SELECT 7 AS n")
    tool_calls = [
        {"id": "call-1", "tool": "run_query", "summary": "1 row", "query_result_id": str(original)},
        {"id": "call-2", "tool": "list_tables", "summary": "3 tables", "query_result_id": None},
    ]
    answer = await repo.update_message(answer["id"], payload={"tool_calls": tool_calls})
    assert answer is not None

    published = await repo.publish_messages(
        shared["id"],
        source_thread_id=scratch["id"],
        author_user_id=user_id,
        body_md="note\n\nq\n\n**Agent:** seven",
        messages=[question, answer],
    )

    assert published["thread_id"] == shared["id"]
    assert (published["kind"], published["author_kind"]) == ("published", "user")
    assert published["author_user_id"] == user_id
    payload = published["payload"]
    assert payload["source_thread_id"] == str(scratch["id"])
    assert payload["source_message_ids"] == [str(question["id"]), str(answer["id"])]
    (copy_id,) = payload["query_results"]
    assert copy_id != str(original)
    copied_calls = payload["tool_calls"]
    assert [c["id"] for c in copied_calls] == ["call-1", "call-2"]
    assert copied_calls[0]["query_result_id"] == copy_id
    assert copied_calls[1]["query_result_id"] is None
    assert copied_calls[0]["source_message_id"] == str(answer["id"])

    await repo.delete_thread(scratch["id"])

    assert await repo.get_query_result(original) is None
    copy = await repo.get_query_result(UUID(copy_id))
    assert copy is not None
    assert copy["thread_id"] == shared["id"]
    assert copy["message_id"] == published["id"]
    assert (copy["sql"], copy["rows"], copy["row_count"]) == ("SELECT 7 AS n", [{"n": 7}], 1)
    stored = await repo.get_message(published["id"])
    assert stored is not None
    assert stored["body_md"].startswith("note")


async def test_get_messages_returns_the_requested_rows(migrated_db: AppDatabase) -> None:
    """Unknown ids are simply absent."""
    _, user_id, issue_id = await _issue(migrated_db)
    repo = IssueThreadRepository(migrated_db)
    thread = await repo.ensure_shared_thread(issue_id)
    message = await repo.append_message(
        thread["id"], author_kind="user", kind="comment", author_user_id=user_id, body_md="x"
    )

    rows = await repo.get_messages([message["id"], uuid4()])

    assert [r["id"] for r in rows] == [message["id"]]
    assert rows[0]["payload"] == {}
