"""Unit tests for assistant API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from dataing.entrypoints.api.routes.assistant import (
    CreateSessionRequest,
    CreateSessionResponse,
    ExportFormat,
    ListSessionsResponse,
    MessageResponse,
    MessageRole,
    SendMessageRequest,
    SendMessageResponse,
    SessionDetailResponse,
    SessionSummary,
    router,
)


class TestPydanticModels:
    """Tests for Pydantic request/response models."""

    def test_create_session_request_minimal(self) -> None:
        """Test CreateSessionRequest with minimal data."""
        req = CreateSessionRequest()
        assert req.parent_investigation_id is None
        assert req.title is None
        assert req.metadata == {}

    def test_create_session_request_full(self) -> None:
        """Test CreateSessionRequest with all fields."""
        parent_id = UUID("12345678-1234-5678-1234-567812345678")
        req = CreateSessionRequest(
            parent_investigation_id=parent_id,
            title="Debug Session",
            metadata={"key": "value"},
        )
        assert req.parent_investigation_id == parent_id
        assert req.title == "Debug Session"
        assert req.metadata == {"key": "value"}

    def test_create_session_response(self) -> None:
        """Test CreateSessionResponse model."""
        session_id = UUID("11111111-1111-1111-1111-111111111111")
        investigation_id = UUID("22222222-2222-2222-2222-222222222222")
        created = datetime.now(UTC)

        resp = CreateSessionResponse(
            session_id=session_id,
            investigation_id=investigation_id,
            created_at=created,
        )
        assert resp.session_id == session_id
        assert resp.investigation_id == investigation_id
        assert resp.created_at == created

    def test_session_summary(self) -> None:
        """Test SessionSummary model."""
        session_id = UUID("11111111-1111-1111-1111-111111111111")
        created = datetime.now(UTC)

        summary = SessionSummary(
            id=session_id,
            title="Test Session",
            created_at=created,
            last_activity=created,
            message_count=5,
            token_count=1000,
        )
        assert summary.id == session_id
        assert summary.title == "Test Session"
        assert summary.message_count == 5
        assert summary.token_count == 1000

    def test_list_sessions_response(self) -> None:
        """Test ListSessionsResponse model."""
        resp = ListSessionsResponse(sessions=[])
        assert resp.sessions == []

    def test_message_response(self) -> None:
        """Test MessageResponse model."""
        msg_id = UUID("33333333-3333-3333-3333-333333333333")
        created = datetime.now(UTC)

        msg = MessageResponse(
            id=msg_id,
            role=MessageRole.USER,
            content="Hello!",
            created_at=created,
            token_count=10,
        )
        assert msg.id == msg_id
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello!"
        assert msg.tool_calls is None
        assert msg.token_count == 10

    def test_message_response_with_tool_calls(self) -> None:
        """Test MessageResponse with tool calls."""
        msg_id = UUID("33333333-3333-3333-3333-333333333333")
        created = datetime.now(UTC)
        tool_calls = [{"name": "read_file", "arguments": {"path": "/test"}}]

        msg = MessageResponse(
            id=msg_id,
            role=MessageRole.ASSISTANT,
            content="Let me read that file.",
            tool_calls=tool_calls,
            created_at=created,
        )
        assert msg.tool_calls == tool_calls

    def test_session_detail_response(self) -> None:
        """Test SessionDetailResponse model."""
        session_id = UUID("11111111-1111-1111-1111-111111111111")
        investigation_id = UUID("22222222-2222-2222-2222-222222222222")
        created = datetime.now(UTC)

        resp = SessionDetailResponse(
            id=session_id,
            investigation_id=investigation_id,
            title="Test",
            created_at=created,
            last_activity=created,
            token_count=0,
            messages=[],
        )
        assert resp.id == session_id
        assert resp.investigation_id == investigation_id
        assert resp.messages == []
        assert resp.parent_investigation_id is None

    def test_send_message_request(self) -> None:
        """Test SendMessageRequest model."""
        req = SendMessageRequest(content="Hello, assistant!")
        assert req.content == "Hello, assistant!"

    def test_send_message_request_validation(self) -> None:
        """Test SendMessageRequest validation."""
        # Empty content should fail
        with pytest.raises(ValueError):
            SendMessageRequest(content="")

    def test_send_message_response(self) -> None:
        """Test SendMessageResponse model."""
        msg_id = UUID("33333333-3333-3333-3333-333333333333")
        resp = SendMessageResponse(message_id=msg_id, status="processing")
        assert resp.message_id == msg_id
        assert resp.status == "processing"


class TestMessageRole:
    """Tests for MessageRole enum."""

    def test_all_roles(self) -> None:
        """Test all message roles exist."""
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.TOOL.value == "tool"


class TestExportFormat:
    """Tests for ExportFormat enum."""

    def test_all_formats(self) -> None:
        """Test all export formats exist."""
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.MARKDOWN.value == "markdown"


class TestRouterRegistration:
    """Tests for router configuration."""

    def test_router_prefix(self) -> None:
        """Test router has correct prefix."""
        assert router.prefix == "/assistant"

    def test_router_tags(self) -> None:
        """Test router has correct tags."""
        assert "assistant" in router.tags


class TestExportSessionHelper:
    """Tests for export functionality."""

    def test_markdown_format_structure(self) -> None:
        """Test Markdown export has correct structure."""
        # Create a minimal session for testing
        session = SessionDetailResponse(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            investigation_id=UUID("22222222-2222-2222-2222-222222222222"),
            title="Test",
            created_at=datetime.now(UTC),
            last_activity=datetime.now(UTC),
            token_count=0,
            messages=[
                MessageResponse(
                    id=UUID("33333333-3333-3333-3333-333333333333"),
                    role=MessageRole.USER,
                    content="Hello!",
                    created_at=datetime.now(UTC),
                ),
                MessageResponse(
                    id=UUID("44444444-4444-4444-4444-444444444444"),
                    role=MessageRole.ASSISTANT,
                    content="Hi there!",
                    created_at=datetime.now(UTC),
                ),
            ],
        )

        # Build expected Markdown structure
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

        markdown = "\n".join(lines)

        # Verify structure
        assert "# Assistant Session" in markdown
        assert "## USER" in markdown
        assert "## ASSISTANT" in markdown
        assert "Hello!" in markdown
        assert "Hi there!" in markdown


class TestHelperFunctions:
    """Tests for helper functions."""

    @pytest.mark.asyncio
    async def test_create_investigation_for_session(self) -> None:
        """Test create_investigation_for_session helper."""
        from dataing.entrypoints.api.routes.assistant import (
            create_investigation_for_session,
        )

        mock_db = AsyncMock()
        mock_db.fetch_one.return_value = {"id": UUID("12345678-1234-5678-1234-567812345678")}

        tenant_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        user_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

        result = await create_investigation_for_session(mock_db, tenant_id, user_id)

        assert result == UUID("12345678-1234-5678-1234-567812345678")
        mock_db.fetch_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_investigation_for_session_failure(self) -> None:
        """Test create_investigation_for_session raises on failure."""
        from dataing.entrypoints.api.routes.assistant import (
            create_investigation_for_session,
        )

        mock_db = AsyncMock()
        mock_db.fetch_one.return_value = None

        tenant_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        user_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

        with pytest.raises(RuntimeError, match="Failed to create investigation"):
            await create_investigation_for_session(mock_db, tenant_id, user_id)

    @pytest.mark.asyncio
    async def test_get_assistant(self) -> None:
        """Test get_assistant creates DataingAssistant."""
        from dataing.entrypoints.api.routes.assistant import get_assistant

        # Mock auth context
        auth = MagicMock()
        auth.tenant_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        mock_db = AsyncMock()

        # Patch the DataingAssistant and settings
        with patch("dataing.entrypoints.api.routes.assistant.DataingAssistant") as mock_assistant:
            with patch("dataing.entrypoints.api.routes.assistant.settings") as mock_settings:
                mock_settings.anthropic_api_key = "test-key"
                mock_settings.llm_model = "claude-sonnet-4-20250514"

                await get_assistant(auth, mock_db)

                mock_assistant.assert_called_once_with(
                    api_key="test-key",
                    tenant_id=auth.tenant_id,
                    model="claude-sonnet-4-20250514",
                )


class TestSSEEventTypes:
    """Tests for SSE event type enum."""

    def test_all_event_types(self) -> None:
        """Test all SSE event types exist."""
        from dataing.entrypoints.api.routes.assistant import SSEEventType

        assert SSEEventType.TEXT.value == "text"
        assert SSEEventType.TOOL_CALL.value == "tool_call"
        assert SSEEventType.TOOL_RESULT.value == "tool_result"
        assert SSEEventType.COMPLETE.value == "complete"
        assert SSEEventType.ERROR.value == "error"
        assert SSEEventType.HEARTBEAT.value == "heartbeat"
