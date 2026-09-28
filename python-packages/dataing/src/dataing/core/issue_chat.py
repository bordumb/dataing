"""What the issue chat agent can reach, backed by the app database.

ThreadChatServices implements ChatServices for one agent turn: it reads the issue
and its linked runs, runs queries as the asker through AgentQueryService, and
stores a snapshot of every query the agent ran on the reply message.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from dataing.adapters.datasource.gateway import UserPrincipal
from dataing.adapters.db.app_db import AppDatabase
from dataing.core.agent_query import (
    AgentQueryError,
    AgentQueryErrorCode,
    AgentQueryResult,
    AgentQueryService,
)
from dataing.core.json_utils import to_json_string

RECENT_EVENTS = 10


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def resolve_chat_datasource(
    db: AppDatabase, tenant_id: UUID, issue_context: dict[str, Any]
) -> UUID | None:
    """Pick the datasource the agent queries for an issue.

    Order: the issue's own ``context.datasource_id``, then the tenant's default
    datasource, then its only active datasource. None when it's ambiguous or there
    is none; the agent then explains that no datasource is set.
    """
    explicit = issue_context.get("datasource_id")
    if explicit:
        return UUID(str(explicit))
    sources = [s for s in await db.list_data_sources(tenant_id) if s.get("is_active", True)]
    defaults = [s for s in sources if s.get("is_default")]
    if len(defaults) == 1:
        return UUID(str(defaults[0]["id"]))
    if len(sources) == 1:
        return UUID(str(sources[0]["id"]))
    return None


# Reads a running investigation's live state (current step, hypotheses with their
# ids and statuses, pending steers); None when the run isn't running or can't be read
InvestigationStatusReader = Callable[[str], Awaitable[dict[str, Any] | None]]


class ThreadChatServices:
    """ChatServices for one turn in one thread."""

    def __init__(
        self,
        db: AppDatabase,
        queries: AgentQueryService,
        *,
        tenant_id: UUID,
        issue_id: UUID,
        reply_message_id: UUID,
        principal: UserPrincipal | None,
        investigation_status: InvestigationStatusReader | None = None,
    ) -> None:
        """Initialize the services for one turn.

        Args:
            db: Application database.
            queries: Runs queries as the asker.
            tenant_id: The issue's tenant.
            issue_id: The issue.
            reply_message_id: The agent reply that query snapshots belong to.
            principal: The asker and datasource, or None when no datasource is set.
            investigation_status: Reads a running investigation's live hypotheses,
                so the agent can name one in a rule_out proposal.
        """
        self._investigation_status = investigation_status
        self._db = db
        self._queries = queries
        self._tenant_id = tenant_id
        self._issue_id = issue_id
        self._reply_message_id = reply_message_id
        self._principal = principal

    def _require_principal(self) -> UserPrincipal:
        if self._principal is None:
            raise AgentQueryError(
                AgentQueryErrorCode.NO_DATASOURCE,
                "No datasource is set for this issue and the tenant has no single default. "
                "Set one on the issue to let the agent query it.",
            )
        return self._principal

    async def issue_context(self) -> dict[str, Any]:
        """Return the issue, its labels, recent events and linked runs."""
        issue = await self._db.fetch_one(
            """
            SELECT id, number, title, description, status, priority, severity, dataset_id,
                   context, assignee_user_id, resolution_note, created_at
            FROM issues WHERE id = $1 AND tenant_id = $2
            """,
            self._issue_id,
            self._tenant_id,
        )
        if issue is None:
            return {"error": "not_found"}
        issue["context"] = _json(issue.get("context")) or {}
        labels = await self._db.fetch_all(
            "SELECT label FROM issue_labels WHERE issue_id = $1 ORDER BY label", self._issue_id
        )
        events = await self._db.fetch_all(
            """
            SELECT event_type, payload, created_at FROM issue_events
            WHERE issue_id = $1 ORDER BY created_at DESC LIMIT $2
            """,
            self._issue_id,
            RECENT_EVENTS,
        )
        runs = await self._db.fetch_all(
            """
            SELECT r.investigation_id, r.execution_profile, r.confidence, r.root_cause_tag,
                   r.synthesis_summary, r.created_at, i.status
            FROM issue_investigation_runs r
            JOIN investigations i ON i.id = r.investigation_id
            WHERE r.issue_id = $1 ORDER BY r.created_at DESC
            """,
            self._issue_id,
        )
        return {
            "issue": issue,
            "labels": [row["label"] for row in labels],
            "recent_events": [{**e, "payload": _json(e["payload"])} for e in events],
            "investigations": runs,
            "datasource_id": str(self._principal.datasource_id) if self._principal else None,
        }

    async def run_query(self, sql: str, purpose: str) -> AgentQueryResult:
        """Run a read-only query as the asker."""
        return await self._queries.run(self._require_principal(), sql, purpose)

    async def save_query_result(
        self,
        tool_call_id: str,
        sql: str,
        result: AgentQueryResult | None,
        error: str | None,
    ) -> UUID:
        """Store what the agent saw with the reply message."""
        principal = self._principal
        row = await self._db.execute_returning(
            """
            INSERT INTO agent_query_results (
                tenant_id, message_id, tool_call_id, datasource_id, sql, dialect,
                columns, rows, row_count, truncated, duration_ms, error
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            self._tenant_id,
            self._reply_message_id,
            tool_call_id,
            principal.datasource_id if principal else None,
            result.sql if result else sql,
            result.dialect if result else "",
            to_json_string(result.columns if result else []),
            to_json_string(result.rows if result else []),
            result.row_count if result else 0,
            result.truncated if result else False,
            result.duration_ms if result else 0,
            error,
        )
        if row is None:
            raise RuntimeError("Failed to store query result")
        snapshot_id: UUID = row["id"]
        return snapshot_id

    async def list_tables(self, pattern: str | None) -> dict[str, Any]:
        """List tables the asker can see."""
        listing = await self._queries.list_tables(self._require_principal(), pattern)
        return listing.to_dict()

    async def describe_table(self, table: str) -> dict[str, Any]:
        """Describe one table's columns."""
        description = await self._queries.describe_table(self._require_principal(), table)
        return description.to_dict()

    async def get_investigation(self, run_id: str) -> dict[str, Any] | None:
        """Return an investigation linked to this issue, or None."""
        try:
            investigation_id = UUID(run_id)
        except ValueError:
            return None
        row = await self._db.fetch_one(
            """
            SELECT r.investigation_id, r.brief, r.execution_profile, r.confidence,
                   r.root_cause_tag, r.synthesis_summary, i.status, i.outcome
            FROM issue_investigation_runs r
            JOIN investigations i ON i.id = r.investigation_id
            WHERE r.issue_id = $1 AND r.investigation_id = $2
            """,
            self._issue_id,
            investigation_id,
        )
        if row is None:
            return None
        row["brief"] = _json(row.get("brief"))
        row["outcome"] = _json(row.get("outcome"))
        steers = await self._db.fetch_all(
            """
            SELECT kind, text, hypothesis_id, status, outcome, created_at
            FROM investigation_steers WHERE investigation_id = $1 ORDER BY created_at
            """,
            investigation_id,
        )
        row["steers"] = steers
        if self._investigation_status is not None and row.get("outcome") is None:
            # Still running: the workflow knows the hypotheses and how each is going
            row["live"] = await self._investigation_status(str(investigation_id))
        result: dict[str, Any] = row
        return result
