"""Unit tests for SDK snapshot diff functionality."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dataing.sdk.diff import (
    DataFrameDiff,
    EvidenceDiff,
    HypothesisDiff,
    SchemaDiff,
    SnapshotDiff,
    SynthesisDiff,
    compare_snapshots,
)


class TestSchemaDiff:
    """Tests for SchemaDiff dataclass."""

    def test_empty_schema_diff(self) -> None:
        """Test empty schema diff."""
        diff = SchemaDiff()
        assert diff.is_empty()
        assert diff.summary() == "No changes"

    def test_schema_diff_with_added_tables(self) -> None:
        """Test schema diff with added tables."""
        diff = SchemaDiff(added_tables=["orders", "customers"])
        assert not diff.is_empty()
        assert "+2 tables" in diff.summary()

    def test_schema_diff_with_removed_columns(self) -> None:
        """Test schema diff with removed columns."""
        diff = SchemaDiff(removed_columns={"orders": ["old_col1", "old_col2"]})
        assert not diff.is_empty()
        assert "-2 columns" in diff.summary()

    def test_schema_diff_with_type_changes(self) -> None:
        """Test schema diff with type changes."""
        diff = SchemaDiff(type_changes={"orders": {"amount": ("integer", "decimal")}})
        assert not diff.is_empty()
        assert "~1 type changes" in diff.summary()


class TestHypothesisDiff:
    """Tests for HypothesisDiff dataclass."""

    def test_empty_hypothesis_diff(self) -> None:
        """Test empty hypothesis diff."""
        diff = HypothesisDiff()
        assert diff.is_empty()
        assert diff.summary() == "No changes"

    def test_hypothesis_diff_with_added(self) -> None:
        """Test hypothesis diff with added hypotheses."""
        diff = HypothesisDiff(added=[{"id": "h1"}, {"id": "h2"}])
        assert not diff.is_empty()
        assert "+2 hypotheses" in diff.summary()

    def test_hypothesis_diff_with_status_changes(self) -> None:
        """Test hypothesis diff with status changes."""
        diff = HypothesisDiff(
            status_changed=[{"id": "h1", "old_status": "pending", "new_status": "supported"}]
        )
        assert not diff.is_empty()
        assert "~1 status changes" in diff.summary()


class TestEvidenceDiff:
    """Tests for EvidenceDiff dataclass."""

    def test_empty_evidence_diff(self) -> None:
        """Test empty evidence diff."""
        diff = EvidenceDiff()
        assert diff.is_empty()
        assert diff.summary() == "No changes"

    def test_evidence_diff_with_added(self) -> None:
        """Test evidence diff with added evidence."""
        diff = EvidenceDiff(added=[{"id": "e1"}, {"id": "e2"}, {"id": "e3"}])
        assert not diff.is_empty()
        assert "+3 evidence items" in diff.summary()


class TestSynthesisDiff:
    """Tests for SynthesisDiff dataclass."""

    def test_empty_synthesis_diff(self) -> None:
        """Test empty synthesis diff."""
        diff = SynthesisDiff()
        assert diff.is_empty()
        assert diff.summary() == "No changes"

    def test_synthesis_diff_with_root_cause_change(self) -> None:
        """Test synthesis diff with root cause change."""
        diff = SynthesisDiff(
            root_cause_changed=True,
            before={"root_cause": "ETL failure"},
            after={"root_cause": "Schema migration"},
        )
        assert not diff.is_empty()
        assert "root_cause changed" in diff.summary()

    def test_synthesis_diff_with_confidence_change(self) -> None:
        """Test synthesis diff with confidence change."""
        diff = SynthesisDiff(confidence_change=0.15)
        assert not diff.is_empty()
        assert "+15" in diff.summary() or "+0.15" in diff.summary()


class TestDataFrameDiff:
    """Tests for DataFrameDiff dataclass."""

    def test_empty_dataframe_diff(self) -> None:
        """Test empty DataFrame diff."""
        diff = DataFrameDiff(table_name="orders")
        assert diff.is_empty()
        assert diff.summary() == "No changes"

    def test_dataframe_diff_with_row_changes(self) -> None:
        """Test DataFrame diff with row changes."""
        diff = DataFrameDiff(table_name="orders", rows_added=100, rows_removed=5)
        assert not diff.is_empty()
        assert "+100 rows" in diff.summary()
        assert "-5 rows" in diff.summary()

    def test_dataframe_diff_with_value_changes(self) -> None:
        """Test DataFrame diff with value changes."""
        diff = DataFrameDiff(table_name="orders", values_changed=42)
        assert not diff.is_empty()
        assert "~42 value changes" in diff.summary()


class TestSnapshotDiff:
    """Tests for SnapshotDiff dataclass."""

    def test_empty_snapshot_diff(self) -> None:
        """Test empty snapshot diff summary."""
        diff = SnapshotDiff(
            before_checkpoint="start",
            after_checkpoint="complete",
            before_investigation_id="abc-123",
            after_investigation_id="abc-123",
        )
        assert "start -> complete" in diff.summary()
        assert "No changes detected" in diff.summary()

    def test_snapshot_diff_with_changes(self) -> None:
        """Test snapshot diff with various changes."""
        diff = SnapshotDiff(
            before_checkpoint="start",
            after_checkpoint="complete",
            before_investigation_id="abc-123",
            after_investigation_id="abc-123",
            hypotheses=HypothesisDiff(added=[{"id": "h1"}]),
            evidence=EvidenceDiff(added=[{"id": "e1"}, {"id": "e2"}]),
        )
        summary = diff.summary()
        assert "Hypotheses: +1 hypotheses" in summary
        assert "Evidence: +2 evidence items" in summary

    def test_to_markdown(self) -> None:
        """Test markdown export."""
        diff = SnapshotDiff(
            before_checkpoint="start",
            after_checkpoint="complete",
            before_investigation_id="abc-123",
            after_investigation_id="abc-123",
            hypotheses=HypothesisDiff(added=[{"id": "h1", "title": "Test hypothesis"}]),
        )
        md = diff.to_markdown()
        assert "# Snapshot Diff" in md
        assert "## Hypothesis Changes" in md
        assert "Test hypothesis" in md

    def test_to_html(self) -> None:
        """Test HTML export."""
        diff = SnapshotDiff(
            before_checkpoint="start",
            after_checkpoint="complete",
            before_investigation_id="abc-123",
            after_investigation_id="abc-123",
            schema=SchemaDiff(added_tables=["orders"]),
        )
        html = diff.to_html()
        assert "dataing-diff" in html
        assert "Schema Changes" in html
        assert "orders" in html

    def test_repr_html(self) -> None:
        """Test Jupyter HTML representation."""
        diff = SnapshotDiff(
            before_checkpoint="start",
            after_checkpoint="complete",
            before_investigation_id="abc-123",
            after_investigation_id="abc-123",
        )
        html = diff._repr_html_()
        assert "<div class='dataing-diff'>" in html


class TestCompareSnapshots:
    """Tests for compare_snapshots function."""

    @pytest.fixture
    def mock_before_state(self) -> MagicMock:
        """Create mock before state."""
        state = MagicMock()
        state.checkpoint = "start"
        state.investigation_id = "abc-123"
        state.hypotheses = []
        state.evidence = []
        state.synthesis = None
        state.dataframes = {}

        # Mock schema
        state.schema = MagicMock()
        state.schema.tables = {}

        return state

    @pytest.fixture
    def mock_after_state(self) -> MagicMock:
        """Create mock after state."""
        state = MagicMock()
        state.checkpoint = "complete"
        state.investigation_id = "abc-123"
        state.hypotheses = [{"id": "h1", "title": "Test", "status": "supported"}]
        state.evidence = [{"id": "e1", "hypothesis_id": "h1", "supports": True}]
        state.synthesis = {"root_cause": "ETL failure", "confidence": 0.9}
        state.dataframes = {}

        # Mock schema
        state.schema = MagicMock()
        state.schema.tables = {}

        return state

    def test_compare_empty_snapshots(
        self, mock_before_state: MagicMock, mock_after_state: MagicMock
    ) -> None:
        """Test comparing snapshots with no common data."""
        mock_before_state.hypotheses = []
        mock_before_state.evidence = []
        mock_before_state.synthesis = None
        mock_after_state.hypotheses = []
        mock_after_state.evidence = []
        mock_after_state.synthesis = None

        diff = compare_snapshots(mock_before_state, mock_after_state)

        assert diff.before_checkpoint == "start"
        assert diff.after_checkpoint == "complete"
        assert diff.hypotheses.is_empty()
        assert diff.evidence.is_empty()
        assert diff.synthesis.is_empty()

    def test_compare_with_added_hypotheses(
        self, mock_before_state: MagicMock, mock_after_state: MagicMock
    ) -> None:
        """Test comparing snapshots with added hypotheses."""
        mock_before_state.hypotheses = []
        mock_after_state.hypotheses = [{"id": "h1", "title": "Test"}]

        diff = compare_snapshots(mock_before_state, mock_after_state)

        assert len(diff.hypotheses.added) == 1
        assert diff.hypotheses.added[0]["id"] == "h1"

    def test_compare_with_hypothesis_status_change(
        self, mock_before_state: MagicMock, mock_after_state: MagicMock
    ) -> None:
        """Test comparing snapshots with hypothesis status change."""
        mock_before_state.hypotheses = [{"id": "h1", "status": "pending"}]
        mock_after_state.hypotheses = [{"id": "h1", "status": "supported"}]

        diff = compare_snapshots(mock_before_state, mock_after_state)

        assert len(diff.hypotheses.status_changed) == 1
        assert diff.hypotheses.status_changed[0]["old_status"] == "pending"
        assert diff.hypotheses.status_changed[0]["new_status"] == "supported"

    def test_compare_with_added_evidence(
        self, mock_before_state: MagicMock, mock_after_state: MagicMock
    ) -> None:
        """Test comparing snapshots with added evidence."""
        mock_before_state.evidence = []
        mock_after_state.evidence = [{"id": "e1"}, {"id": "e2"}]

        diff = compare_snapshots(mock_before_state, mock_after_state)

        assert len(diff.evidence.added) == 2

    def test_compare_with_synthesis_change(
        self, mock_before_state: MagicMock, mock_after_state: MagicMock
    ) -> None:
        """Test comparing snapshots with synthesis change."""
        mock_before_state.synthesis = {"root_cause": "Unknown", "confidence": 0.3}
        mock_after_state.synthesis = {"root_cause": "ETL failure", "confidence": 0.9}

        diff = compare_snapshots(mock_before_state, mock_after_state)

        assert diff.synthesis.root_cause_changed
        assert diff.synthesis.confidence_change == pytest.approx(0.6, rel=0.01)

    def test_compare_schema_added_table(
        self, mock_before_state: MagicMock, mock_after_state: MagicMock
    ) -> None:
        """Test comparing schemas with added table."""
        mock_before_state.schema.tables = {}
        mock_after_state.schema.tables = {"orders": MagicMock(columns=[])}

        diff = compare_snapshots(mock_before_state, mock_after_state)

        assert "orders" in diff.schema.added_tables

    def test_compare_schema_removed_table(
        self, mock_before_state: MagicMock, mock_after_state: MagicMock
    ) -> None:
        """Test comparing schemas with removed table."""
        mock_before_state.schema.tables = {"legacy": MagicMock(columns=[])}
        mock_after_state.schema.tables = {}

        diff = compare_snapshots(mock_before_state, mock_after_state)

        assert "legacy" in diff.schema.removed_tables

    def test_compare_schema_column_changes(
        self, mock_before_state: MagicMock, mock_after_state: MagicMock
    ) -> None:
        """Test comparing schemas with column changes."""
        before_col = MagicMock()
        before_col.name = "id"
        before_col.data_type = "integer"

        after_col1 = MagicMock()
        after_col1.name = "id"
        after_col1.data_type = "integer"

        after_col2 = MagicMock()
        after_col2.name = "new_col"
        after_col2.data_type = "varchar"

        before_table = MagicMock()
        before_table.columns = [before_col]

        after_table = MagicMock()
        after_table.columns = [after_col1, after_col2]

        mock_before_state.schema.tables = {"orders": before_table}
        mock_after_state.schema.tables = {"orders": after_table}

        diff = compare_snapshots(mock_before_state, mock_after_state)

        assert "orders" in diff.schema.added_columns
        assert "new_col" in diff.schema.added_columns["orders"]
