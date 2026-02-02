"""Unit tests for DataingAssistant."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from dataing.agents.assistant import (
    ASSISTANT_SYSTEM_PROMPT,
    DataingAssistant,
    create_assistant,
)


class TestDataingAssistantInit:
    """Tests for DataingAssistant initialization."""

    def test_init_minimal(self) -> None:
        """Test initialization with minimal arguments."""
        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent"):
                    assistant = DataingAssistant(
                        api_key="test-key",
                        tenant_id="test-tenant",
                    )

                    assert assistant._tenant_id == "test-tenant"
                    assert assistant._repo_path == Path(".")
                    assert assistant._github_token is None

    def test_init_with_uuid_tenant(self) -> None:
        """Test initialization with UUID tenant ID."""
        tenant_uuid = UUID("12345678-1234-5678-1234-567812345678")

        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent"):
                    assistant = DataingAssistant(
                        api_key="test-key",
                        tenant_id=tenant_uuid,
                    )

                    assert assistant._tenant_id == str(tenant_uuid)

    def test_init_with_all_options(self) -> None:
        """Test initialization with all options."""
        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent"):
                    assistant = DataingAssistant(
                        api_key="test-key",
                        tenant_id="test-tenant",
                        model="claude-opus-4-20250514",
                        repo_path="/path/to/repo",
                        github_token="gh-token",
                        log_directories=["/var/log", "/app/logs"],
                        max_retries=5,
                    )

                    assert assistant._repo_path == Path("/path/to/repo")
                    assert assistant._github_token == "gh-token"


class TestDataingAssistantTools:
    """Tests for DataingAssistant tool building."""

    @pytest.fixture
    def assistant(self) -> DataingAssistant:
        """Create a test assistant instance."""
        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent"):
                    return DataingAssistant(
                        api_key="test-key",
                        tenant_id="test-tenant",
                    )

    def test_build_tools_includes_file_tools(self, assistant: DataingAssistant) -> None:
        """Test that file tools are included."""
        tools = assistant._build_tools()
        tool_names = [t.function.__name__ for t in tools if hasattr(t, "function")]

        # Local file tools
        assert "read_local_file" in tool_names
        assert "search_in_files" in tool_names
        assert "list_directory" in tool_names

    def test_build_tools_includes_docker_tools(self, assistant: DataingAssistant) -> None:
        """Test that Docker tools are included."""
        tools = assistant._build_tools()
        tool_names = [t.function.__name__ for t in tools if hasattr(t, "function")]

        # Docker tools
        assert "list_docker_containers" in tool_names
        assert "get_docker_container_status" in tool_names
        assert "get_docker_container_health" in tool_names
        assert "get_docker_container_stats" in tool_names
        assert "find_unhealthy_docker_containers" in tool_names

    def test_build_tools_includes_log_tools(self, assistant: DataingAssistant) -> None:
        """Test that log tools are included."""
        tools = assistant._build_tools()
        tool_names = [t.function.__name__ for t in tools if hasattr(t, "function")]

        # Log tools (bound methods)
        assert "_get_logs" in tool_names
        assert "_search_logs" in tool_names
        assert "_get_recent_errors" in tool_names


class TestDataingAssistantLogTools:
    """Tests for DataingAssistant log tool methods."""

    @pytest.fixture
    def assistant(self) -> DataingAssistant:
        """Create a test assistant instance."""
        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent"):
                    return DataingAssistant(
                        api_key="test-key",
                        tenant_id="test-tenant",
                    )

    @pytest.mark.asyncio
    async def test_get_logs_success(self, assistant: DataingAssistant) -> None:
        """Test successful log retrieval."""
        from datetime import datetime

        from dataing.agents.tools.log_providers.base import LogEntry, LogResult

        mock_result = LogResult(
            entries=[
                LogEntry(
                    timestamp=datetime(2024, 1, 15, 10, 30, 45),
                    message="Application started",
                    level="info",
                    source="/app/logs/app.log",
                ),
                LogEntry(
                    timestamp=datetime(2024, 1, 15, 10, 30, 46),
                    message="Database connected",
                    level="info",
                    source="/app/logs/app.log",
                ),
            ],
            source="/app/logs/app.log",
        )

        assistant._log_provider.get_logs = AsyncMock(return_value=mock_result)

        result = await assistant._get_logs("/app/logs/app.log", max_entries=10)

        assert "2 entries" in result
        assert "Application started" in result
        assert "Database connected" in result

    @pytest.mark.asyncio
    async def test_get_logs_error(self, assistant: DataingAssistant) -> None:
        """Test log retrieval with error."""
        from dataing.agents.tools.log_providers.base import LogResult

        mock_result = LogResult(
            entries=[],
            source="/nonexistent/log",
            error="File not found",
        )

        assistant._log_provider.get_logs = AsyncMock(return_value=mock_result)

        result = await assistant._get_logs("/nonexistent/log")

        assert "Error reading logs" in result
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_search_logs_success(self, assistant: DataingAssistant) -> None:
        """Test successful log search."""
        from datetime import datetime

        from dataing.agents.tools.log_providers.base import LogEntry, LogResult

        mock_result = LogResult(
            entries=[
                LogEntry(
                    timestamp=datetime(2024, 1, 15, 10, 30, 48),
                    message="ERROR: Connection refused",
                    level="error",
                    source="/app/logs/app.log",
                ),
            ],
            source="multiple",
        )

        assistant._log_provider.search_logs = AsyncMock(return_value=mock_result)

        result = await assistant._search_logs("ERROR")

        assert "1 entries" in result
        assert "Connection refused" in result

    @pytest.mark.asyncio
    async def test_get_recent_errors_success(self, assistant: DataingAssistant) -> None:
        """Test successful recent errors retrieval."""
        from datetime import datetime

        from dataing.agents.tools.log_providers.base import LogEntry, LogResult

        mock_result = LogResult(
            entries=[
                LogEntry(
                    timestamp=datetime(2024, 1, 15, 10, 30, 48),
                    message="Failed to connect to database",
                    level="error",
                    source="/app/logs/app.log",
                    metadata={
                        "context_before": ["Attempting connection..."],
                        "context_after": ["Retrying in 5 seconds"],
                    },
                ),
            ],
            source="/app/logs/app.log",
        )

        assistant._log_provider.get_recent_errors = AsyncMock(return_value=mock_result)

        result = await assistant._get_recent_errors("/app/logs/app.log")

        assert "1 found" in result
        assert "Failed to connect" in result
        assert "Context before" in result
        assert "Context after" in result


class TestDataingAssistantAsk:
    """Tests for DataingAssistant.ask method."""

    @pytest.fixture
    def assistant(self) -> DataingAssistant:
        """Create a test assistant instance."""
        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent") as mock_agent_class:
                    mock_agent = MagicMock()
                    mock_agent.ask = AsyncMock(return_value="Test response")
                    mock_agent_class.return_value = mock_agent

                    assistant = DataingAssistant(
                        api_key="test-key",
                        tenant_id="test-tenant",
                    )
                    assistant._agent = mock_agent
                    return assistant

    @pytest.mark.asyncio
    async def test_ask_simple_question(self, assistant: DataingAssistant) -> None:
        """Test asking a simple question."""
        result = await assistant.ask("What containers are running?")

        assert result == "Test response"
        assistant._agent.ask.assert_called_once()

    @pytest.mark.asyncio
    async def test_ask_with_session_id(self, assistant: DataingAssistant) -> None:
        """Test asking with a session ID."""
        await assistant.ask("Check logs", session_id="session-123")

        call_args = assistant._agent.ask.call_args
        assert "session-123" in str(call_args)

    @pytest.mark.asyncio
    async def test_ask_with_context(self, assistant: DataingAssistant) -> None:
        """Test asking with additional context."""
        context = {
            "investigation": {
                "id": "inv-123",
                "status": "in_progress",
            },
            "datasource": {
                "name": "production-db",
                "type": "postgresql",
            },
        }

        await assistant.ask("What's the status?", context=context)

        call_args = assistant._agent.ask.call_args
        prompt = call_args[0][0]
        assert "inv-123" in prompt
        assert "production-db" in prompt

    @pytest.mark.asyncio
    async def test_ask_with_handlers(self, assistant: DataingAssistant) -> None:
        """Test asking with streaming handlers."""
        handlers = MagicMock()

        await assistant.ask("Check health", handlers=handlers)

        call_args = assistant._agent.ask.call_args
        assert call_args.kwargs.get("handlers") == handlers


class TestDataingAssistantContextFormatting:
    """Tests for context formatting."""

    @pytest.fixture
    def assistant(self) -> DataingAssistant:
        """Create a test assistant instance."""
        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent"):
                    return DataingAssistant(
                        api_key="test-key",
                        tenant_id="test-tenant",
                    )

    def test_format_context_with_investigation(self, assistant: DataingAssistant) -> None:
        """Test formatting context with investigation."""
        context = {
            "investigation": {
                "id": "inv-456",
                "status": "completed",
                "finding": {"root_cause": "Null values in column X"},
            },
        }

        result = assistant._format_context(context)

        assert "inv-456" in result
        assert "completed" in result
        assert "Null values" in result

    def test_format_context_with_datasource(self, assistant: DataingAssistant) -> None:
        """Test formatting context with datasource."""
        context = {
            "datasource": {
                "name": "analytics-dw",
                "type": "snowflake",
            },
        }

        result = assistant._format_context(context)

        assert "analytics-dw" in result
        assert "snowflake" in result

    def test_format_context_with_alerts(self, assistant: DataingAssistant) -> None:
        """Test formatting context with alerts."""
        context = {
            "recent_alerts": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
        }

        result = assistant._format_context(context)

        assert "Recent alerts: 3" in result


class TestCreateAssistant:
    """Tests for the create_assistant factory function."""

    def test_create_assistant_basic(self) -> None:
        """Test creating an assistant with basic arguments."""
        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent"):
                    assistant = create_assistant(
                        api_key="test-key",
                        tenant_id="test-tenant",
                    )

                    assert isinstance(assistant, DataingAssistant)
                    assert assistant._tenant_id == "test-tenant"

    def test_create_assistant_with_kwargs(self) -> None:
        """Test creating an assistant with additional kwargs."""
        with patch("dataing.agents.assistant.AnthropicProvider"):
            with patch("dataing.agents.assistant.AnthropicModel"):
                with patch("dataing.agents.assistant.BondAgent"):
                    assistant = create_assistant(
                        api_key="test-key",
                        tenant_id="test-tenant",
                        github_token="gh-token",
                        log_directories=["/logs"],
                    )

                    assert assistant._github_token == "gh-token"


class TestSystemPrompt:
    """Tests for the system prompt."""

    def test_system_prompt_contains_capabilities(self) -> None:
        """Test that system prompt describes capabilities."""
        assert "Infrastructure debugging" in ASSISTANT_SYSTEM_PROMPT
        assert "Data questions" in ASSISTANT_SYSTEM_PROMPT
        assert "Investigation support" in ASSISTANT_SYSTEM_PROMPT

    def test_system_prompt_contains_dataing_overview(self) -> None:
        """Test that system prompt describes Dataing platform."""
        assert "Dataing" in ASSISTANT_SYSTEM_PROMPT
        assert "data quality" in ASSISTANT_SYSTEM_PROMPT
        assert "Investigations" in ASSISTANT_SYSTEM_PROMPT

    def test_system_prompt_contains_approach_guidance(self) -> None:
        """Test that system prompt includes approach guidance."""
        assert "helpful" in ASSISTANT_SYSTEM_PROMPT
        assert "reasoning" in ASSISTANT_SYSTEM_PROMPT
        assert "next steps" in ASSISTANT_SYSTEM_PROMPT
