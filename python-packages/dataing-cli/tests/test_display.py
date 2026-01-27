"""Tests for display/output formatting module."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from dataing_cli.display import (
    format_completion,
    format_event,
    format_evidence_item,
    format_hypothesis,
    format_query,
    format_synthesis,
    format_timestamp,
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


class TestFormatTimestamp:
    """Tests for format_timestamp function."""

    def test_format_timestamp_seconds(self) -> None:
        """Test formatting elapsed time in seconds."""
        start_time = time.time() - 5  # 5 seconds ago
        result = format_timestamp(start_time)
        assert result == "[00:05]"

    def test_format_timestamp_minute(self) -> None:
        """Test formatting elapsed time in minutes."""
        start_time = time.time() - 60  # 1 minute ago
        result = format_timestamp(start_time)
        assert result == "[01:00]"

    def test_format_timestamp_minutes_seconds(self) -> None:
        """Test formatting elapsed time with minutes and seconds."""
        start_time = time.time() - 95  # 1 min 35 sec ago
        result = format_timestamp(start_time)
        assert result == "[01:35]"

    def test_format_timestamp_zero(self) -> None:
        """Test formatting zero elapsed time."""
        start_time = time.time()
        result = format_timestamp(start_time)
        assert result == "[00:00]"


class TestFormatHypothesis:
    """Tests for format_hypothesis function."""

    def test_format_hypothesis_basic(self) -> None:
        """Test formatting a hypothesis event."""
        event = {"data": {"hypothesis": "The data has null values"}}
        result = format_hypothesis(event, 1, "[00:05]")

        assert isinstance(result, Panel)
        assert "[00:05] Hypothesis #1" in str(result.title)
        assert "blue" in str(result.border_style)

    def test_format_hypothesis_number_increment(self) -> None:
        """Test hypothesis numbering."""
        event = {"data": {"hypothesis": "Another hypothesis"}}
        result = format_hypothesis(event, 3, "[00:10]")

        assert "Hypothesis #3" in str(result.title)

    def test_format_hypothesis_missing_data(self) -> None:
        """Test hypothesis with missing data."""
        event = {}
        result = format_hypothesis(event, 1, "[00:01]")

        assert isinstance(result, Panel)
        assert "blue" in str(result.border_style)


class TestFormatQuery:
    """Tests for format_query function."""

    def test_format_query_basic(self) -> None:
        """Test formatting a query event."""
        event = {"data": {"query": "SELECT * FROM orders WHERE id IS NULL"}}
        result = format_query(event, "[00:05]")

        assert isinstance(result, Panel)
        assert "[00:05] Executing Query" in str(result.title)
        assert "yellow" in str(result.border_style)

    def test_format_query_long_sql_truncation(self) -> None:
        """Test that long SQL is truncated."""
        long_sql = "\n".join(["SELECT col FROM table"] * 25)
        event = {"data": {"query": long_sql}}
        result = format_query(event, "[00:05]")

        assert isinstance(result, Panel)
        # The SQL should be truncated (panel created without error)
        assert "yellow" in str(result.border_style)

    def test_format_query_missing_query(self) -> None:
        """Test query formatting with missing query field."""
        event = {"data": {}}
        result = format_query(event, "[00:05]")

        assert isinstance(result, Panel)


class TestFormatEvidenceItem:
    """Tests for format_evidence_item function."""

    def test_format_evidence_supports(self) -> None:
        """Test formatting evidence that supports hypothesis."""
        event = {
            "data": {
                "supports_hypothesis": True,
                "interpretation": "Found 500 null rows",
                "confidence": 0.85,
            }
        }
        result = format_evidence_item(event, "[00:15]")

        assert isinstance(result, Panel)
        assert "Supports" in str(result.title)
        assert "green" in str(result.border_style)

    def test_format_evidence_refutes(self) -> None:
        """Test formatting evidence that refutes hypothesis."""
        event = {
            "data": {
                "supports_hypothesis": False,
                "interpretation": "No nulls found",
            }
        }
        result = format_evidence_item(event, "[00:20]")

        assert isinstance(result, Panel)
        assert "Refutes" in str(result.title)
        assert "red" in str(result.border_style)

    def test_format_evidence_inconclusive(self) -> None:
        """Test formatting inconclusive evidence."""
        event = {"data": {"interpretation": "Results unclear"}}
        result = format_evidence_item(event, "[00:25]")

        assert isinstance(result, Panel)
        assert "Inconclusive" in str(result.title)
        assert "yellow" in str(result.border_style)

    def test_format_evidence_missing_data(self) -> None:
        """Test evidence formatting with missing data."""
        event = {}
        result = format_evidence_item(event, "[00:30]")

        assert isinstance(result, Panel)


class TestFormatSynthesis:
    """Tests for format_synthesis function."""

    def test_format_synthesis_basic(self) -> None:
        """Test formatting synthesis event."""
        event = {
            "data": {
                "root_cause": "Data pipeline failed at 2am",
                "confidence": 0.9,
                "recommendations": [
                    {"text": "Fix the pipeline schedule"},
                    {"text": "Add monitoring"},
                ],
            }
        }
        result = format_synthesis(event, "[01:00]")

        assert isinstance(result, Panel)
        assert "Synthesis" in str(result.title)
        assert "cyan" in str(result.border_style)

    def test_format_synthesis_no_recommendations(self) -> None:
        """Test synthesis without recommendations."""
        event = {
            "data": {
                "root_cause": "Unknown cause",
                "confidence": 0.5,
            }
        }
        result = format_synthesis(event, "[01:00]")

        assert isinstance(result, Panel)
        assert "cyan" in str(result.border_style)

    def test_format_synthesis_missing_data(self) -> None:
        """Test synthesis with missing data."""
        event = {}
        result = format_synthesis(event, "[01:00]")

        assert isinstance(result, Panel)
        assert "cyan" in str(result.border_style)


class TestTimelineFormattersEdgeCases:
    """Edge case tests for timeline formatters."""

    def test_all_formatters_handle_none_event(self) -> None:
        """Test that formatters handle None-like events gracefully."""
        # These should not raise exceptions
        format_hypothesis({}, 1, "[00:00]")
        format_query({}, "[00:00]")
        format_evidence_item({}, "[00:00]")
        format_synthesis({}, "[00:00]")

    def test_formatters_with_mock_objects(self) -> None:
        """Test formatters work with mock objects."""
        mock_event = MagicMock()
        mock_event.data = {"hypothesis": "Test", "confidence": 0.8}

        result = format_hypothesis(mock_event, 1, "[00:05]")
        assert isinstance(result, Panel)

    def test_evidence_with_query_snippet(self) -> None:
        """Test evidence formatting includes query snippet."""
        event = {
            "data": {
                "supports_hypothesis": True,
                "interpretation": "Found issue",
                "query": "SELECT * FROM orders",
            }
        }
        result = format_evidence_item(event, "[00:15]")

        assert isinstance(result, Panel)
