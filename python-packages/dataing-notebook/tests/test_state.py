"""Tests for notebook state management."""

from unittest.mock import MagicMock

import pytest

from dataing_notebook.state import NotebookState, get_state, reset_state


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before and after each test."""
    reset_state()
    yield
    reset_state()


class TestNotebookState:
    """Tests for NotebookState class."""

    def test_initial_state(self) -> None:
        """Test initial state values."""
        state = NotebookState()
        assert state.client is None
        assert state.context is None
        assert state.bundle_cache == {}
        assert state.default_datasource_id is None
        assert state.default_platform is None
        assert state.is_attached is False

    def test_attach_context(self) -> None:
        """Test attaching a context."""
        state = NotebookState()

        # Create mock context
        mock_context = MagicMock()
        mock_context.bundle_id = "test-bundle-123"
        mock_context.bundle_hash = "abc123"
        mock_context.resolved_assets = []

        state.attach_context(mock_context)

        assert state.context == mock_context
        assert state.is_attached is True
        assert state.bundle_cache["abc123"] == mock_context
        assert len(state.history) == 1
        assert state.history[0]["action"] == "attach"

    def test_get_cached_context(self) -> None:
        """Test getting a cached context."""
        state = NotebookState()

        # Create and attach mock context
        mock_context = MagicMock()
        mock_context.bundle_hash = "hash123"
        mock_context.bundle_id = "id123"
        mock_context.resolved_assets = []

        state.attach_context(mock_context)

        # Should find cached context
        cached = state.get_cached_context("hash123")
        assert cached == mock_context

        # Should return None for unknown hash
        assert state.get_cached_context("unknown") is None

    def test_clear_context(self) -> None:
        """Test clearing context."""
        state = NotebookState()

        mock_context = MagicMock()
        mock_context.bundle_hash = "hash"
        mock_context.bundle_id = "id"
        mock_context.resolved_assets = []

        state.attach_context(mock_context)
        assert state.is_attached is True

        state.clear_context()
        assert state.context is None
        assert state.is_attached is False
        # Cache should still exist
        assert "hash" in state.bundle_cache

    def test_clear_cache(self) -> None:
        """Test clearing cache."""
        state = NotebookState()

        mock_context = MagicMock()
        mock_context.bundle_hash = "hash"
        mock_context.bundle_id = "id"
        mock_context.resolved_assets = []

        state.attach_context(mock_context)
        assert len(state.bundle_cache) == 1

        state.clear_cache()
        assert len(state.bundle_cache) == 0

    def test_history_tracking(self) -> None:
        """Test history tracking."""
        state = NotebookState()

        mock_context = MagicMock()
        mock_context.bundle_hash = "hash"
        mock_context.bundle_id = "id"
        mock_context.resolved_assets = []

        state.attach_context(mock_context)
        state.clear_context()
        state.clear_cache()

        assert len(state.history) == 3
        assert state.history[0]["action"] == "attach"
        assert state.history[1]["action"] == "clear"
        assert state.history[2]["action"] == "clear_cache"


class TestGlobalState:
    """Tests for global state functions."""

    def test_get_state_returns_singleton(self) -> None:
        """Test that get_state returns the same instance."""
        state1 = get_state()
        state2 = get_state()
        assert state1 is state2

    def test_reset_state_creates_new_instance(self) -> None:
        """Test that reset_state creates a new instance."""
        state1 = get_state()
        state1.default_platform = "postgres"

        reset_state()

        state2 = get_state()
        assert state2 is not state1
        assert state2.default_platform is None
