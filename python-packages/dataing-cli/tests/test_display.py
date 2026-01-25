"""Tests for display/output formatting module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from dataing_cli.display import (
    format_completion,
    format_event,
)
from rich.panel import Panel

if TYPE_CHECKING:
    pass


class TestFormatEvent:
    """Tests for format_event function."""

    def test_format_evidence_event_supports_true(self) -> None:
        """Test formatting evidence event that supports hypothesis."""
        event = {
            "type": "evidence",
            "hypothesis": "Upstream table issue",
            "query": "SELECT COUNT(*) FROM upstream",
            "interpretation": "No data in upstream table",
            "supports_hypothesis": True,
        }

        result = format_event(event)

        assert isinstance(result, Panel)
        assert "Evidence" in str(result.title)
        assert "green" in str(result.border_style)

    def test_format_evidence_event_supports_false(self) -> None:
        """Test formatting evidence event that refutes hypothesis."""
        event = {
            "type": "evidence",
            "hypothesis": "Data quality issue",
            "query": "SELECT COUNT(*) FROM test",
            "interpretation": "Data looks normal",
            "supports_hypothesis": False,
        }

        result = format_event(event)

        assert isinstance(result, Panel)
        assert "Evidence" in str(result.title)
        assert "red" in str(result.border_style)

    def test_format_evidence_event_supports_none(self) -> None:
        """Test formatting evidence event with no determination."""
        event = {
            "type": "evidence",
            "hypothesis": "Unknown issue",
            "query": "SELECT * FROM test",
            "interpretation": "Inconclusive",
            "supports_hypothesis": None,
        }

        result = format_event(event)

        assert isinstance(result, Panel)
        assert "Evidence" in str(result.title)
        assert "yellow" in str(result.border_style)

    def test_format_progress_event(self) -> None:
        """Test formatting progress event."""
        event = {
            "type": "progress",
            "message": "Gathering context...",
        }

        result = format_event(event)

        assert isinstance(result, Panel)
        assert "Progress" in str(result.title)

    def test_format_event_with_object(self) -> None:
        """Test formatting event as object instead of dict."""
        event = MagicMock()
        event.type = "evidence"
        event.hypothesis = "Test hypothesis"
        event.query = "SELECT 1"
        event.interpretation = "Test"
        event.supports_hypothesis = True

        result = format_event(event)

        assert isinstance(result, Panel)

    def test_format_unknown_event_type(self) -> None:
        """Test formatting unknown event type."""
        event = {"type": "unknown_type", "data": "test"}

        result = format_event(event)

        assert isinstance(result, Panel)


class TestFormatCompletion:
    """Tests for format_completion function."""

    def test_format_completion_with_root_cause(self) -> None:
        """Test formatting completion with root cause."""
        event = {
            "root_cause": "Upstream ETL failed",
            "confidence": 0.87,
        }

        result = format_completion(event)

        assert isinstance(result, Panel)
        assert "Result" in str(result.title)
        assert "green" in str(result.border_style)

    def test_format_completion_no_root_cause(self) -> None:
        """Test formatting completion without root cause."""
        event = {
            "confidence": 0.5,
        }

        result = format_completion(event)

        assert isinstance(result, Panel)
        # Should show default message
        assert "No root cause identified" in str(result.renderable)

    def test_format_completion_with_object(self) -> None:
        """Test formatting completion as object instead of dict."""
        event = MagicMock()
        event.root_cause = "Test cause"
        event.confidence = 0.9

        result = format_completion(event)

        assert isinstance(result, Panel)

    def test_format_completion_zero_confidence(self) -> None:
        """Test formatting completion with zero confidence."""
        event = {
            "root_cause": "Unknown",
            "confidence": 0,
        }

        result = format_completion(event)

        assert isinstance(result, Panel)


class TestFormatEventEdgeCases:
    """Edge case tests for format_event."""

    def test_format_evidence_no_query(self) -> None:
        """Test formatting evidence without query."""
        event = {
            "type": "evidence",
            "hypothesis": "Test",
            "interpretation": "Finding",
            "supports_hypothesis": True,
        }

        result = format_event(event)

        assert isinstance(result, Panel)

    def test_format_evidence_no_interpretation(self) -> None:
        """Test formatting evidence without interpretation."""
        event = {
            "type": "evidence",
            "hypothesis": "Test",
            "query": "SELECT 1",
            "supports_hypothesis": False,
        }

        result = format_event(event)

        assert isinstance(result, Panel)

    def test_format_progress_no_message(self) -> None:
        """Test formatting progress without message."""
        event = {
            "type": "progress",
        }

        result = format_event(event)

        assert isinstance(result, Panel)

    def test_format_event_empty_dict(self) -> None:
        """Test formatting empty event."""
        event: dict = {}

        result = format_event(event)

        assert isinstance(result, Panel)
