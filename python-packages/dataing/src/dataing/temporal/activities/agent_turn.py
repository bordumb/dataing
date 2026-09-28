"""Activities that run one issue chat agent turn (docs/specs/0001_issue_chat.md §7.4).

run_agent_turn answers one request message:

1. It uses the reply the API created when the question was asked (status
   ``queued``), or creates one. A retried attempt reuses the same reply, so a
   crashed worker never leaves two answers.
2. It streams the answer into the reply, flushing new text every FLUSH_SECONDS,
   and heartbeats so a cancelled turn stops promptly.
3. It ends the reply as ``complete`` with the tool calls, steer proposals and
   token usage in its payload, or ``cancelled`` (partial text kept).

mark_turn_failed marks the reply ``error`` once every attempt has failed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from pydantic_ai import Agent
from temporalio import activity

from dataing.adapters.datasource.gateway import UserPrincipal
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.agents.chat import ChatDeps, build_history, build_instructions, run_turn
from dataing.core.agent_query import AgentQueryService
from dataing.core.issue_chat import ThreadChatServices, resolve_chat_datasource

logger = logging.getLogger(__name__)

FLUSH_SECONDS = 0.25
HISTORY_LIMIT = 200

ChatAgentFactory = Callable[[], Agent[ChatDeps, str]]


async def _author_names(db: AppDatabase, user_ids: set[UUID]) -> dict[UUID, str]:
    if not user_ids:
        return {}
    rows = await db.fetch_all(
        "SELECT id, name, email FROM users WHERE id = ANY($1::uuid[])", list(user_ids)
    )
    return {row["id"]: row["name"] or row["email"] for row in rows}


async def _history_for(
    db: AppDatabase, threads: IssueThreadRepository, request: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return earlier thread messages (labelled) and the request message itself."""
    thread_id = request["thread_id"]
    messages = await threads.list_messages(thread_id, after_seq=0, limit=10_000)
    request_msg = next(m for m in messages if m["id"] == request["id"])
    earlier = [
        m
        for m in messages
        if m["seq"] < request_msg["seq"] and m["status"] in ("complete", "cancelled")
    ][-HISTORY_LIMIT:]
    names = await _author_names(
        db,
        {m["author_user_id"] for m in [*earlier, request_msg] if m.get("author_user_id")},
    )
    for message in [*earlier, request_msg]:
        message["author_name"] = names.get(message.get("author_user_id") or UUID(int=0))
    return earlier, request_msg


def make_run_agent_turn_activity(
    app_db: AppDatabase,
    agent_factory: ChatAgentFactory,
    query_service: AgentQueryService | None = None,
) -> Any:
    """Return the run_agent_turn activity with its dependencies bound.

    Args:
        app_db: Application database.
        agent_factory: Builds the chat agent (a fresh one per turn).
        query_service: Runs queries as the asker; built from app_db if omitted.
    """
    queries = query_service or AgentQueryService(app_db)

    @activity.defn(name="run_agent_turn")
    async def run_agent_turn(request: dict[str, Any]) -> dict[str, Any]:
        """Answer one request message in its thread."""
        threads = IssueThreadRepository(app_db)
        request_id = UUID(str(request["message_id"]))
        tenant_id = UUID(str(request["tenant_id"]))
        issue_id = UUID(str(request["issue_id"]))
        requested_by = UUID(str(request["requested_by"]))

        reply = await threads.get_reply_for_request(request_id)
        if reply is None:
            reply = await threads.append_message(
                UUID(str(request["thread_id"])),
                author_kind="agent",
                kind="agent_reply",
                requested_by_user_id=requested_by,
                request_message_id=request_id,
                reply_to_id=request_id,
                status="queued",
            )
        if reply["status"] == "cancelled":
            return {"status": "cancelled"}
        reply_id: UUID = reply["id"]
        await threads.update_message(reply_id, body_md="", payload={}, status="streaming")

        issue_row = await app_db.fetch_one(
            "SELECT context FROM issues WHERE id = $1 AND tenant_id = $2", issue_id, tenant_id
        )
        context_raw = issue_row["context"] if issue_row else "{}"
        issue_context = json.loads(context_raw) if isinstance(context_raw, str) else context_raw
        datasource_id = await resolve_chat_datasource(app_db, tenant_id, issue_context or {})
        principal = (
            UserPrincipal(user_id=requested_by, tenant_id=tenant_id, datasource_id=datasource_id)
            if datasource_id
            else None
        )
        services = ThreadChatServices(
            app_db,
            queries,
            tenant_id=tenant_id,
            issue_id=issue_id,
            reply_message_id=reply_id,
            principal=principal,
        )
        deps = ChatDeps(principal=principal, services=services)
        overview = await services.issue_context()

        earlier, request_msg = await _history_for(
            app_db, threads, {"thread_id": UUID(str(request["thread_id"])), "id": request_id}
        )
        if request_msg.get("deleted_at") is not None:
            await threads.update_message(reply_id, status="cancelled")
            return {"status": "cancelled"}
        prompt = f"{request_msg.get('author_name') or 'Someone'}: {request_msg['body_md']}"

        text_parts: list[str] = []

        def on_text(delta: str) -> None:
            text_parts.append(delta)

        turn = asyncio.create_task(
            run_turn(
                agent_factory(),
                deps,
                prompt,
                build_history(earlier),
                on_text,
                instructions=build_instructions(overview),
            )
        )
        flushed = 0
        try:
            while not turn.done():
                await asyncio.wait({turn}, timeout=FLUSH_SECONDS)
                activity.heartbeat()
                text = "".join(text_parts)
                if len(text) != flushed:
                    await threads.update_message(reply_id, body_md=text)
                    flushed = len(text)
            result = turn.result()
        except asyncio.CancelledError:
            turn.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await turn
            await threads.update_message(
                reply_id,
                body_md="".join(text_parts),
                payload={"tool_calls": [c.to_payload() for c in deps.tool_calls]},
                status="cancelled",
            )
            raise

        await threads.update_message(
            reply_id,
            body_md=result.text,
            payload={
                "tool_calls": [c.to_payload() for c in result.tool_calls],
                "proposals": result.proposals,
                "usage": result.usage.to_payload(),
            },
            status="complete",
        )
        return {"status": "complete", "reply_id": str(reply_id)}

    return run_agent_turn


def make_mark_turn_failed_activity(app_db: AppDatabase) -> Any:
    """Return the mark_turn_failed activity with its database bound."""

    @activity.defn(name="mark_turn_failed")
    async def mark_turn_failed(request: dict[str, Any]) -> None:
        """Mark the reply to a request as failed after its last attempt."""
        threads = IssueThreadRepository(app_db)
        reply = await threads.get_reply_for_request(UUID(str(request["message_id"])))
        if reply is None or reply["status"] in ("complete", "cancelled"):
            return
        error = str(request.get("error") or "The agent could not answer")
        await threads.update_message(
            reply["id"],
            payload={**reply["payload"], "error": error},
            status="error",
        )

    return mark_turn_failed
