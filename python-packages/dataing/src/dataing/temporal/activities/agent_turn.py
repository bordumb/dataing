"""Activities that run one issue chat agent turn (docs/specs/0001_issue_chat.md §7.4).

run_agent_turn answers one request message:

1. It uses the reply the API created when the question was asked (status
   ``queued``), or creates one. A retried attempt reuses the same reply, so a
   crashed worker never leaves two answers.
2. It streams the answer into the reply, flushing new text every FLUSH_SECONDS,
   and heartbeats so a cancelled turn stops promptly.
3. It ends the reply as ``complete`` with the tool calls, steer proposals and
   token usage in its payload, or ``cancelled`` (partial text kept).

run_brief_draft fills a ``brief`` message (created by the API when someone asked
for a draft) with an InvestigationBrief drafted from the thread. A draft asked for
in a scratch chat reads the shared thread first (messages numbered #n), then the
scratch chat (numbered #sn), and may cite query results from both.

mark_turn_failed marks the reply (or the brief) ``error`` once every attempt has
failed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from uuid import UUID

from pydantic_ai import Agent
from temporalio import activity

from dataing.adapters.datasource.gateway import UserPrincipal
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.agents.chat import (
    ChatDeps,
    build_history,
    build_instructions,
    draft_brief,
    run_turn,
)
from dataing.core.agent_query import AgentQueryService
from dataing.core.investigation.brief import BriefDraft, brief_from_draft, brief_to_markdown
from dataing.core.issue_chat import (
    InvestigationStatusReader,
    ThreadChatServices,
    resolve_chat_datasource,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

FLUSH_SECONDS = 0.25
HEARTBEAT_SECONDS = 5.0
HISTORY_LIMIT = 200

ChatAgentFactory = Callable[[], Agent[ChatDeps, str]]
BriefAgentFactory = Callable[[], Agent[None, BriefDraft]]


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
    investigation_status: InvestigationStatusReader | None = None,
) -> Any:
    """Return the run_agent_turn activity with its dependencies bound.

    Args:
        app_db: Application database.
        agent_factory: Builds the chat agent (a fresh one per turn).
        query_service: Runs queries as the asker; built from app_db if omitted.
        investigation_status: Reads a running investigation's live hypotheses.
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
            investigation_status=investigation_status,
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
        message_id = UUID(str(request["message_id"]))
        if request.get("kind") == "draft_brief":
            reply = await threads.get_message(message_id)
        else:
            reply = await threads.get_reply_for_request(message_id)
        if reply is None or reply["status"] in ("complete", "cancelled"):
            return
        error = str(request.get("error") or "The agent could not answer")
        await threads.update_message(
            reply["id"],
            payload={**reply["payload"], "error": error},
            status="error",
        )

    return mark_turn_failed


async def _with_heartbeats(work: Awaitable[T]) -> T:
    """Await work while heartbeating, so long model calls don't time out."""
    task = asyncio.ensure_future(work)
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=HEARTBEAT_SECONDS)
            activity.heartbeat()
    except asyncio.CancelledError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        raise
    return task.result()


async def _labelled_messages(
    db: AppDatabase, threads: IssueThreadRepository, thread_id: UUID, before_seq: int
) -> list[dict[str, Any]]:
    """Return a thread's finished messages before a seq, with author names."""
    messages = [
        m
        for m in await threads.list_messages(thread_id, after_seq=0, limit=10_000)
        if m["seq"] < before_seq and m["status"] in ("complete", "cancelled")
    ][-HISTORY_LIMIT:]
    names = await _author_names(
        db, {m["author_user_id"] for m in messages if m.get("author_user_id")}
    )
    for message in messages:
        message["author_name"] = names.get(message.get("author_user_id") or UUID(int=0))
    return messages


async def _thread_query_results(db: AppDatabase, thread_id: UUID) -> set[UUID]:
    rows = await db.fetch_all(
        """
        SELECT r.id FROM agent_query_results r
        JOIN issue_thread_messages m ON m.id = r.message_id
        WHERE m.thread_id = $1
        """,
        thread_id,
    )
    return {row["id"] for row in rows}


@dataclass
class BriefSources:
    """What a brief draft reads, and how its citations resolve."""

    history: list[dict[str, Any]]
    seq_to_message: dict[int, UUID]
    known_query_results: set[UUID]
    scratch_seq_to_message: dict[int, UUID] | None = None


async def _brief_sources(
    db: AppDatabase,
    threads: IssueThreadRepository,
    issue_id: UUID,
    thread_id: UUID,
    before_seq: int,
) -> BriefSources:
    """Collect the messages and query results a brief draft may cite.

    For the shared thread that is its own messages before the brief. For a
    scratch chat it is the whole shared thread, then a marker, then the scratch
    messages before the brief relabelled ``s<seq>``, so no citation is ambiguous.
    """
    messages = await _labelled_messages(db, threads, thread_id, before_seq)
    known = await _thread_query_results(db, thread_id)
    thread = await threads.get_thread(thread_id)
    if thread is None or thread["kind"] != "scratch":
        return BriefSources(messages, {m["seq"]: m["id"] for m in messages}, known)

    shared = await threads.ensure_shared_thread(issue_id)
    shared_messages = await _labelled_messages(db, threads, shared["id"], sys.maxsize)
    owner = (await _author_names(db, {thread["owner_user_id"]})).get(thread["owner_user_id"])
    marker = {
        "author_kind": "system",
        "seq": None,
        "body_md": (
            f"The shared thread ends here. What follows is {owner or 'the requester'}'s "
            "private scratch chat. Its messages are numbered #s1, #s2, ...; cite them "
            "with source_seq s1, s2, ..."
        ),
    }
    scratch = [{**m, "seq": f"s{m['seq']}"} for m in messages]
    return BriefSources(
        history=[*shared_messages, marker, *scratch],
        seq_to_message={m["seq"]: m["id"] for m in shared_messages},
        known_query_results=known | await _thread_query_results(db, shared["id"]),
        scratch_seq_to_message={m["seq"]: m["id"] for m in messages},
    )


def make_run_brief_draft_activity(
    app_db: AppDatabase,
    agent_factory: BriefAgentFactory,
    query_service: AgentQueryService | None = None,
) -> Any:
    """Return the run_brief_draft activity with its dependencies bound.

    Args:
        app_db: Application database.
        agent_factory: Builds the brief-drafting agent.
        query_service: Only used to describe the issue; built from app_db if omitted.
    """
    queries = query_service or AgentQueryService(app_db)

    @activity.defn(name="run_brief_draft")
    async def run_brief_draft(request: dict[str, Any]) -> dict[str, Any]:
        """Draft an investigation brief into the requested brief message."""
        threads = IssueThreadRepository(app_db)
        brief_id = UUID(str(request["message_id"]))
        tenant_id = UUID(str(request["tenant_id"]))
        issue_id = UUID(str(request["issue_id"]))
        thread_id = UUID(str(request["thread_id"]))

        message = await threads.get_message(brief_id)
        if message is None or message["status"] == "cancelled":
            return {"status": "cancelled"}
        await threads.update_message(brief_id, status="streaming")
        activity.heartbeat()

        issue_row = await app_db.fetch_one(
            "SELECT context FROM issues WHERE id = $1 AND tenant_id = $2", issue_id, tenant_id
        )
        context_raw = issue_row["context"] if issue_row else "{}"
        issue_context = json.loads(context_raw) if isinstance(context_raw, str) else context_raw
        datasource_id = await resolve_chat_datasource(app_db, tenant_id, issue_context or {})
        services = ThreadChatServices(
            app_db,
            queries,
            tenant_id=tenant_id,
            issue_id=issue_id,
            reply_message_id=brief_id,
            principal=None,
        )
        overview = await services.issue_context()
        sources = await _brief_sources(app_db, threads, issue_id, thread_id, message["seq"])

        draft, usage = await _with_heartbeats(
            draft_brief(
                agent_factory(),
                build_history(sources.history, max_messages=len(sources.history)),
                instructions=build_instructions(overview),
            )
        )
        brief = brief_from_draft(
            draft,
            seq_to_message=sources.seq_to_message,
            scratch_seq_to_message=sources.scratch_seq_to_message,
            known_query_results=sources.known_query_results,
            datasource_id=datasource_id,
        )
        await threads.update_message(
            brief_id,
            body_md=brief_to_markdown(brief),
            payload={
                "brief": brief.model_dump(mode="json", by_alias=True),
                "usage": usage.to_payload(),
            },
            status="complete",
        )
        return {"status": "complete", "brief_id": str(brief_id)}

    return run_brief_draft
