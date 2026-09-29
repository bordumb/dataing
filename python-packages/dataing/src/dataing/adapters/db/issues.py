"""Issues and their investigation runs in the app database.

open_issue() is the one way to insert an issue: the API, both webhooks and the
investigation starter use it, so every issue's shared thread starts with the event
that opened it (docs/specs/0001_issue_chat.md §7.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.core.json_utils import to_json_string

ISSUE_COLUMNS = """id, number, title, description, status, priority, severity,
               dataset_id, due_at, assignee_user_id, acknowledged_by, created_by_user_id,
               author_type, source_provider, source_external_id, source_external_url,
               resolution_note, context, created_at, updated_at, closed_at"""

RUN_COLUMNS = """
    id, issue_id, investigation_id, trigger_type, brief, source_thread_id, parent_run_id,
    execution_profile, approval_status, confidence, root_cause_tag, synthesis_summary,
    created_at, completed_at, outcome_verdict, outcome_note, outcome_reviewed_by,
    outcome_reviewed_at
"""

# A run with its number among the issue's runs, and how it ended so far
_RUNS = f"""
    SELECT {", ".join(f"r.{column.strip()}" for column in RUN_COLUMNS.split(","))},
           ROW_NUMBER() OVER (PARTITION BY r.issue_id ORDER BY r.created_at, r.id) AS number,
           CASE WHEN i.outcome IS NULL THEN 'running'
                ELSE COALESCE(i.outcome->>'status', 'completed') END AS status,
           i.outcome->'error'->>'message' AS error
    FROM issue_investigation_runs r
    JOIN investigations i ON i.id = r.investigation_id
"""

# A new comment and a new investigation are already messages in the thread (a
# comment, an investigation card), so those events are only in the event log.
THREAD_SILENT_EVENTS = frozenset({"comment_added", "investigation_spawned"})


async def record_issue_event(
    db: AppDatabase,
    issue_id: UUID,
    event_type: str,
    actor_user_id: UUID | None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Record an issue event and show it in the issue's shared thread."""
    await db.execute(
        """
        INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
        VALUES ($1, $2, $3, $4)
        """,
        issue_id,
        event_type,
        actor_user_id,
        to_json_string(payload or {}),
    )
    if event_type not in THREAD_SILENT_EVENTS:
        await IssueThreadRepository(db).append_event(issue_id, event_type, actor_user_id, payload)


async def open_issue(
    db: AppDatabase,
    *,
    tenant_id: UUID,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    severity: str | None = None,
    dataset_id: str | None = None,
    labels: Sequence[str] = (),
    context: dict[str, Any] | None = None,
    created_by: UUID | None = None,
    author_type: str = "human",
    source_provider: str | None = None,
    source_external_id: str | None = None,
    source_external_url: str | None = None,
    event_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert an open issue, with its labels and the event that opens its thread.

    Args:
        db: The app database.
        tenant_id: The issue's tenant.
        title: What is wrong, in a line.
        description: More detail, as markdown.
        priority: P0-P3.
        severity: low, medium, high or critical.
        dataset_id: The affected table, as a native path.
        labels: Labels to add.
        context: Where the problem was seen, e.g. observed_at and column.
        created_by: The person who opened it; None when an integration or dataing did.
        author_type: human or integration.
        source_provider: The integration it came from, e.g. monte_carlo.
        source_external_id: The source's id for it, the webhook dedup key.
        source_external_url: A link back to the source.
        event_payload: Extra fields for the opening event.

    Returns:
        The issue row.
    """
    number_row = await db.fetch_one("SELECT next_issue_number($1) AS number", tenant_id)
    number = number_row["number"] if number_row else 1
    row = await db.execute_returning(
        f"""
        INSERT INTO issues (
            tenant_id, number, title, description, status, priority, severity, dataset_id,
            created_by_user_id, author_type, source_provider, source_external_id,
            source_external_url, context
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        RETURNING {ISSUE_COLUMNS}
        """,
        tenant_id,
        number,
        title,
        description,
        "open",
        priority,
        severity,
        dataset_id,
        created_by,
        author_type,
        source_provider,
        source_external_id,
        source_external_url,
        to_json_string(context or {}),
    )
    if row is None:
        raise RuntimeError("Failed to create issue")
    for label in labels:
        await db.execute(
            "INSERT INTO issue_labels (issue_id, label) VALUES ($1, $2)", row["id"], label
        )
    opened: dict[str, Any] = {"title": title}
    if source_provider:
        opened["source_provider"] = source_provider
    await record_issue_event(
        db, row["id"], "created", created_by, {**opened, **(event_payload or {})}
    )
    return row


async def list_runs(db: AppDatabase, issue_id: UUID) -> list[dict[str, Any]]:
    """Return an issue's investigation runs, newest first."""
    return await db.fetch_all(
        f"{_RUNS} WHERE r.issue_id = $1 ORDER BY r.created_at DESC, r.id DESC", issue_id
    )


async def get_run(db: AppDatabase, run_id: UUID) -> dict[str, Any] | None:
    """Return one investigation run, numbered among its issue's runs."""
    return await db.fetch_one(
        f"""
        SELECT * FROM ({_RUNS}
            WHERE r.issue_id = (SELECT issue_id FROM issue_investigation_runs WHERE id = $1)
        ) runs
        WHERE id = $1
        """,
        run_id,
    )
