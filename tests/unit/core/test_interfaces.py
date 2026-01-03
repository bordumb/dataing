"""Unit tests for interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from dataing.core.interfaces import (
    ContextEngine,
    DatabaseAdapter,
    LLMClient,
    LineageClient,
)


class TestDatabaseAdapterInterface:
    """Tests for DatabaseAdapter interface."""

    def test_is_protocol(self) -> None:
        """Test that DatabaseAdapter is a Protocol."""
        assert issubclass(DatabaseAdapter, Protocol)

    def test_is_runtime_checkable(self) -> None:
        """Test that DatabaseAdapter is runtime checkable."""
        # Runtime checkable protocols can be used with isinstance
        assert hasattr(DatabaseAdapter, "__protocol_attrs__") or hasattr(
            DatabaseAdapter, "_is_runtime_protocol"
        )

    def test_has_required_methods(self) -> None:
        """Test that interface has required methods."""
        assert hasattr(DatabaseAdapter, "execute_query")
        assert hasattr(DatabaseAdapter, "get_schema")


class TestLLMClientInterface:
    """Tests for LLMClient interface."""

    def test_is_protocol(self) -> None:
        """Test that LLMClient is a Protocol."""
        assert issubclass(LLMClient, Protocol)

    def test_has_required_methods(self) -> None:
        """Test that interface has required methods."""
        assert hasattr(LLMClient, "generate_hypotheses")
        assert hasattr(LLMClient, "generate_query")
        assert hasattr(LLMClient, "interpret_evidence")
        assert hasattr(LLMClient, "synthesize_findings")


class TestContextEngineInterface:
    """Tests for ContextEngine interface."""

    def test_is_protocol(self) -> None:
        """Test that ContextEngine is a Protocol."""
        assert issubclass(ContextEngine, Protocol)

    def test_has_required_methods(self) -> None:
        """Test that interface has required methods."""
        assert hasattr(ContextEngine, "gather")


class TestLineageClientInterface:
    """Tests for LineageClient interface."""

    def test_is_protocol(self) -> None:
        """Test that LineageClient is a Protocol."""
        assert issubclass(LineageClient, Protocol)

    def test_has_required_methods(self) -> None:
        """Test that interface has required methods."""
        assert hasattr(LineageClient, "get_lineage")
