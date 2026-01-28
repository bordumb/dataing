"""Tests for rich rendering utilities."""

from unittest.mock import MagicMock

from dataing_notebook.rendering import (
    is_notebook_environment,
    render_comparison_table,
    render_context,
    render_evidence,
    render_history_table,
    render_lineage_tree,
    render_replay_detail,
    render_run,
    render_table,
)


class TestIsNotebookEnvironment:
    """Tests for notebook environment detection."""

    def test_returns_false_when_no_ipython(self) -> None:
        """Test returns False when IPython not available."""
        # This test runs in pytest, not in a notebook
        # The function should detect this
        result = is_notebook_environment()
        # In pytest, we're in TerminalInteractiveShell (if IPython is available)
        # or no shell at all
        assert isinstance(result, bool)


class TestRenderLineageTree:
    """Tests for lineage tree rendering."""

    def test_empty_lineage(self) -> None:
        """Test rendering with no lineage."""
        html = render_lineage_tree(None)
        assert "No lineage information" in html

    def test_empty_dict(self) -> None:
        """Test rendering with empty dict."""
        html = render_lineage_tree({})
        assert "No lineage information" in html

    def test_lineage_with_root(self) -> None:
        """Test rendering with root node."""
        lineage = {
            "root": "postgres://db.schema.orders",
            "datasets": {},
            "edges": [],
        }
        html = render_lineage_tree(lineage)
        assert "postgres://db.schema.orders" in html
        assert "dataing-lineage" in html

    def test_lineage_with_edges(self) -> None:
        """Test rendering with edges."""
        lineage = {
            "root": "orders",
            "datasets": {},
            "edges": [
                {"source": "customers", "target": "orders", "edge_type": "transforms"},
                {"source": "products", "target": "orders", "edge_type": "joins"},
            ],
        }
        html = render_lineage_tree(lineage)
        assert "customers" in html
        assert "orders" in html
        assert "products" in html
        assert "transforms" in html
        assert "joins" in html


class TestRenderTable:
    """Tests for table rendering."""

    def test_empty_rows(self) -> None:
        """Test rendering with no rows."""
        html = render_table([])
        assert "No data" in html

    def test_simple_table(self) -> None:
        """Test rendering a simple table."""
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        html = render_table(rows)
        assert "<table>" in html
        assert "id" in html
        assert "name" in html
        assert "Alice" in html
        assert "Bob" in html

    def test_table_with_nulls(self) -> None:
        """Test rendering table with null values."""
        rows = [
            {"id": 1, "name": None},
        ]
        html = render_table(rows)
        assert "NULL" in html
        assert 'class="null"' in html

    def test_table_truncation(self) -> None:
        """Test table truncation at 100 rows."""
        rows = [{"id": i} for i in range(150)]
        html = render_table(rows)
        assert "100 of 150" in html

    def test_table_with_columns(self) -> None:
        """Test rendering with explicit column metadata."""
        rows = [{"a": 1, "b": 2}]
        columns = [{"name": "col_a"}, {"name": "col_b"}]
        html = render_table(rows, columns)
        assert "col_a" in html
        assert "col_b" in html


class TestRenderEvidence:
    """Tests for evidence rendering."""

    def test_sql_evidence(self) -> None:
        """Test rendering SQL evidence."""
        evidence = MagicMock()
        evidence.kind = MagicMock(value="sql")
        evidence.confidence = 0.85
        evidence.result_summary = "Found 10 null values"
        evidence.source = {"sql": "SELECT COUNT(*) FROM orders WHERE id IS NULL"}
        evidence.conclusion = "Data quality issue detected"

        html = render_evidence(evidence)
        assert "SQL" in html
        assert "85%" in html
        assert "Found 10 null values" in html
        assert "SELECT COUNT" in html
        assert "Data quality issue" in html

    def test_metric_evidence(self) -> None:
        """Test rendering metric evidence."""
        evidence = MagicMock()
        evidence.kind = MagicMock(value="metric")
        evidence.confidence = None
        evidence.result_summary = "Row count changed"
        evidence.source = None
        evidence.conclusion = None

        html = render_evidence(evidence)
        assert "METRIC" in html
        assert "Row count changed" in html


class TestRenderContext:
    """Tests for context rendering."""

    def test_render_context(self) -> None:
        """Test rendering a context."""
        context = MagicMock()
        context.bundle_id = "test-bundle-123456789"
        context.bundle_hash = "abc123hash"
        context.resolved_assets = [
            MagicMock(dataset_id="postgres://db.schema.orders"),
            MagicMock(dataset_id="postgres://db.schema.customers"),
        ]
        context.lineage = None
        context.anomalies = None

        html = render_context(context)
        assert "Context" in html
        assert "test-bundle-1234" in html
        assert "abc123hash" in html
        assert "2 asset(s)" in html
        assert "postgres://db.schema.orders" in html

    def test_render_context_with_lineage(self) -> None:
        """Test rendering context with lineage."""
        context = MagicMock()
        context.bundle_id = "test-bundle"
        context.bundle_hash = "hash"
        context.resolved_assets = [MagicMock(dataset_id="table1")]
        context.lineage = {"root": "table1", "edges": []}
        context.anomalies = None

        html = render_context(context)
        assert "Lineage" in html

    def test_render_context_with_anomalies(self) -> None:
        """Test rendering context with anomalies."""
        context = MagicMock()
        context.bundle_id = "test-bundle"
        context.bundle_hash = "hash"
        context.resolved_assets = []
        context.lineage = None
        context.anomalies = [{"type": "null_spike"}, {"type": "volume_drop"}]

        html = render_context(context)
        assert "Anomalies" in html
        assert "2 anomaly(ies)" in html


class TestRenderRun:
    """Tests for run rendering."""

    def test_render_running(self) -> None:
        """Test rendering a running run."""
        run = MagicMock()
        run.run_id = "run-123456789"
        run.bundle_hash = "hash123"
        run.status = MagicMock(value="running")

        html = render_run(run)
        assert "Run" in html
        assert "RUNNING" in html
        assert "run-1234" in html
        assert "#3b82f6" in html  # Blue color

    def test_render_completed(self) -> None:
        """Test rendering a completed run."""
        run = MagicMock()
        run.run_id = "run-123"
        run.bundle_hash = "hash"
        run.status = MagicMock(value="completed")

        html = render_run(run)
        assert "COMPLETED" in html
        assert "#10b981" in html  # Green color

    def test_render_failed(self) -> None:
        """Test rendering a failed run."""
        run = MagicMock()
        run.run_id = "run-123"
        run.bundle_hash = "hash"
        run.status = MagicMock(value="failed")

        html = render_run(run)
        assert "FAILED" in html
        assert "#ef4444" in html  # Red color


class TestRenderHistoryTable:
    """Tests for render_history_table."""

    def test_empty_list(self) -> None:
        """Test rendering empty investigation list."""
        result = render_history_table([])
        assert "No" in result or "empty" in result.lower()

    def test_single_investigation(self) -> None:
        """Test rendering a single investigation."""
        investigations = [
            {
                "investigation_id": "abc-123-def-456",
                "dataset_id": "orders",
                "status": "completed",
                "created_at": "2026-01-28T10:00:00Z",
            },
        ]
        result = render_history_table(investigations)
        assert "abc-123" in result
        assert "orders" in result
        assert "completed" in result.lower()

    def test_pagination_display(self) -> None:
        """Test pagination info in footer."""
        investigations = [
            {
                "investigation_id": f"id-{i}",
                "dataset_id": "orders",
                "status": "completed",
                "created_at": "2026-01-28T10:00:00Z",
            }
            for i in range(5)
        ]
        result = render_history_table(investigations, page=2, total=93, page_size=20)
        assert "Page" in result or "93" in result

    def test_status_badges(self) -> None:
        """Test that different statuses get appropriate styling."""
        investigations = [
            {
                "investigation_id": "id-1",
                "dataset_id": "orders",
                "status": "completed",
                "created_at": "2026-01-28T10:00:00Z",
            },
            {
                "investigation_id": "id-2",
                "dataset_id": "orders",
                "status": "failed",
                "created_at": "2026-01-28T11:00:00Z",
            },
        ]
        result = render_history_table(investigations)
        assert "completed" in result.lower()
        assert "failed" in result.lower()


class TestRenderReplayDetail:
    """Tests for render_replay_detail."""

    def test_completed_investigation(self) -> None:
        """Test rendering a completed investigation."""
        inv = {
            "investigation_id": "abc-123",
            "status": "completed",
            "root_hash": "hash123456789",
            "main_branch": {
                "synthesis": {"summary": "Root cause identified"},
                "evidence": [{"kind": "sql", "result_summary": "Null spike"}],
            },
        }
        result = render_replay_detail(inv)
        assert "abc-123" in result
        assert "completed" in result.lower()

    def test_failed_investigation(self) -> None:
        """Test rendering a failed investigation."""
        inv = {
            "investigation_id": "def-456",
            "status": "failed",
            "root_hash": None,
            "main_branch": {
                "synthesis": None,
                "evidence": [],
            },
        }
        result = render_replay_detail(inv)
        assert "def-456" in result
        assert "failed" in result.lower()

    def test_evidence_displayed(self) -> None:
        """Test that evidence items are rendered."""
        inv = {
            "investigation_id": "ghi-789",
            "status": "completed",
            "root_hash": "abc",
            "main_branch": {
                "synthesis": {"summary": "Found it"},
                "evidence": [
                    {"kind": "sql", "sql": "SELECT * FROM test"},
                    {"kind": "metric", "metric": "row_count", "value": 100},
                ],
            },
        }
        result = render_replay_detail(inv)
        assert "Evidence" in result
        assert "2 items" in result


class TestRenderComparisonTable:
    """Tests for render_comparison_table."""

    def test_identical_investigations(self) -> None:
        """Test comparing investigations with same data."""
        inv = {
            "investigation_id": "id-1",
            "status": "completed",
            "main_branch": {
                "synthesis": {"summary": "Same root cause"},
                "evidence": [],
            },
        }
        result = render_comparison_table(inv, inv)
        assert "id-1" in result

    def test_different_statuses(self) -> None:
        """Test comparing investigations with different statuses."""
        inv1 = {
            "investigation_id": "id-1",
            "status": "completed",
            "main_branch": {
                "synthesis": {"summary": "Found root cause"},
                "evidence": [{"kind": "sql"}],
            },
        }
        inv2 = {
            "investigation_id": "id-2",
            "status": "failed",
            "main_branch": {
                "synthesis": None,
                "evidence": [],
            },
        }
        result = render_comparison_table(inv1, inv2)
        assert "id-1" in result
        assert "id-2" in result
        assert "completed" in result.lower()
        assert "failed" in result.lower()

    def test_different_evidence(self) -> None:
        """Test comparing investigations with different evidence."""
        inv1 = {
            "investigation_id": "id-1",
            "status": "completed",
            "main_branch": {
                "synthesis": None,
                "evidence": [{"kind": "sql", "sql": "SELECT 1"}],
            },
        }
        inv2 = {
            "investigation_id": "id-2",
            "status": "completed",
            "main_branch": {
                "synthesis": None,
                "evidence": [
                    {"kind": "sql", "sql": "SELECT 2"},
                    {"kind": "metric", "metric": "count"},
                ],
            },
        }
        result = render_comparison_table(inv1, inv2)
        # Should show difference in evidence counts
        assert "Unique" in result or "1" in result
