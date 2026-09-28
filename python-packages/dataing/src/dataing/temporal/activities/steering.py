"""Activities for steering a running investigation (docs/specs/0001_issue_chat.md §7.8)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from temporalio import activity

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.investigation_steers import InvestigationSteerRepository

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 120


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
        result: dict[str, Any] = await InvestigationSteerRepository(app_db).record_outcome(
            steer_id,
            status=str(payload["status"]),
            phase=str(payload.get("phase") or ""),
            outcome=str(payload.get("outcome") or ""),
            investigation_id=str(payload.get("investigation_id") or ""),
        )
        return result

    return record_steer_outcome
