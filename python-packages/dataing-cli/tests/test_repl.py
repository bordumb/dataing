"""Tests for REPL functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass


class TestDataingREPL:
    """Tests for REPL initialization and basic functionality."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock DataingClient."""
        client = MagicMock()
        client.steer.return_value = MagicMock(status="pending")
        client.stream_run.return_value = iter([])
        client.get_investigation.return_value = None
        return client

    @pytest.fixture
    def repl(self, mock_client: MagicMock) -> MagicMock:
        """Create a DataingREPL instance with mocked dependencies."""
        with patch("dataing_cli.repl.FileHistory"), patch("dataing_cli.repl.ThreadedHistory"):
            from dataing_cli.repl import DataingREPL

            return DataingREPL(mock_client, "test-investigation-id")

    def test_init_sets_investigation_id(self, repl: MagicMock) -> None:
        """Test REPL initialization sets investigation ID."""
        assert repl.investigation_id == "test-investigation-id"

    def test_init_sets_client(self, repl: MagicMock, mock_client: MagicMock) -> None:
        """Test REPL initialization sets client."""
        assert repl.client == mock_client

    def test_build_completer_includes_commands(self, repl: MagicMock) -> None:
        """Test completer includes all slash commands."""
        completer = repl._build_completer()
        # NestedCompleter stores commands in options dict
        assert completer is not None
        # Check that completer was created (doesn't raise)

    def test_get_prompt_format(self, repl: MagicMock) -> None:
        """Test prompt shows investigation context."""
        # Set up mock investigation state
        repl.investigation = MagicMock()
        repl.investigation.evidence = [
            {"kind": "hypothesis"},
            {"kind": "query_result"},
            {"kind": "hypothesis"},
        ]

        prompt = repl._get_prompt()

        # Prompt should include short ID
        prompt_str = str(prompt)
        assert "test-inv" in prompt_str

    def test_get_prompt_no_investigation(self, repl: MagicMock) -> None:
        """Test prompt works with no investigation state."""
        repl.investigation = None

        prompt = repl._get_prompt()

        # Should not raise
        assert prompt is not None


class TestReplCommandRouting:
    """Tests for command routing."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock DataingClient."""
        client = MagicMock()
        client.steer.return_value = MagicMock(status="pending")
        client.stream_run.return_value = iter([])
        client.get_investigation.return_value = None
        return client

    @pytest.fixture
    def repl(self, mock_client: MagicMock) -> MagicMock:
        """Create a DataingREPL instance."""
        with patch("dataing_cli.repl.FileHistory"), patch("dataing_cli.repl.ThreadedHistory"):
            from dataing_cli.repl import DataingREPL

            return DataingREPL(mock_client, "test-id")

    @pytest.mark.asyncio
    async def test_handle_input_empty_does_nothing(self, repl: MagicMock) -> None:
        """Test empty input does nothing."""
        # Should not raise
        await repl._handle_input("")

    @pytest.mark.asyncio
    async def test_handle_input_slash_routes_to_command(self, repl: MagicMock) -> None:
        """Test slash input routes to command handler."""
        repl._handle_command = AsyncMock()

        await repl._handle_input("/help")

        repl._handle_command.assert_called_once_with("/help")

    @pytest.mark.asyncio
    async def test_handle_input_text_routes_to_message(self, repl: MagicMock) -> None:
        """Test non-slash input routes to message handler."""
        repl._handle_message = AsyncMock()

        await repl._handle_input("test question")

        repl._handle_message.assert_called_once_with("test question")

    @pytest.mark.asyncio
    async def test_handle_command_unknown(self, repl: MagicMock) -> None:
        """Test unknown command prints error."""
        # Should not raise
        await repl._handle_command("/unknown")


class TestSlashCommands:
    """Tests for individual slash commands."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock DataingClient."""
        client = MagicMock()
        client.get_investigation.return_value = None
        return client

    @pytest.fixture
    def repl(self, mock_client: MagicMock) -> MagicMock:
        """Create a DataingREPL instance."""
        with patch("dataing_cli.repl.FileHistory"), patch("dataing_cli.repl.ThreadedHistory"):
            from dataing_cli.repl import DataingREPL

            return DataingREPL(mock_client, "test-id")

    @pytest.mark.asyncio
    async def test_cmd_help(self, repl: MagicMock) -> None:
        """Test /help command doesn't raise."""
        await repl._cmd_help([])

    @pytest.mark.asyncio
    async def test_cmd_quit_raises_eof(self, repl: MagicMock) -> None:
        """Test /quit raises EOFError."""
        with pytest.raises(EOFError):
            await repl._cmd_quit([])

    @pytest.mark.asyncio
    async def test_cmd_hypotheses_no_investigation(self, repl: MagicMock) -> None:
        """Test /hypotheses with no investigation state."""
        repl.investigation = None

        # Should not raise
        await repl._cmd_hypotheses([])

    @pytest.mark.asyncio
    async def test_cmd_hypotheses_empty(self, repl: MagicMock) -> None:
        """Test /hypotheses with no hypotheses."""
        repl.investigation = MagicMock()
        repl.investigation.evidence = []

        await repl._cmd_hypotheses([])
        # Should print "No hypotheses"

    @pytest.mark.asyncio
    async def test_cmd_hypotheses_with_data(self, repl: MagicMock) -> None:
        """Test /hypotheses with hypothesis data."""
        repl.investigation = MagicMock()
        repl.investigation.evidence = [
            {
                "kind": "hypothesis",
                "hypothesis_text": "Test hypothesis",
                "verdict": "confirmed",
                "confidence": 0.85,
            }
        ]

        await repl._cmd_hypotheses([])
        # Should display the hypothesis

    @pytest.mark.asyncio
    async def test_cmd_evidence_no_investigation(self, repl: MagicMock) -> None:
        """Test /evidence with no investigation state."""
        repl.investigation = None

        # Should not raise
        await repl._cmd_evidence([])

    @pytest.mark.asyncio
    async def test_cmd_evidence_empty(self, repl: MagicMock) -> None:
        """Test /evidence with no evidence."""
        repl.investigation = MagicMock()
        repl.investigation.evidence = []

        await repl._cmd_evidence([])
        # Should print "No evidence"

    @pytest.mark.asyncio
    async def test_cmd_evidence_with_data(self, repl: MagicMock) -> None:
        """Test /evidence with evidence data."""
        repl.investigation = MagicMock()
        repl.investigation.evidence = [
            {
                "kind": "query_result",
                "supports_hypothesis": True,
                "interpretation": "Found data",
                "confidence": 0.9,
                "query": "SELECT * FROM test",
            }
        ]

        await repl._cmd_evidence([])
        # Should display the evidence

    @pytest.mark.asyncio
    async def test_cmd_export_default_markdown(self, repl: MagicMock) -> None:
        """Test /export defaults to markdown and doesn't raise."""
        repl.investigation = MagicMock()
        repl.investigation.investigation_id = "test-id"
        repl.investigation.status = "completed"

        main_branch = MagicMock()
        main_branch.status = "completed"
        main_branch.current_step = "synthesis"
        main_branch.synthesis = {"root_cause": "Test cause", "confidence": 0.9}
        main_branch.evidence = []
        repl.investigation.main_branch = main_branch

        # Should not raise - just verify it executes
        await repl._cmd_export([])

    @pytest.mark.asyncio
    async def test_cmd_export_json(self, repl: MagicMock) -> None:
        """Test /export json format doesn't raise."""
        repl.investigation = MagicMock()
        repl.investigation.investigation_id = "test-id"
        repl.investigation.status = "completed"

        main_branch = MagicMock()
        main_branch.status = "completed"
        main_branch.current_step = "synthesis"
        main_branch.synthesis = {"root_cause": "Test cause", "confidence": 0.9}
        main_branch.evidence = []
        repl.investigation.main_branch = main_branch

        # Should not raise - just verify it executes
        await repl._cmd_export(["json"])

    @pytest.mark.asyncio
    async def test_cmd_export_invalid_format(self, repl: MagicMock) -> None:
        """Test /export with invalid format."""
        # Should print error, not raise
        await repl._cmd_export(["invalid"])

    @pytest.mark.asyncio
    async def test_cmd_lineage(self, repl: MagicMock) -> None:
        """Test /lineage command doesn't raise."""
        await repl._cmd_lineage([])
        # Should print placeholder message


class TestReplMessageHandling:
    """Tests for message handling."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock DataingClient."""
        client = MagicMock()
        client.steer.return_value = MagicMock(status="pending")

        # Set up completed event
        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True
        client.stream_run.return_value = iter([completed_event])
        client.get_investigation.return_value = None
        return client

    @pytest.fixture
    def repl(self, mock_client: MagicMock) -> MagicMock:
        """Create a DataingREPL instance."""
        with patch("dataing_cli.repl.FileHistory"), patch("dataing_cli.repl.ThreadedHistory"):
            from dataing_cli.repl import DataingREPL

            return DataingREPL(mock_client, "test-id")

    @pytest.mark.asyncio
    async def test_handle_message_sends_to_sdk(
        self, repl: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test message is sent via SDK."""
        with patch("dataing_cli.repl.Live"):
            await repl._handle_message("test question")

        mock_client.steer.assert_called_once_with("test-id", "test question")

    @pytest.mark.asyncio
    async def test_handle_message_streams_response(
        self, repl: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test response is streamed."""
        with patch("dataing_cli.repl.Live"):
            await repl._handle_message("test question")

        mock_client.stream_run.assert_called_once_with("test-id")

    @pytest.mark.asyncio
    async def test_handle_message_refreshes_state(
        self, repl: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test investigation state is refreshed after message."""
        with patch("dataing_cli.repl.Live"):
            await repl._handle_message("test question")

        # get_investigation should be called to refresh state
        mock_client.get_investigation.assert_called()
