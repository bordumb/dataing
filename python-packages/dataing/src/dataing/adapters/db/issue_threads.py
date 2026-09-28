"""Persistence for issue threads and their messages (docs/specs/0001_issue_chat.md).

Every issue has one shared thread and any number of private scratch threads.
Messages hold comments, agent replies and system events in one timeline:

- ``seq`` orders messages inside a thread. It is assigned in the transaction
  that locks the thread row, so concurrent posts never collide.
- ``rev`` moves on every insert and update (a trigger bumps it), so a stream can
  resume from the last ``rev`` it sent. ``touched_at`` is clock time, so a
  poller can re-read rows that committed after a newer ``rev`` was already seen.

JSONB has no codec on this pool: payloads are written as JSON text and decoded
on the way out.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string

MESSAGE_COLUMNS = """
    id, tenant_id, thread_id, seq, rev, author_kind, author_user_id,
    requested_by_user_id, request_message_id, kind, body_md, payload, status,
    asks_agent, reply_to_id, created_at, updated_at, touched_at, edited_at, deleted_at
"""

THREAD_COLUMNS = "id, tenant_id, issue_id, kind, owner_user_id, title, created_at, updated_at"

RUNNING_STATUSES = ("queued", "streaming")


def _decode_message(row: dict[str, Any]) -> dict[str, Any]:
    """Return a message row with its payload decoded to a dict."""
    payload = row.get("payload")
    if isinstance(payload, str):
        row["payload"] = json.loads(payload)
    elif payload is None:
        row["payload"] = {}
    return row


def describe_event(event_type: str, payload: dict[str, Any]) -> str:
    """Return a one-line, human-readable description of an issue event."""
    if event_type == "status_changed":
        return f"Status changed from {payload.get('from', '?')} to {payload.get('to', '?')}"
    if event_type in ("assigned", "assignee_changed"):
        assignee = payload.get("to") or payload.get("assignee_user_id")
        return "Unassigned" if not assignee else "Assignee changed"
    if event_type == "investigation_spawned":
        return "Investigation started"
    if event_type == "investigation_completed":
        return "Investigation finished"
    if event_type in ("label_added", "label_removed"):
        verb = "added" if event_type == "label_added" else "removed"
        return f"Label {payload.get('label', '')} {verb}".strip()
    if event_type == "acknowledged":
        return "Acknowledged" if payload.get("to") else "Acknowledgment cleared"
    if event_type in ("priority_changed", "severity_changed"):
        field = event_type.removesuffix("_changed").capitalize()
        return _change_text(field, payload.get("from"), payload.get("to"))
    if event_type == "field_changed":
        field = str(payload.get("field", "field")).replace("_", " ").capitalize()
        return _change_text(field, payload.get("from"), payload.get("to"))
    return event_type.replace("_", " ").capitalize()


def _change_text(field: str, before: Any, after: Any) -> str:
    """Describe a field change, keeping long values out of the timeline."""

    def show(value: Any) -> str:
        text = "none" if value in (None, "") else str(value)
        return text if len(text) <= 40 else "a new value"

    if after in (None, ""):
        return f"{field} cleared"
    if before in (None, ""):
        return f"{field} set to {show(after)}"
    return f"{field} changed from {show(before)} to {show(after)}"


class IssueThreadRepository:
    """Reads and writes issue threads and thread messages."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository with the application database."""
        self._db = db

    # Threads

    async def ensure_shared_thread(self, issue_id: UUID) -> dict[str, Any]:
        """Return the issue's shared thread, creating it if needed.

        Raises:
            LookupError: If the issue does not exist.
        """
        await self._db.execute(
            """
            INSERT INTO issue_threads (tenant_id, issue_id, kind)
            SELECT tenant_id, id, 'shared' FROM issues WHERE id = $1
            ON CONFLICT (issue_id) WHERE kind = 'shared' DO NOTHING
            """,
            issue_id,
        )
        row = await self._db.fetch_one(
            f"SELECT {THREAD_COLUMNS} FROM issue_threads WHERE issue_id = $1 AND kind = 'shared'",
            issue_id,
        )
        if row is None:
            raise LookupError(f"Issue not found: {issue_id}")
        return row

    async def create_scratch_thread(
        self, tenant_id: UUID, issue_id: UUID, owner_user_id: UUID, title: str | None
    ) -> dict[str, Any]:
        """Create a private scratch thread on an issue."""
        row = await self._db.execute_returning(
            f"""
            INSERT INTO issue_threads (tenant_id, issue_id, kind, owner_user_id, title)
            VALUES ($1, $2, 'scratch', $3, $4)
            RETURNING {THREAD_COLUMNS}
            """,
            tenant_id,
            issue_id,
            owner_user_id,
            title,
        )
        if row is None:
            raise RuntimeError("Failed to create scratch thread")
        return row

    async def get_thread(self, thread_id: UUID) -> dict[str, Any] | None:
        """Return a thread by id."""
        return await self._db.fetch_one(
            f"SELECT {THREAD_COLUMNS} FROM issue_threads WHERE id = $1", thread_id
        )

    async def list_threads(self, issue_id: UUID, user_id: UUID | None) -> list[dict[str, Any]]:
        """Return the shared thread and the caller's own scratch threads, shared first."""
        await self.ensure_shared_thread(issue_id)
        return await self._db.fetch_all(
            f"""
            SELECT {THREAD_COLUMNS} FROM issue_threads
            WHERE issue_id = $1 AND (kind = 'shared' OR owner_user_id = $2)
            ORDER BY (kind = 'shared') DESC, created_at ASC
            """,
            issue_id,
            user_id,
        )

    async def delete_thread(self, thread_id: UUID) -> None:
        """Delete a thread and its messages."""
        await self._db.execute("DELETE FROM issue_threads WHERE id = $1", thread_id)

    # Messages

    async def append_message(
        self,
        thread_id: UUID,
        *,
        author_kind: str,
        kind: str,
        body_md: str = "",
        payload: dict[str, Any] | None = None,
        author_user_id: UUID | None = None,
        requested_by_user_id: UUID | None = None,
        request_message_id: UUID | None = None,
        status: str = "complete",
        asks_agent: bool = False,
        reply_to_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Append a message to a thread with the next seq.

        The thread row is locked first and seq is read in a later statement of the
        same transaction, so that statement's snapshot includes every append that
        committed before the lock was granted. Concurrent appends therefore get
        consecutive seq values.
        """
        async with self._db.acquire() as conn, conn.transaction():
            thread = await conn.fetchrow(
                "SELECT id, tenant_id FROM issue_threads WHERE id = $1 FOR UPDATE", thread_id
            )
            if thread is None:
                raise LookupError(f"Thread not found: {thread_id}")
            row = await conn.fetchrow(
                f"""
                INSERT INTO issue_thread_messages (
                    tenant_id, thread_id, seq, author_kind, author_user_id,
                    requested_by_user_id, request_message_id, kind, body_md, payload,
                    status, asks_agent, reply_to_id
                )
                SELECT $1, $2,
                       COALESCE(
                           (SELECT MAX(seq) FROM issue_thread_messages WHERE thread_id = $2),
                           0
                       ) + 1,
                       $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                RETURNING {MESSAGE_COLUMNS}
                """,
                thread["tenant_id"],
                thread_id,
                author_kind,
                author_user_id,
                requested_by_user_id,
                request_message_id,
                kind,
                body_md,
                to_json_string(payload or {}),
                status,
                asks_agent,
                reply_to_id,
            )
        if row is None:
            raise RuntimeError("Failed to append message")
        return _decode_message(dict(row))

    async def append_event(
        self,
        issue_id: UUID,
        event_type: str,
        actor_user_id: UUID | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a system event message to the issue's shared thread."""
        data = payload or {}
        thread = await self.ensure_shared_thread(issue_id)
        return await self.append_message(
            thread["id"],
            author_kind="system",
            kind="event",
            author_user_id=actor_user_id,
            body_md=describe_event(event_type, data),
            payload={"event_type": event_type, **data},
        )

    async def get_message(self, message_id: UUID) -> dict[str, Any] | None:
        """Return a message by id."""
        row = await self._db.fetch_one(
            f"SELECT {MESSAGE_COLUMNS} FROM issue_thread_messages WHERE id = $1", message_id
        )
        return _decode_message(row) if row else None

    async def get_reply_for_request(self, request_message_id: UUID) -> dict[str, Any] | None:
        """Return the agent reply created for a request message, if any."""
        row = await self._db.fetch_one(
            f"SELECT {MESSAGE_COLUMNS} FROM issue_thread_messages WHERE request_message_id = $1",
            request_message_id,
        )
        return _decode_message(row) if row else None

    async def update_message(
        self,
        message_id: UUID,
        *,
        body_md: str | None = None,
        payload: dict[str, Any] | None = None,
        status: str | None = None,
        edited: bool = False,
    ) -> dict[str, Any] | None:
        """Update a message's body, payload or status; unset fields are unchanged."""
        row = await self._db.execute_returning(
            f"""
            UPDATE issue_thread_messages SET
                body_md = COALESCE($2, body_md),
                payload = COALESCE($3::jsonb, payload),
                status = COALESCE($4, status),
                edited_at = CASE WHEN $5 THEN NOW() ELSE edited_at END
            WHERE id = $1
            RETURNING {MESSAGE_COLUMNS}
            """,
            message_id,
            body_md,
            to_json_string(payload) if payload is not None else None,
            status,
            edited,
        )
        return _decode_message(row) if row else None

    async def soft_delete_message(self, message_id: UUID) -> dict[str, Any] | None:
        """Mark a message deleted and clear its body."""
        row = await self._db.execute_returning(
            f"""
            UPDATE issue_thread_messages
            SET deleted_at = NOW(), body_md = ''
            WHERE id = $1
            RETURNING {MESSAGE_COLUMNS}
            """,
            message_id,
        )
        return _decode_message(row) if row else None

    async def list_messages(
        self, thread_id: UUID, *, after_seq: int = 0, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Return messages after a seq, oldest first."""
        rows = await self._db.fetch_all(
            f"""
            SELECT {MESSAGE_COLUMNS} FROM issue_thread_messages
            WHERE thread_id = $1 AND seq > $2
            ORDER BY seq ASC
            LIMIT $3
            """,
            thread_id,
            after_seq,
            limit,
        )
        return [_decode_message(r) for r in rows]

    async def changes_since(
        self, thread_id: UUID, *, after_rev: int, overlap_seconds: float = 5.0
    ) -> list[dict[str, Any]]:
        """Return messages written after a rev, plus any touched in the overlap window.

        The overlap re-reads rows whose transaction committed after a newer rev was
        already streamed. Callers de-duplicate by (id, rev).
        """
        rows = await self._db.fetch_all(
            f"""
            SELECT {MESSAGE_COLUMNS} FROM issue_thread_messages
            WHERE thread_id = $1
              AND (rev > $2 OR touched_at >= clock_timestamp() - make_interval(secs => $3))
            ORDER BY rev ASC
            LIMIT 500
            """,
            thread_id,
            after_rev,
            float(overlap_seconds),
        )
        return [_decode_message(r) for r in rows]

    async def get_query_result(self, result_id: UUID) -> dict[str, Any] | None:
        """Return a query snapshot with the thread its message belongs to."""
        row = await self._db.fetch_one(
            """
            SELECT r.id, r.message_id, r.tool_call_id, r.datasource_id, r.sql, r.dialect,
                   r.columns, r.rows, r.row_count, r.truncated, r.duration_ms, r.error,
                   r.created_at, m.thread_id
            FROM agent_query_results r
            JOIN issue_thread_messages m ON m.id = r.message_id
            WHERE r.id = $1
            """,
            result_id,
        )
        if row is None:
            return None
        for key in ("columns", "rows"):
            if isinstance(row[key], str):
                row[key] = json.loads(row[key])
        return row

    async def count_running_turns(self, user_id: UUID) -> int:
        """Count agent turns the person has queued or streaming, across threads."""
        row = await self._db.fetch_one(
            """
            SELECT COUNT(*) AS n FROM issue_thread_messages
            WHERE requested_by_user_id = $1 AND status = ANY($2::text[])
            """,
            user_id,
            list(RUNNING_STATUSES),
        )
        return int(row["n"]) if row else 0

    async def fail_stale_turns(self, reason: str) -> int:
        """Mark every queued or streaming turn as failed (worker restart)."""
        status = await self._db.execute(
            """
            UPDATE issue_thread_messages
            SET status = 'error',
                payload = payload || jsonb_build_object('error', $1::text)
            WHERE status = ANY($2::text[])
            """,
            reason,
            list(RUNNING_STATUSES),
        )
        try:
            return int(status.split()[-1])
        except (ValueError, IndexError):
            return 0
