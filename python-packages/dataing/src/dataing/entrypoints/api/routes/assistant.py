"""API routes for Dataing Assistant.

Provides endpoints for chat sessions, messages, and real-time streaming.
Uses Temporal workflows for durable execution and observability.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from temporalio.service import RPCError

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string
from dataing.entrypoints.api.deps import get_app_db, settings
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.temporal.client import TemporalAgentClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Type aliases for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]

# SSE configuration
HEARTBEAT_INTERVAL_SECONDS = 15
MAX_STREAM_DURATION_SECONDS = 300  # 5 minutes

# In-memory message queue for active sessions (Redis in production)
_active_streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}


# =============================================================================
# Pydantic Models
# =============================================================================


class CreateSessionRequest(BaseModel):
    """Request to create a new assistant session."""

    parent_investigation_id: UUID | None = Field(
        None, description="Optional parent investigation to link to"
    )
    title: str | None = Field(None, description="Optional session title")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSessionResponse(BaseModel):
    """Response from creating a session."""

    session_id: UUID
    investigation_id: UUID
    created_at: datetime


class SessionSummary(BaseModel):
    """Summary of a session for listing."""

    id: UUID
    title: str | None
    created_at: datetime
    last_activity: datetime
    message_count: int
    token_count: int


class ListSessionsResponse(BaseModel):
    """Response from listing sessions."""

    sessions: list[SessionSummary]


class MessageRole(str, Enum):
    """Message role types."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageResponse(BaseModel):
    """A message in a session."""

    id: UUID
    role: MessageRole
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    created_at: datetime
    token_count: int | None = None


class SessionDetailResponse(BaseModel):
    """Full session details with messages."""

    id: UUID
    investigation_id: UUID
    title: str | None
    created_at: datetime
    last_activity: datetime
    token_count: int
    messages: list[MessageResponse]
    parent_investigation_id: UUID | None = None


class PageContextError(BaseModel):
    """A frontend error captured by the error bus."""

    type: str = Field(..., description="Error type: api, react, or console")
    message: str
    status: int | None = None
    url: str | None = None
    timestamp: int
    stack_preview: str | None = None


class PageContext(BaseModel):
    """Context about the page the user is currently viewing."""

    route: str
    route_pattern: str
    route_params: dict[str, str] = Field(default_factory=dict)
    page_type: str
    page_title: str
    page_data: dict[str, Any] = Field(default_factory=dict)
    errors: list[PageContextError] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    """Request to send a message."""

    content: str = Field(..., min_length=1, max_length=32000)
    page_context: PageContext | None = None


class SendMessageResponse(BaseModel):
    """Response from sending a message."""

    message_id: UUID
    status: str = "processing"


class SSEEventType(str, Enum):
    """SSE event types for streaming."""

    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    COMPLETE = "complete"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class ExportFormat(str, Enum):
    """Export format options."""

    JSON = "json"
    MARKDOWN = "markdown"


# =============================================================================
# Temporal Client Cache
# =============================================================================

# Cache the Temporal client connection (lazy initialization)
_temporal_client: TemporalAgentClient | None = None


async def get_temporal_client() -> TemporalAgentClient:
    """Get or create the Temporal agent client.

    Returns:
        Connected TemporalAgentClient.
    """
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await TemporalAgentClient.connect(
            host=settings.TEMPORAL_HOST,
            namespace=settings.TEMPORAL_NAMESPACE,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
        logger.info(
            f"Temporal agent client connected: host={settings.TEMPORAL_HOST}, "
            f"namespace={settings.TEMPORAL_NAMESPACE}"
        )
    return _temporal_client


# =============================================================================
# Helper Functions
# =============================================================================


async def create_investigation_for_session(
    db: AppDatabase,
    tenant_id: UUID,
    user_id: UUID | None,
) -> UUID:
    """Create an investigation record for a new assistant session.

    Args:
        db: Application database.
        tenant_id: Tenant ID.
        user_id: User ID (may be None for API key auth).

    Returns:
        The created investigation UUID.
    """
    # Create investigation with empty alert (assistant sessions are special)
    row = await db.fetch_one(
        """
        INSERT INTO investigations (tenant_id, alert, created_by)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        tenant_id,
        to_json_string({"type": "assistant_session", "description": "Assistant chat"}),
        user_id,
    )
    if not row:
        raise RuntimeError("Failed to create investigation")
    result: UUID = row["id"]
    return result


# =============================================================================
# Session Endpoints
# =============================================================================


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    auth: AuthDep,
    db: AppDbDep,
) -> CreateSessionResponse:
    """Create a new assistant session.

    Each session is linked to an investigation for tracking and context.
    """
    # Create the underlying investigation
    investigation_id = await create_investigation_for_session(db, auth.tenant_id, auth.user_id)

    # Create the session
    row = await db.fetch_one(
        """
        INSERT INTO assistant_sessions
            (investigation_id, tenant_id, user_id, parent_investigation_id, title, metadata)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, created_at
        """,
        investigation_id,
        auth.tenant_id,
        auth.user_id or UUID("00000000-0000-0000-0000-000000000000"),
        request.parent_investigation_id,
        request.title,
        to_json_string(request.metadata),
    )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create session")

    return CreateSessionResponse(
        session_id=row["id"],
        investigation_id=investigation_id,
        created_at=row["created_at"],
    )


@router.get("/sessions", response_model=ListSessionsResponse)
async def list_sessions(
    auth: AuthDep,
    db: AppDbDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ListSessionsResponse:
    """List the user's assistant sessions."""
    rows = await db.fetch_all(
        """
        SELECT
            s.id,
            s.title,
            s.created_at,
            s.last_activity,
            s.token_count,
            COUNT(m.id) as message_count
        FROM assistant_sessions s
        LEFT JOIN assistant_messages m ON m.session_id = s.id
        WHERE s.tenant_id = $1
          AND ($2::uuid IS NULL OR s.user_id = $2)
        GROUP BY s.id
        ORDER BY s.last_activity DESC
        LIMIT $3 OFFSET $4
        """,
        auth.tenant_id,
        auth.user_id,
        limit,
        offset,
    )

    sessions = [
        SessionSummary(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            last_activity=row["last_activity"],
            message_count=row["message_count"],
            token_count=row["token_count"] or 0,
        )
        for row in rows
    ]

    return ListSessionsResponse(sessions=sessions)


@router.get("/investigations/{investigation_id}/sessions", response_model=ListSessionsResponse)
async def list_sessions_for_investigation(
    investigation_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ListSessionsResponse:
    """List assistant sessions linked to an investigation.

    Returns sessions where the investigation is the parent.
    """
    rows = await db.fetch_all(
        """
        SELECT
            s.id,
            s.title,
            s.created_at,
            s.last_activity,
            s.token_count,
            COUNT(m.id) as message_count
        FROM assistant_sessions s
        LEFT JOIN assistant_messages m ON m.session_id = s.id
        WHERE s.tenant_id = $1
          AND s.parent_investigation_id = $2
        GROUP BY s.id
        ORDER BY s.last_activity DESC
        LIMIT $3 OFFSET $4
        """,
        auth.tenant_id,
        investigation_id,
        limit,
        offset,
    )

    sessions = [
        SessionSummary(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            last_activity=row["last_activity"],
            message_count=row["message_count"],
            token_count=row["token_count"] or 0,
        )
        for row in rows
    ]

    return ListSessionsResponse(sessions=sessions)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> SessionDetailResponse:
    """Get full session details with messages."""
    # Get session
    session = await db.fetch_one(
        """
        SELECT id, investigation_id, title, created_at, last_activity,
               token_count, parent_investigation_id
        FROM assistant_sessions
        WHERE id = $1 AND tenant_id = $2
        """,
        session_id,
        auth.tenant_id,
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages
    message_rows = await db.fetch_all(
        """
        SELECT id, role, content, tool_calls, created_at, token_count
        FROM assistant_messages
        WHERE session_id = $1
        ORDER BY created_at ASC
        """,
        session_id,
    )

    messages = [
        MessageResponse(
            id=row["id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            tool_calls=row["tool_calls"],
            created_at=row["created_at"],
            token_count=row["token_count"],
        )
        for row in message_rows
    ]

    return SessionDetailResponse(
        id=session["id"],
        investigation_id=session["investigation_id"],
        title=session["title"],
        created_at=session["created_at"],
        last_activity=session["last_activity"],
        token_count=session["token_count"] or 0,
        messages=messages,
        parent_investigation_id=session["parent_investigation_id"],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
) -> dict[str, str]:
    """Delete an assistant session."""
    result = await db.execute(
        """
        DELETE FROM assistant_sessions
        WHERE id = $1 AND tenant_id = $2
        """,
        session_id,
        auth.tenant_id,
    )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Session not found")

    return {"status": "deleted"}


# =============================================================================
# Message Endpoints
# =============================================================================


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(
    session_id: UUID,
    request_body: SendMessageRequest,
    auth: AuthDep,
    db: AppDbDep,
) -> SendMessageResponse:
    """Send a message to the assistant.

    The response will be streamed via the /stream endpoint.
    """
    # Verify session exists and belongs to tenant
    session = await db.fetch_one(
        """
        SELECT id, investigation_id FROM assistant_sessions
        WHERE id = $1 AND tenant_id = $2
        """,
        session_id,
        auth.tenant_id,
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Store user message
    user_msg = await db.fetch_one(
        """
        INSERT INTO assistant_messages (session_id, role, content)
        VALUES ($1, 'user', $2)
        RETURNING id
        """,
        session_id,
        request_body.content,
    )

    if not user_msg:
        raise HTTPException(status_code=500, detail="Failed to store message")

    # Initialize the stream queue for this session
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _active_streams[str(session_id)] = queue

    # Start background task to process the message
    asyncio.create_task(
        _process_message(
            session_id=session_id,
            message_content=request_body.content,
            page_context=request_body.page_context,
            auth=auth,
            db=db,
            queue=queue,
        )
    )

    return SendMessageResponse(
        message_id=user_msg["id"],
        status="processing",
    )


async def _load_parent_investigation_context(
    db: AppDatabase,
    session_id: UUID,
    tenant_id: UUID,
) -> dict[str, Any] | None:
    """Load parent investigation context for a session.

    Args:
        db: Application database.
        session_id: The assistant session ID.
        tenant_id: Tenant ID for security check.

    Returns:
        Parent investigation context dict or None if no parent.
    """
    # Get session with parent_investigation_id
    session = await db.fetch_one(
        """
        SELECT parent_investigation_id FROM assistant_sessions
        WHERE id = $1 AND tenant_id = $2
        """,
        session_id,
        tenant_id,
    )

    if not session or not session.get("parent_investigation_id"):
        return None

    parent_id = session["parent_investigation_id"]

    # Load parent investigation
    investigation = await db.fetch_one(
        """
        SELECT id, dataset_id, metric_name, status, severity,
               expected_value, actual_value, deviation_pct, anomaly_date,
               finding, events, metadata, created_at, completed_at
        FROM investigations
        WHERE id = $1 AND tenant_id = $2
        """,
        parent_id,
        tenant_id,
    )

    if not investigation:
        return None

    return {
        "parent_investigation": {
            "id": str(investigation["id"]),
            "dataset_id": investigation["dataset_id"],
            "metric_name": investigation["metric_name"],
            "status": investigation["status"],
            "severity": investigation.get("severity"),
            "expected_value": investigation.get("expected_value"),
            "actual_value": investigation.get("actual_value"),
            "deviation_pct": investigation.get("deviation_pct"),
            "anomaly_date": investigation.get("anomaly_date"),
            "finding": investigation.get("finding"),
            "events": investigation.get("events"),
            "metadata": investigation.get("metadata"),
        }
    }


async def _process_message(
    session_id: UUID,
    message_content: str,
    page_context: PageContext | None,
    auth: ApiKeyContext,
    db: AppDatabase,
    queue: asyncio.Queue[dict[str, Any]],
) -> None:
    """Process a message via Temporal workflow and send events to the queue.

    This function:
    1. Gets or creates a Temporal workflow for the session
    2. Sends the message via signal
    3. Polls for the response
    4. Streams the response via SSE

    Args:
        session_id: The session ID.
        message_content: The user's message.
        page_context: Optional context about the page the user is viewing.
        auth: Authentication context.
        db: Application database.
        queue: Queue for SSE events.
    """
    try:
        # Get Temporal client
        temporal_client = await get_temporal_client()

        # Get conversation history for context
        history_rows = await db.fetch_all(
            """
            SELECT role, content FROM assistant_messages
            WHERE session_id = $1
            ORDER BY created_at ASC
            LIMIT 50
            """,
            session_id,
        )

        # Build context with history
        history = [{"role": r["role"], "content": r["content"]} for r in history_rows]
        context: dict[str, Any] = {"history": history} if history else {}

        # Load parent investigation context if available
        parent_context = await _load_parent_investigation_context(db, session_id, auth.tenant_id)
        if parent_context:
            context.update(parent_context)

        # Attach page context if provided
        if page_context:
            context["page_context"] = page_context.model_dump()

        logger.info(f"[ASSISTANT] Processing message via Temporal: {message_content[:100]}...")

        # Get or create workflow for this session
        session_str = str(session_id)
        workflow_exists = await temporal_client.workflow_exists(session_str)

        if workflow_exists:
            # Update context and send message to existing workflow
            logger.info(f"[ASSISTANT] Signaling existing workflow for session {session_str}")
            await temporal_client.update_context(session_str, context)
            await temporal_client.send_message(session_str, message_content)
        else:
            # Start new workflow with initial message
            logger.info(f"[ASSISTANT] Starting new workflow for session {session_str}")
            await temporal_client.start_session(
                agent_name="dataing-assistant",
                session_id=session_str,
                tenant_id=str(auth.tenant_id),
                context=context,
                initial_message=message_content,
            )

        # Poll for response with timeout
        response = await temporal_client.wait_for_response(
            session_id=session_str,
            timeout_seconds=300,  # 5 minutes
            poll_interval=0.5,
        )

        if response is None:
            raise TimeoutError("Agent did not respond within timeout")

        logger.info(f"[ASSISTANT] Response length: {len(response)}")

        # Send the full response as a single text event
        await queue.put(
            {
                "event": SSEEventType.TEXT.value,
                "data": to_json_string({"text": response}),
            }
        )

        # Store assistant response
        await db.execute(
            """
            INSERT INTO assistant_messages (session_id, role, content)
            VALUES ($1, 'assistant', $2)
            """,
            session_id,
            response,
        )

        # Send completion event
        await queue.put(
            {
                "event": SSEEventType.COMPLETE.value,
                "data": to_json_string({"status": "complete"}),
            }
        )

    except RPCError as e:
        logger.exception(f"Temporal RPC error for session {session_id}")
        await queue.put(
            {
                "event": SSEEventType.ERROR.value,
                "data": to_json_string({"error": f"Temporal error: {e}"}),
            }
        )

    except TimeoutError as e:
        logger.exception(f"Timeout processing message for session {session_id}")
        await queue.put(
            {
                "event": SSEEventType.ERROR.value,
                "data": to_json_string({"error": str(e)}),
            }
        )

    except Exception as e:
        logger.exception(f"Error processing message for session {session_id}")
        await queue.put(
            {
                "event": SSEEventType.ERROR.value,
                "data": to_json_string({"error": str(e)}),
            }
        )

    finally:
        # Clean up the stream
        if str(session_id) in _active_streams:
            del _active_streams[str(session_id)]


@router.get("/sessions/{session_id}/stream")
async def stream_response(
    request: Request,
    session_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    last_event_id: int | None = Query(None, description="Resume from event ID"),
) -> EventSourceResponse:
    """Stream assistant responses via Server-Sent Events.

    Connect to this endpoint after sending a message to receive real-time
    updates including text chunks, tool calls, and completion status.
    """
    # Verify session exists
    session = await db.fetch_one(
        """
        SELECT id FROM assistant_sessions
        WHERE id = $1 AND tenant_id = $2
        """,
        session_id,
        auth.tenant_id,
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        """Generate SSE events."""
        queue = _active_streams.get(str(session_id))
        event_id = 0
        last_heartbeat = datetime.now(UTC)

        try:
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from session {session_id}")
                    break

                # Check stream duration limit
                stream_duration = (datetime.now(UTC) - last_heartbeat).total_seconds()
                if stream_duration > MAX_STREAM_DURATION_SECONDS:
                    yield {
                        "event": "timeout",
                        "data": to_json_string({"message": "Stream timeout"}),
                    }
                    break

                # Try to get event from queue
                if queue:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=1.0)
                        event_id += 1

                        # Skip events before last_event_id (for resumption)
                        if last_event_id and event_id <= last_event_id:
                            continue

                        event["id"] = str(event_id)
                        yield event

                        # Check for completion
                        if event.get("event") in (
                            SSEEventType.COMPLETE.value,
                            SSEEventType.ERROR.value,
                        ):
                            break

                    except TimeoutError:
                        pass

                # Send heartbeat
                now = datetime.now(UTC)
                if (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL_SECONDS:
                    yield {
                        "event": SSEEventType.HEARTBEAT.value,
                        "data": to_json_string({"timestamp": now.isoformat()}),
                    }
                    last_heartbeat = now

                # If no queue yet, wait for it
                if not queue:
                    await asyncio.sleep(0.5)
                    queue = _active_streams.get(str(session_id))

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for session {session_id}")

    return EventSourceResponse(
        event_generator(),
        headers={"X-Accel-Buffering": "no"},
    )


# =============================================================================
# Export Endpoint
# =============================================================================


@router.post("/sessions/{session_id}/export")
async def export_session(
    session_id: UUID,
    auth: AuthDep,
    db: AppDbDep,
    format: ExportFormat = Query(ExportFormat.MARKDOWN),  # noqa: B008
) -> dict[str, Any]:
    """Export a session as JSON or Markdown."""
    # Get session with messages
    session = await get_session(session_id, auth, db)

    if format == ExportFormat.JSON:
        return {
            "format": "json",
            "content": session.model_dump(mode="json"),
        }

    # Markdown format
    lines = [
        "# Assistant Session",
        "",
        f"**Session ID:** {session.id}",
        f"**Created:** {session.created_at.isoformat()}",
        f"**Messages:** {len(session.messages)}",
        "",
        "---",
        "",
    ]

    for msg in session.messages:
        role_label = msg.role.value.upper()
        lines.append(f"## {role_label}")
        lines.append("")
        lines.append(msg.content)
        lines.append("")

        if msg.tool_calls:
            lines.append("**Tool Calls:**")
            for tc in msg.tool_calls:
                lines.append(f"- `{tc.get('name', 'unknown')}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    return {
        "format": "markdown",
        "content": "\n".join(lines),
    }
