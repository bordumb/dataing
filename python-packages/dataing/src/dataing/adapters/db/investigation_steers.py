"""Steers people send to running investigations (docs/specs/0001_issue_chat.md §7.8).

A steer is stored pending before the workflow is signalled; the workflow's
record_steer_outcome activity (or the API, when the signal fails) marks it
applied or rejected and says so in the issue's shared thread.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository

STEER_COLUMNS = """
    id, investigation_id, issue_id, message_id, kind, text, hypothesis_id, actor_user_id,
    status, applied_phase, outcome, created_at, applied_at
"""

PHASE_WORDS = {
    "before_hypotheses": "before hypotheses were generated",
    "evaluation": "during evaluation",
    "synthesis": "during synthesis",
    "finished": "after the run",
}

KIND_WORDS = {
    "add_context": "Add context",
    "rule_out": "Rule out",
    "add_hypothesis": "Add hypothesis",
    "stop_and_synthesize": "Stop and conclude",
}


def steer_outcome_text(status: str, phase: str, outcome: str) -> str:
    """Return the thread line for a steer's outcome."""
    if status == "applied":
        return f"Applied {PHASE_WORDS.get(phase, phase)}: {outcome}"
    return f"Not applied: {outcome}"


def steer_request_text(kind: str, text: str, hypothesis_id: str | None) -> str:
    """Return the thread line for a steer a person sent."""
    target = f" {hypothesis_id}" if hypothesis_id else ""
    body = f": {text}" if text else ""
    return f"**{KIND_WORDS.get(kind, kind)}{target}**{body}"


class InvestigationSteerRepository:
    """Stores steers and their outcomes."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository."""
        self._db = db

    async def find_by_proposal(
        self, investigation_id: UUID, proposal_message_id: UUID
    ) -> dict[str, Any] | None:
        """Return the steer already sent from an agent's proposal, if any."""
        row: dict[str, Any] | None = await self._db.fetch_one(
            f"""
            SELECT {", ".join(f"s.{c.strip()}" for c in STEER_COLUMNS.split(","))}
            FROM investigation_steers s
            JOIN issue_thread_messages m ON m.id = s.message_id
            WHERE s.investigation_id = $1 AND m.payload->>'proposal_message_id' = $2
            """,
            investigation_id,
            str(proposal_message_id),
        )
        return row

    async def create(
        self,
        *,
        tenant_id: UUID,
        investigation_id: UUID,
        issue_id: UUID | None,
        kind: str,
        text: str,
        hypothesis_id: str | None,
        actor_user_id: UUID | None,
        proposal_message_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Store a pending steer, and the person's message in the issue thread."""
        message_id: UUID | None = None
        if issue_id is not None:
            threads = IssueThreadRepository(self._db)
            thread = await threads.ensure_shared_thread(issue_id)
            message = await threads.append_message(
                thread["id"],
                author_kind="user",
                author_user_id=actor_user_id,
                kind="steer",
                body_md=steer_request_text(kind, text, hypothesis_id),
                payload={
                    "investigation_id": str(investigation_id),
                    "kind": kind,
                    "hypothesis_id": hypothesis_id,
                    "proposal_message_id": str(proposal_message_id)
                    if proposal_message_id
                    else None,
                },
            )
            message_id = message["id"]
        row = await self._db.execute_returning(
            f"""
            INSERT INTO investigation_steers
                (tenant_id, investigation_id, issue_id, message_id, kind, text,
                 hypothesis_id, actor_user_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING {STEER_COLUMNS}
            """,
            tenant_id,
            investigation_id,
            issue_id,
            message_id,
            kind,
            text,
            hypothesis_id,
            actor_user_id,
        )
        assert row is not None
        steer: dict[str, Any] = row
        return steer

    async def list_for_investigation(self, investigation_id: UUID) -> list[dict[str, Any]]:
        """Return an investigation's steers, oldest first."""
        rows: list[dict[str, Any]] = await self._db.fetch_all(
            f"""
            SELECT {STEER_COLUMNS} FROM investigation_steers
            WHERE investigation_id = $1 ORDER BY created_at, id
            """,
            investigation_id,
        )
        return rows

    async def get(self, steer_id: UUID) -> dict[str, Any] | None:
        """Return one steer."""
        row: dict[str, Any] | None = await self._db.fetch_one(
            f"SELECT {STEER_COLUMNS} FROM investigation_steers WHERE id = $1", steer_id
        )
        return row

    async def record_outcome(
        self,
        steer_id: UUID,
        *,
        status: str,
        phase: str,
        outcome: str,
        investigation_id: str = "",
    ) -> dict[str, Any]:
        """Mark a pending steer applied or rejected and say so in the issue thread.

        Only a pending steer changes, and the thread gets one outcome message per
        steer, so recording the same outcome again changes nothing.

        Returns:
            {"recorded": bool, "thread_message": bool}.
        """
        await self._db.execute(
            """
            UPDATE investigation_steers
            SET status = $2, applied_phase = $3, outcome = $4, applied_at = NOW()
            WHERE id = $1 AND status = 'pending'
            """,
            steer_id,
            status,
            phase,
            outcome,
        )
        steer = await self.get(steer_id)
        if steer is None or steer["issue_id"] is None:
            return {"recorded": steer is not None, "thread_message": False}

        threads = IssueThreadRepository(self._db)
        thread = await threads.ensure_shared_thread(steer["issue_id"])
        existing = await self._db.fetch_one(
            """
            SELECT id FROM issue_thread_messages
            WHERE thread_id = $1 AND kind = 'steer' AND payload->>'outcome_for' = $2
            """,
            thread["id"],
            str(steer_id),
        )
        if existing is None:
            await threads.append_message(
                thread["id"],
                author_kind="system",
                kind="steer",
                body_md=steer_outcome_text(steer["status"], phase, steer["outcome"] or outcome),
                payload={
                    "outcome_for": str(steer_id),
                    "steer_id": str(steer_id),
                    "investigation_id": investigation_id or str(steer["investigation_id"]),
                    "kind": steer["kind"],
                    "hypothesis_id": steer["hypothesis_id"],
                    "status": steer["status"],
                    "phase": steer["applied_phase"] or phase,
                    "outcome": steer["outcome"] or outcome,
                },
            )
        return {"recorded": True, "thread_message": existing is None}
