"""Tests for IPython magic commands."""

from unittest.mock import MagicMock

import pytest

from dataing_notebook.magic import DataingMagics, load_ipython_extension, unload_ipython_extension
from dataing_notebook.state import get_state, reset_state


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before and after each test."""
    reset_state()
    yield
    reset_state()


@pytest.fixture
def mock_shell():
    """Create a mock IPython shell."""
    from IPython.core.interactiveshell import InteractiveShell

    # Create a minimal InteractiveShell instance for testing
    # We use instance() to get a singleton, but it may not be fully initialized
    try:
        shell = InteractiveShell.instance()
    except Exception:
        # If we can't create a real shell, use a MagicMock with the right base class
        shell = MagicMock(spec=InteractiveShell)
        shell.config = MagicMock()
    return shell


@pytest.fixture
def magics(mock_shell):
    """Create DataingMagics instance."""
    # We need to pass None if the shell doesn't work properly
    # IPython magics can be instantiated with shell=None for testing
    try:
        return DataingMagics(mock_shell)
    except Exception:
        # Create magics without shell for simpler testing
        magics = DataingMagics.__new__(DataingMagics)
        magics._state = get_state()
        return magics


class TestDataingMagics:
    """Tests for DataingMagics class."""

    def test_empty_line_shows_help(self, magics, capsys) -> None:
        """Test that empty line shows help."""
        magics.dataing("")
        captured = capsys.readouterr()
        assert "Dataing Magic Commands" in captured.out

    def test_help_command(self, magics, capsys) -> None:
        """Test help command."""
        magics.dataing("help")
        captured = capsys.readouterr()
        assert "Dataing Magic Commands" in captured.out
        assert "%dataing connect" in captured.out
        assert "%dataing attach" in captured.out

    def test_unknown_command(self, magics, capsys) -> None:
        """Test unknown command shows error and help."""
        magics.dataing("unknown_command")
        captured = capsys.readouterr()
        assert "Unknown subcommand" in captured.err
        assert "Dataing Magic Commands" in captured.out

    def test_status_no_connection(self, magics, capsys) -> None:
        """Test status when not connected."""
        magics.dataing("status")
        captured = capsys.readouterr()
        assert "API: Not connected" in captured.out
        assert "Context: Not attached" in captured.out

    def test_connect_creates_client(self, magics, capsys) -> None:
        """Test connect creates client."""
        magics.dataing("connect --base-url https://test.example.com")
        captured = capsys.readouterr()
        assert "Connected to https://test.example.com" in captured.out

        state = get_state()
        assert state.client is not None
        assert state.client.base_url == "https://test.example.com"

    def test_attach_requires_target(self, magics, capsys) -> None:
        """Test attach requires a target."""
        magics.dataing("attach")
        captured = capsys.readouterr()
        assert "attach requires a URN or SQL query" in captured.err

    def test_attach_sql_requires_datasource_or_platform(self, magics, capsys) -> None:
        """Test attach SQL requires --datasource or --platform."""
        magics.dataing('attach "SELECT * FROM orders"')
        captured = capsys.readouterr()
        assert "requires --datasource or --platform" in captured.err

    def test_lineage_requires_context(self, magics, capsys) -> None:
        """Test lineage requires attached context."""
        magics.dataing("lineage")
        captured = capsys.readouterr()
        assert "No context attached" in captured.err

    def test_ask_requires_question(self, magics, capsys) -> None:
        """Test ask requires a question."""
        magics.dataing("ask")
        captured = capsys.readouterr()
        assert "ask requires a question" in captured.err

    def test_ask_requires_context(self, magics, capsys) -> None:
        """Test ask requires attached context."""
        magics.dataing('ask "Why are there null values?"')
        captured = capsys.readouterr()
        assert "No context attached" in captured.err

    def test_clear_context(self, magics, capsys) -> None:
        """Test clear command."""
        # First attach something
        state = get_state()
        mock_context = MagicMock()
        mock_context.bundle_hash = "hash"
        mock_context.bundle_id = "id"
        mock_context.resolved_assets = []
        state.attach_context(mock_context)
        assert state.is_attached is True

        # Now clear
        magics.dataing("clear")
        captured = capsys.readouterr()
        assert "Cleared context" in captured.out
        assert state.is_attached is False

    def test_clear_cache(self, magics, capsys) -> None:
        """Test clear --cache command."""
        state = get_state()
        mock_context = MagicMock()
        mock_context.bundle_hash = "hash"
        mock_context.bundle_id = "id"
        mock_context.resolved_assets = []
        state.attach_context(mock_context)

        magics.dataing("clear --cache")
        captured = capsys.readouterr()
        assert "Cleared context" in captured.out
        assert "Cleared cache" in captured.out
        assert len(state.bundle_cache) == 0


class TestExtensionLoading:
    """Tests for extension loading/unloading."""

    def test_load_extension(self, mock_shell) -> None:
        """Test loading extension registers magics."""
        # Just verify it doesn't raise an error
        try:
            load_ipython_extension(mock_shell)
        except Exception as e:
            pytest.fail(f"load_ipython_extension raised {e}")

    def test_unload_extension_resets_state(self, mock_shell) -> None:
        """Test unloading extension resets state."""
        # Set up some state
        state = get_state()
        state.default_platform = "postgres"

        unload_ipython_extension(mock_shell)

        # State should be reset
        new_state = get_state()
        assert new_state.default_platform is None


class TestAttachCommand:
    """Tests for attach command variations."""

    def test_detect_sql_by_select(self, magics, capsys) -> None:
        """Test that SELECT queries are detected as SQL."""
        # This will fail because no datasource/platform, which proves detection works
        magics.dataing('attach "SELECT * FROM orders"')
        captured = capsys.readouterr()
        # Should fail with datasource error (proving it detected SQL)
        assert "requires --datasource or --platform" in captured.err

    def test_detect_sql_by_with(self, magics, capsys) -> None:
        """Test that WITH queries are detected as SQL."""
        magics.dataing('attach "WITH cte AS (SELECT 1) SELECT * FROM cte"')
        captured = capsys.readouterr()
        # Should fail with datasource error (proving it detected SQL)
        assert "requires --datasource or --platform" in captured.err

    def test_detect_sql_by_from(self, magics, capsys) -> None:
        """Test that queries with FROM are detected as SQL."""
        magics.dataing('attach "TRUNCATE FROM orders"')
        captured = capsys.readouterr()
        # Should fail with datasource error (proving it detected SQL)
        assert "requires --datasource or --platform" in captured.err


class TestHistoryCommand:
    """Tests for %dataing history command."""

    def test_history_requires_connection(self, magics, capsys) -> None:
        """Test history without connection shows error."""
        magics.dataing("history")
        captured = capsys.readouterr()
        assert "Not connected" in captured.err

    def test_history_calls_api(self, magics, capsys) -> None:
        """Test history calls API on client."""
        state = get_state()
        mock_response = MagicMock()
        mock_response.json.return_value = []
        state.client = MagicMock()
        state.client._request.return_value = mock_response
        magics.dataing("history")
        state.client._request.assert_called_once_with("GET", "/api/v1/investigations")

    def test_history_renders_results(self, magics, capsys) -> None:
        """Test history renders returned investigations."""
        state = get_state()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "investigation_id": "abc-123-def-456",
                "dataset_id": "orders_table",
                "status": "completed",
                "created_at": "2026-01-28T10:00:00Z",
            },
        ]
        state.client = MagicMock()
        state.client._request.return_value = mock_response
        magics.dataing("history")
        captured = capsys.readouterr()
        # Check output - may be HTML object (in notebook) or plain text
        assert (
            "abc-123" in captured.out
            or "orders" in captured.out
            or "HTML" in captured.out  # IPython HTML object repr
        )

    def test_history_empty_results(self, magics, capsys) -> None:
        """Test history with no investigations."""
        state = get_state()
        mock_response = MagicMock()
        mock_response.json.return_value = []
        state.client = MagicMock()
        state.client._request.return_value = mock_response
        magics.dataing("history")
        captured = capsys.readouterr()
        assert "No investigations found" in captured.out

    def test_history_api_error(self, magics, capsys) -> None:
        """Test history handles API errors gracefully."""
        state = get_state()
        state.client = MagicMock()
        state.client._request.side_effect = Exception("Connection failed")
        magics.dataing("history")
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_history_limit_filter(self, magics, capsys) -> None:
        """Test history respects --limit filter."""
        state = get_state()
        mock_response = MagicMock()
        # Return more results than limit
        mock_response.json.return_value = [
            {
                "investigation_id": f"id-{i}",
                "dataset_id": "test",
                "status": "completed",
                "created_at": "2026-01-28T10:00:00Z",
            }
            for i in range(10)
        ]
        state.client = MagicMock()
        state.client._request.return_value = mock_response
        magics.dataing("history --limit 3")
        captured = capsys.readouterr()
        # Should show pagination info or HTML (in notebook)
        assert "1-3" in captured.out or "Showing" in captured.out or "HTML" in captured.out


class TestReplayCommand:
    """Tests for %dataing replay command."""

    def test_replay_requires_connection(self, magics, capsys) -> None:
        """Test replay without connection shows error."""
        magics.dataing("replay abc-123")
        captured = capsys.readouterr()
        assert "Not connected" in captured.err

    def test_replay_requires_id(self, magics, capsys) -> None:
        """Test replay without ID shows usage error."""
        state = get_state()
        state.client = MagicMock()
        magics.dataing("replay")
        captured = capsys.readouterr()
        # argparse should output usage
        assert "investigation_id" in captured.err or "usage" in captured.err.lower()

    def test_replay_fetches_investigation(self, magics, capsys) -> None:
        """Test replay calls get_investigation on client."""
        state = get_state()
        state.client = MagicMock()
        mock_inv = MagicMock()
        mock_inv.investigation_id = "abc-123-def"
        mock_inv.status = "completed"
        mock_inv.root_hash = "hash123"
        mock_inv.main_branch = MagicMock()
        mock_inv.main_branch.branch_id = "main"
        mock_inv.main_branch.status = "completed"
        mock_inv.main_branch.current_step = "done"
        mock_inv.main_branch.evidence = []
        mock_inv.main_branch.synthesis = None
        state.client.get_investigation.return_value = mock_inv
        magics.dataing("replay abc-123-def")
        state.client.get_investigation.assert_called_once_with("abc-123-def")

    def test_replay_stores_in_history(self, magics, capsys) -> None:
        """Test replayed investigation is added to session history."""
        state = get_state()
        state.client = MagicMock()
        mock_inv = MagicMock()
        mock_inv.investigation_id = "abc-123"
        mock_inv.status = "completed"
        mock_inv.root_hash = "hash123"
        mock_inv.main_branch = MagicMock()
        mock_inv.main_branch.branch_id = "main"
        mock_inv.main_branch.status = "completed"
        mock_inv.main_branch.current_step = "done"
        mock_inv.main_branch.evidence = []
        mock_inv.main_branch.synthesis = None
        state.client.get_investigation.return_value = mock_inv
        initial_history_len = len(state._history)
        magics.dataing("replay abc-123")
        assert len(state._history) == initial_history_len + 1
        assert state._history[-1]["action"] == "replay"

    def test_replay_invalid_id(self, magics, capsys) -> None:
        """Test replay with invalid ID shows error."""
        state = get_state()
        state.client = MagicMock()
        state.client.get_investigation.side_effect = Exception("404 Not found")
        magics.dataing("replay nonexistent-id")
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "Error" in captured.err


class TestCompareCommand:
    """Tests for %dataing compare command."""

    def test_compare_requires_connection(self, magics, capsys) -> None:
        """Test compare without connection shows error."""
        magics.dataing("compare id1 id2")
        captured = capsys.readouterr()
        assert "Not connected" in captured.err

    def test_compare_requires_two_ids(self, magics, capsys) -> None:
        """Test compare requires exactly two investigation IDs."""
        state = get_state()
        state.client = MagicMock()
        magics.dataing("compare only-one-id")
        captured = capsys.readouterr()
        # argparse should report missing argument
        assert "id2" in captured.err or "required" in captured.err.lower()

    def test_compare_fetches_both(self, magics, capsys) -> None:
        """Test compare calls get_investigation for both IDs."""
        state = get_state()
        state.client = MagicMock()
        mock_inv = MagicMock()
        mock_inv.investigation_id = "test-id"
        mock_inv.status = "completed"
        mock_inv.main_branch = MagicMock()
        mock_inv.main_branch.evidence = []
        mock_inv.main_branch.synthesis = None
        state.client.get_investigation.return_value = mock_inv
        magics.dataing("compare id-aaa id-bbb")
        assert state.client.get_investigation.call_count == 2

    def test_compare_handles_first_id_failure(self, magics, capsys) -> None:
        """Test compare handles error when first ID fetch fails."""
        state = get_state()
        state.client = MagicMock()
        state.client.get_investigation.side_effect = Exception("Not found")
        magics.dataing("compare bad-id good-id")
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_compare_handles_second_id_failure(self, magics, capsys) -> None:
        """Test compare handles error when second ID fetch fails."""
        state = get_state()
        state.client = MagicMock()
        mock_inv = MagicMock()
        mock_inv.investigation_id = "good"
        mock_inv.status = "completed"
        mock_inv.main_branch = MagicMock()
        mock_inv.main_branch.evidence = []
        mock_inv.main_branch.synthesis = None
        call_count = [0]

        def side_effect(inv_id):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Not found")
            return mock_inv

        state.client.get_investigation.side_effect = side_effect
        magics.dataing("compare good-id bad-id")
        captured = capsys.readouterr()
        assert "Error" in captured.err
