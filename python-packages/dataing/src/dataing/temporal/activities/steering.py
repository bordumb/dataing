"""Activities for steering a running investigation (docs/specs/0001_issue_chat.md §7.8)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from temporalio import activity

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 120

PHASE_WORDS = {
    "before_hypotheses": "before hypotheses were generated",
    "evaluation": "during evaluation",
    "synthesis": "during synthesis",
    "finished": "after the run",
}


@activity.defn(name="formulate_hypothesis")
async def formulate_hypothesis(payload: dict[str, Any]) -> dict[str, Any]:
    """Turn a person's text into a hypothesis a subagent can test.

    The subagent writes the query itself, so the text becomes the title and
    reasoning as the person wrote it; no model call is needed here.
    """
    text = " ".join(str(payload.get("text") or "").split())
    title = text if len(text) <= MAX_TITLE_CHARS else f"{text[: MAX_TITLE_CHARS - 3]}..."
    return {
        "hypothesis": {
            "id": payload["hypothesis_id"],
            "title": title,
            "category": "data_quality",
            "reasoning": f"A person asked the investigation to test this: {text}",
            "suggested_query": "",
        }
    }


def steer_outcome_text(status: str, phase: str, outcome: str) -> str:
    """Return the thread line for a steer's outcome."""
    if status == "applied":
        return f"Applied {PHASE_WORDS.get(phase, phase)}: {outcome}"
    return f"Not applied: {outcome}"


def make_record_steer_outcome_activity(app_db: AppDatabase) -> Any:
    """Return the record_steer_outcome activity with its database bound."""

    @activity.defn(name="record_steer_outcome")
    async def record_steer_outcome(payload: dict[str, Any]) -> dict[str, Any]:
        """Mark a steer applied or rejected and say so in the issue thread.

        Both steps are idempotent, so a retried attempt records the outcome once.
        """
        try:
            steer_id = UUID(str(payload["steer_id"]))
        except ValueError:
            logger.warning(f"Steer id is not a UUID: {payload.get('steer_id')}")
            return {"recorded": False}
        status = str(payload["status"])
        phase = str(payload.get("phase") or "")
        outcome = str(payload.get("outcome") or "")

        await app_db.execute(
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
        steer = await app_db.fetch_one(
            "SELECT issue_id, kind, hypothesis_id FROM investigation_steers WHERE id = $1",
            steer_id,
        )
        if steer is None or steer["issue_id"] is None:
            return {"recorded": steer is not None, "thread_message": False}

        threads = IssueThreadRepository(app_db)
        thread = await threads.ensure_shared_thread(steer["issue_id"])
        existing = await app_db.fetch_one(
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
                body_md=steer_outcome_text(status, phase, outcome),
                payload={
                    "outcome_for": str(steer_id),
                    "steer_id": str(steer_id),
                    "investigation_id": str(payload.get("investigation_id") or ""),
                    "kind": steer["kind"],
                    "hypothesis_id": steer["hypothesis_id"],
                    "status": status,
                    "phase": phase,
                    "outcome": outcome,
                },
            )
        return {"recorded": True, "thread_message": existing is None}

    return record_steer_outcome
