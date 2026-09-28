"""Issue thread API: the shared thread, scratch threads and their messages.

See docs/specs/0001_issue_chat.md §7.1. Access rules that depend on the thread
or the message (kind, owner, author, asking the agent) are enforced here, not by
route dependencies:

- Anyone in the tenant reads the shared thread and may comment in it.
- Asking the agent runs queries, so it needs the write scope.
- Scratch threads answer 404 to everyone but their owner, admins included.
- Only a message's author edits it; its author or an admin deletes it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.entrypoints.api.routes.issues import _record_issue_event, _verify_issue_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues", tags=["issue-threads"])

MAX_RUNNING_TURNS_PER_PERSON = 3


class ThreadAgent(Protocol):
    """Hands agent requests to the thread's workflow."""

    async def enqueue_thread_request(self, request: dict[str, Any]) -> None:
        """Queue a request, starting the thread's workflow if needed."""
        ...

    async def cancel_thread_request(self, thread_id: str, message_id: str) -> None:
        """Drop a queued request or cancel the running turn."""
        ...


def get_thread_agent(request: Request) -> ThreadAgent | None:
    """Return the Temporal client that runs agent turns, if one is connected."""
    agent: ThreadAgent | None = getattr(request.app.state, "temporal_client", None)
    return agent


def get_issue_thread_repository(
    db: Annotated[AppDatabase, Depends(get_app_db)],
) -> IssueThreadRepository:
    """Return the thread repository for the request."""
    return IssueThreadRepository(db)


AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
WriteScopeDep = Annotated[ApiKeyContext, Depends(require_scope("write"))]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
ThreadsDep = Annotated[IssueThreadRepository, Depends(get_issue_thread_repository)]
ThreadAgentDep = Annotated["ThreadAgent | None", Depends(get_thread_agent)]


# ============================================================================
# Models
# ============================================================================


class ThreadResponse(BaseModel):
    """A shared or scratch thread."""

    id: UUID
    issue_id: UUID
    kind: Literal["shared", "scratch"]
    owner_user_id: UUID | None
    title: str | None
    created_at: datetime


class ThreadListResponse(BaseModel):
    """The shared thread followed by the caller's scratch threads."""

    items: list[ThreadResponse]


class ScratchThreadCreate(BaseModel):
    """Request body for creating a scratch thread."""

    title: str | None = Field(default=None, max_length=200)


class MessageResponse(BaseModel):
    """One entry in a thread's timeline."""

    id: UUID
    thread_id: UUID
    seq: int
    rev: int
    author_kind: str
    author_user_id: UUID | None
    requested_by_user_id: UUID | None
    request_message_id: UUID | None
    kind: str
    body_md: str
    payload: dict[str, Any]
    status: str
    asks_agent: bool
    reply_to_id: UUID | None
    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None


class MessageListResponse(BaseModel):
    """A page of messages ordered by seq."""

    items: list[MessageResponse]


class QueryResultResponse(BaseModel):
    """What the agent saw when it ran a query."""

    id: UUID
    message_id: UUID
    tool_call_id: str
    sql: str
    dialect: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    error: str | None
    created_at: datetime


class MessageCreate(BaseModel):
    """Request body for posting a message."""

    body_md: str = Field(..., min_length=1, max_length=20_000)
    ask_agent: bool = False
    reply_to_id: UUID | None = None


class MessageUpdate(BaseModel):
    """Request body for editing a comment."""

    body_md: str = Field(..., min_length=1, max_length=20_000)


def _thread_response(row: dict[str, Any]) -> ThreadResponse:
    return ThreadResponse(
        id=row["id"],
        issue_id=row["issue_id"],
        kind=row["kind"],
        owner_user_id=row["owner_user_id"],
        title=row["title"],
        created_at=row["created_at"],
    )


def message_response(row: dict[str, Any]) -> MessageResponse:
    """Convert a message row to its API shape."""
    return MessageResponse(**{field: row.get(field) for field in MessageResponse.model_fields})


# ============================================================================
# Access helpers
# ============================================================================


def _require_user(auth: ApiKeyContext) -> UUID:
    if auth.user_id is None:
        raise HTTPException(status_code=403, detail="User identity required")
    return auth.user_id


async def _thread_for_caller(
    threads: IssueThreadRepository,
    issue_id: UUID,
    thread_id: UUID,
    auth: ApiKeyContext,
) -> dict[str, Any]:
    """Return the thread if the caller may see it, else raise 404."""
    thread = await threads.get_thread(thread_id)
    visible = (
        thread is not None
        and thread["issue_id"] == issue_id
        and thread["tenant_id"] == auth.tenant_id
        and (thread["kind"] == "shared" or auth.is_user(thread["owner_user_id"]))
    )
    if not visible or thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


async def _message_in_thread(
    threads: IssueThreadRepository, thread_id: UUID, message_id: UUID
) -> dict[str, Any]:
    message = await threads.get_message(message_id)
    if message is None or message["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


# ============================================================================
# Threads
# ============================================================================


@router.get("/{issue_id}/threads", response_model=ThreadListResponse)
async def list_threads(
    issue_id: UUID, auth: AuthDep, db: AppDbDep, threads: ThreadsDep
) -> ThreadListResponse:
    """List the shared thread and the caller's own scratch threads."""
    await _verify_issue_access(db, issue_id, auth.tenant_id)
    rows = await threads.list_threads(issue_id, auth.user_id)
    return ThreadListResponse(items=[_thread_response(r) for r in rows])


@router.post("/{issue_id}/threads", response_model=ThreadResponse, status_code=201)
async def create_scratch_thread(
    issue_id: UUID,
    body: ScratchThreadCreate,
    auth: WriteScopeDep,
    db: AppDbDep,
    threads: ThreadsDep,
) -> ThreadResponse:
    """Create a private scratch thread on the issue."""
    await _verify_issue_access(db, issue_id, auth.tenant_id)
    owner = _require_user(auth)
    row = await threads.create_scratch_thread(auth.tenant_id, issue_id, owner, body.title)
    return _thread_response(row)


@router.delete("/{issue_id}/threads/{thread_id}", status_code=204, response_class=Response)
async def delete_scratch_thread(
    issue_id: UUID, thread_id: UUID, auth: AuthDep, threads: ThreadsDep
) -> Response:
    """Delete the caller's own scratch thread."""
    thread = await _thread_for_caller(threads, issue_id, thread_id, auth)
    if thread["kind"] == "shared":
        raise HTTPException(status_code=400, detail="The shared thread can't be deleted")
    await threads.delete_thread(thread_id)
    return Response(status_code=204)


# ============================================================================
# Messages
# ============================================================================


@router.get("/{issue_id}/threads/{thread_id}/messages", response_model=MessageListResponse)
async def list_messages(
    issue_id: UUID,
    thread_id: UUID,
    auth: AuthDep,
    threads: ThreadsDep,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> MessageListResponse:
    """List a thread's messages after a seq, oldest first."""
    await _thread_for_caller(threads, issue_id, thread_id, auth)
    rows = await threads.list_messages(thread_id, after_seq=after_seq, limit=limit)
    return MessageListResponse(items=[message_response(r) for r in rows])


@router.post(
    "/{issue_id}/threads/{thread_id}/messages",
    response_model=MessageResponse,
    status_code=201,
)
async def post_message(
    issue_id: UUID,
    thread_id: UUID,
    body: MessageCreate,
    auth: AuthDep,
    db: AppDbDep,
    threads: ThreadsDep,
    agent: ThreadAgentDep,
) -> MessageResponse:
    """Post a comment, optionally asking the agent to answer it.

    Asking the agent needs the write scope, and a person may have at most three
    agent turns queued or streaming at once.
    """
    thread = await _thread_for_caller(threads, issue_id, thread_id, auth)
    user_id = _require_user(auth)
    if thread["kind"] == "scratch" and not auth.has_scope("write"):
        raise HTTPException(status_code=403, detail="Scope 'write' required")
    if body.ask_agent:
        if not auth.has_scope("write"):
            raise HTTPException(status_code=403, detail="Scope 'write' required to ask the agent")
        if await threads.count_running_turns(user_id) >= MAX_RUNNING_TURNS_PER_PERSON:
            raise HTTPException(
                status_code=429,
                detail="You already have three agent answers in progress",
            )

    row = await threads.append_message(
        thread_id,
        author_kind="user",
        kind="comment",
        author_user_id=user_id,
        body_md=body.body_md,
        asks_agent=body.ask_agent,
        reply_to_id=body.reply_to_id,
    )
    if thread["kind"] == "shared":
        await _record_issue_event(
            db, issue_id, "comment_added", user_id, {"message_id": str(row["id"])}
        )
        await db.execute("UPDATE issues SET updated_at = NOW() WHERE id = $1", issue_id)
    if body.ask_agent:
        await _queue_answer(threads, agent, thread, row, user_id)
    return message_response(row)


async def _queue_answer(
    threads: IssueThreadRepository,
    agent: ThreadAgent | None,
    thread: dict[str, Any],
    question: dict[str, Any],
    user_id: UUID,
) -> None:
    """Create the queued reply and hand the question to the thread's workflow.

    The reply exists before the workflow runs, so the thread shows "queued" at
    once and the per-person turn limit counts it. If the workflow can't be
    reached, the reply is marked failed rather than left queued forever.
    """
    reply = await threads.append_message(
        thread["id"],
        author_kind="agent",
        kind="agent_reply",
        requested_by_user_id=user_id,
        request_message_id=question["id"],
        reply_to_id=question["id"],
        status="queued",
    )
    request = {
        "message_id": str(question["id"]),
        "kind": "answer",
        "thread_id": str(thread["id"]),
        "tenant_id": str(thread["tenant_id"]),
        "issue_id": str(thread["issue_id"]),
        "requested_by": str(user_id),
    }
    try:
        if agent is None:
            raise RuntimeError("no workflow client connected")
        await agent.enqueue_thread_request(request)
    except Exception as e:
        logger.error(f"Could not queue agent request {question['id']}: {e}")
        await threads.update_message(
            reply["id"],
            status="error",
            payload={"error": "The agent is unavailable right now. Try again shortly."},
        )


@router.patch(
    "/{issue_id}/threads/{thread_id}/messages/{message_id}", response_model=MessageResponse
)
async def edit_message(
    issue_id: UUID,
    thread_id: UUID,
    message_id: UUID,
    body: MessageUpdate,
    auth: AuthDep,
    threads: ThreadsDep,
) -> MessageResponse:
    """Edit the caller's own comment. Editing never re-runs the agent."""
    await _thread_for_caller(threads, issue_id, thread_id, auth)
    message = await _message_in_thread(threads, thread_id, message_id)
    if message["kind"] != "comment" or not auth.is_user(message["author_user_id"]):
        raise HTTPException(status_code=403, detail="Only the author can edit this message")
    if message["deleted_at"] is not None:
        raise HTTPException(status_code=409, detail="Message was deleted")
    row = await threads.update_message(message_id, body_md=body.body_md, edited=True)
    if row is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message_response(row)


@router.delete(
    "/{issue_id}/threads/{thread_id}/messages/{message_id}",
    status_code=204,
    response_class=Response,
)
async def delete_message(
    issue_id: UUID,
    thread_id: UUID,
    message_id: UUID,
    auth: AuthDep,
    threads: ThreadsDep,
) -> Response:
    """Delete a comment: its author or an admin."""
    await _thread_for_caller(threads, issue_id, thread_id, auth)
    message = await _message_in_thread(threads, thread_id, message_id)
    if message["kind"] != "comment" or not (
        auth.is_user(message["author_user_id"]) or auth.has_scope("admin")
    ):
        raise HTTPException(status_code=403, detail="Only the author or an admin can delete this")
    await threads.soft_delete_message(message_id)
    return Response(status_code=204)


@router.post(
    "/{issue_id}/threads/{thread_id}/messages/{message_id}/cancel",
    response_model=MessageResponse,
)
async def cancel_answer(
    issue_id: UUID,
    thread_id: UUID,
    message_id: UUID,
    auth: AuthDep,
    threads: ThreadsDep,
    agent: ThreadAgentDep,
) -> MessageResponse:
    """Cancel a queued or streaming agent answer: the person who asked, or an admin."""
    await _thread_for_caller(threads, issue_id, thread_id, auth)
    reply = await _message_in_thread(threads, thread_id, message_id)
    if reply["kind"] != "agent_reply" or reply["request_message_id"] is None:
        raise HTTPException(status_code=400, detail="Only agent answers can be cancelled")
    if not (auth.is_user(reply["requested_by_user_id"]) or auth.has_scope("admin")):
        raise HTTPException(status_code=403, detail="Only the person who asked can cancel this")
    if reply["status"] not in ("queued", "streaming"):
        raise HTTPException(status_code=409, detail="This answer has already finished")
    if reply["status"] == "queued":
        updated = await threads.update_message(message_id, status="cancelled")
        reply = updated or reply
    if agent is not None:
        await agent.cancel_thread_request(str(thread_id), str(reply["request_message_id"]))
    return message_response(reply)


@router.get(
    "/{issue_id}/threads/{thread_id}/query-results/{result_id}",
    response_model=QueryResultResponse,
)
async def get_query_result(
    issue_id: UUID,
    thread_id: UUID,
    result_id: UUID,
    auth: AuthDep,
    threads: ThreadsDep,
) -> QueryResultResponse:
    """Return a query snapshot: the SQL the agent ran and the rows it saw."""
    await _thread_for_caller(threads, issue_id, thread_id, auth)
    snapshot = await threads.get_query_result(result_id)
    if snapshot is None or snapshot["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail="Query result not found")
    return QueryResultResponse(
        **{field: snapshot.get(field) for field in QueryResultResponse.model_fields}
    )


# ============================================================================
# Streaming
# ============================================================================


class ThreadChanges(Protocol):
    """What the stream needs from the repository."""

    def changes_since(
        self, thread_id: UUID, *, after_rev: int, overlap_seconds: float = ...
    ) -> Awaitable[list[dict[str, Any]]]:
        """Return messages written after a rev plus recently touched ones."""
        ...


async def thread_message_stream(
    threads: ThreadChanges,
    thread_id: UUID,
    *,
    after_rev: int,
    is_disconnected: Callable[[], Awaitable[bool]],
    poll_interval: float = 0.25,
    overlap_seconds: float = 5.0,
    heartbeat_every: int = 120,
    max_polls: int = 7200,
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE events for every new or changed message in a thread.

    Each poll reads messages with a rev above the cursor plus any touched within
    the overlap window, which catches rows that committed after a newer rev was
    streamed. Rows are sent when their (id, rev) is new to this connection, so
    nothing repeats within a connection; after a reconnect, rows in the overlap
    window may be sent again and clients de-duplicate by (id, rev). The event id
    is the rev, so a reconnect resumes with Last-Event-ID.
    """
    cursor = after_rev
    sent: dict[UUID, int] = {}
    for poll in range(1, max_polls + 1):
        if await is_disconnected():
            return
        rows = await threads.changes_since(
            thread_id, after_rev=cursor, overlap_seconds=overlap_seconds
        )
        for row in rows:
            if sent.get(row["id"], -1) >= row["rev"]:
                continue
            sent[row["id"]] = row["rev"]
            cursor = max(cursor, row["rev"])
            yield {
                "event": "message",
                "id": str(row["rev"]),
                "data": message_response(row).model_dump_json(),
            }
        if poll % heartbeat_every == 0:
            yield {"event": "heartbeat", "data": to_json_string({"rev": cursor})}
        await asyncio.sleep(poll_interval)
    yield {"event": "timeout", "data": to_json_string({"message": "Reconnect to continue"})}


@router.get("/{issue_id}/threads/{thread_id}/stream")
async def stream_thread(
    issue_id: UUID,
    thread_id: UUID,
    request: Request,
    auth: AuthDep,
    threads: ThreadsDep,
    after: int | None = Query(default=None, ge=0),
) -> EventSourceResponse:
    """Stream new and changed messages over Server-Sent Events.

    Resume with ?after=<rev> or the Last-Event-ID header.
    """
    await _thread_for_caller(threads, issue_id, thread_id, auth)
    last_event_id = request.headers.get("last-event-id")
    after_rev = after if after is not None else 0
    if last_event_id and last_event_id.isdigit():
        after_rev = max(after_rev, int(last_event_id))
    return EventSourceResponse(
        thread_message_stream(
            threads,
            thread_id,
            after_rev=after_rev,
            is_disconnected=request.is_disconnected,
        ),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
