"""Activity that publishes a finished investigation's outcome (spec 0001 §7.7, §7.12).

It writes the outcome to the investigation (the 036 trigger stamps completed_at),
fills the linked issue run's summary fields, and posts the result card to the
issue's shared thread. A failed run publishes its failure the same way, as
{"status": "failed", "error": {code, message, step}}. Every step is idempotent, so a
retried attempt changes nothing twice.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from temporalio import activity

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.core.json_utils import to_json_string

logger = logging.getLogger(__name__)


def outcome_markdown(synthesis: dict[str, Any], hypotheses: list[dict[str, Any]]) -> str:
    """Render the outcome card's text for the thread."""
    root_cause = synthesis.get("root_cause") or "No root cause was established."
    confidence = synthesis.get("confidence")
    lines = ["**Investigation finished**", "", f"**Root cause:** {root_cause}"]
    if isinstance(confidence, int | float):
        lines.append(f"**Confidence:** {confidence:.2f}")
    if hypotheses:
        lines += ["", "**Hypotheses**"]
        lines += [f"- {h.get('title') or h.get('id')}: {h.get('status')}" for h in hypotheses]
    recommendations = synthesis.get("recommendations") or []
    if recommendations:
        lines += ["", "**Recommendations**", *[f"- {r}" for r in recommendations]]
    return "\n".join(lines)


def failure_markdown(failure: dict[str, Any]) -> str:
    """Render a failed run's card text for the thread."""
    return f"**Investigation failed**\n\n{failure.get('message') or 'The run failed.'}"


def make_publish_investigation_outcome_activity(app_db: AppDatabase) -> Any:
    """Return the publish_investigation_outcome activity with its database bound."""

    @activity.defn(name="publish_investigation_outcome")
    async def publish_investigation_outcome(payload: dict[str, Any]) -> dict[str, Any]:
        """Write the outcome to the investigation, its issue run and the issue thread."""
        investigation_id = UUID(str(payload["investigation_id"]))
        tenant_id = UUID(str(payload["tenant_id"]))
        synthesis: dict[str, Any] = payload.get("synthesis") or {}
        hypotheses: list[dict[str, Any]] = payload.get("hypotheses") or []
        failure: dict[str, Any] | None = payload.get("failure")
        outcome: dict[str, Any]
        if failure:
            outcome = {"status": "failed", "error": failure, "hypotheses": hypotheses}
        else:
            outcome = {
                "status": "completed",
                "root_cause": synthesis.get("root_cause"),
                "confidence": synthesis.get("confidence"),
                "recommendations": synthesis.get("recommendations") or [],
                "supporting_evidence": synthesis.get("supporting_evidence") or [],
                "hypotheses": hypotheses,
                "counter_analysis": payload.get("counter_analysis"),
            }
        await app_db.execute(
            "UPDATE investigations SET outcome = $3 WHERE id = $1 AND tenant_id = $2",
            investigation_id,
            tenant_id,
            to_json_string(outcome),
        )

        issue_id_raw = payload.get("issue_id")
        if not issue_id_raw:
            return {"published": True, "thread_message": False}
        issue_id = UUID(str(issue_id_raw))

        run = await app_db.execute_returning(
            """
            UPDATE issue_investigation_runs
            SET synthesis_summary = $3, confidence = $4,
                completed_at = COALESCE(completed_at, NOW())
            WHERE investigation_id = $1 AND issue_id = $2
            RETURNING id
            """,
            investigation_id,
            issue_id,
            synthesis.get("root_cause"),
            synthesis.get("confidence"),
        )

        threads = IssueThreadRepository(app_db)
        thread = await threads.ensure_shared_thread(issue_id)
        existing = await app_db.fetch_one(
            """
            SELECT id FROM issue_thread_messages
            WHERE thread_id = $1 AND kind = 'investigation'
              AND payload->>'outcome_for' = $2
            """,
            thread["id"],
            str(investigation_id),
        )
        if existing is None:
            await threads.append_message(
                thread["id"],
                author_kind="agent",
                kind="investigation",
                body_md=(
                    failure_markdown(failure)
                    if failure
                    else outcome_markdown(synthesis, hypotheses)
                ),
                payload={
                    "phase": "outcome",
                    "outcome_for": str(investigation_id),
                    "investigation_id": str(investigation_id),
                    "run_id": str(run["id"]) if run else None,
                    "outcome": outcome,
                },
            )
            event_type, event = (
                ("investigation_failed", {"code": failure.get("code")})
                if failure
                else ("investigation_completed", {"confidence": synthesis.get("confidence")})
            )
            await app_db.execute(
                """
                INSERT INTO issue_events (issue_id, event_type, payload)
                VALUES ($1, $2, $3)
                """,
                issue_id,
                event_type,
                to_json_string({"investigation_id": str(investigation_id), **event}),
            )
        return {"published": True, "thread_message": existing is None}

    return publish_investigation_outcome
