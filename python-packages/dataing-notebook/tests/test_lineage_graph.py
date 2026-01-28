"""Tests for lineage graph visualization."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dataing_notebook.lineage_graph import (
    _render_ascii_fallback,
    _render_dataset_details,
    _render_job_details,
    export_lineage_graph,
    is_widget_environment,
    lineage_to_cytoscape_elements,
    render_lineage_graph,
)

# --- Fixtures ---


@pytest.fixture
def sample_lineage() -> dict[str, Any]:
    """Sample lineage API response for testing."""
    return {
        "root": "orders",
        "datasets": {
            "orders": {
                "type": "table",
                "platform": "postgres",
                "description": "Order transactions",
                "tags": ["production", "pii"],
                "owners": ["data-team"],
                "schema": [{"name": "id"}, {"name": "customer_id"}, {"name": "total"}],
            },
            "raw_orders": {
                "type": "source",
                "platform": "postgres",
            },
            "customers": {
                "type": "table",
                "platform": "postgres",
            },
            "order_metrics": {
                "type": "view",
                "platform": "postgres",
            },
        },
        "edges": [
            {"source": "raw_orders", "target": "orders", "edge_type": "transforms"},
            {"source": "orders", "target": "order_metrics", "edge_type": "transforms"},
            {"source": "customers", "target": "orders", "edge_type": "joins"},
        ],
        "jobs": {
            "dbt_run_orders": {
                "type": "transformation",
                "inputs": ["raw_orders"],
                "outputs": ["orders"],
                "source_url": "https://github.com/example/repo/models/orders.sql",
            },
        },
    }


@pytest.fixture
def empty_lineage() -> dict[str, Any]:
    """Empty lineage response."""
    return {"root": "", "datasets": {}, "edges": [], "jobs": {}}


def _get_nodes(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract nodes from elements list."""
    return [e for e in elements if "source" not in e.get("data", {})]


def _get_edges(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract edges from elements list."""
    return [e for e in elements if "source" in e.get("data", {})]


# --- Element Conversion ---


class TestLineageToCytoscapeElements:
    """Tests for lineage_to_cytoscape_elements()."""

    def test_produces_nodes_and_edges(self, sample_lineage: dict[str, Any]) -> None:
        """Test that conversion produces correct node and edge counts."""
        elements = lineage_to_cytoscape_elements(sample_lineage, depth=3, direction="both")
        nodes = _get_nodes(elements)
        edges = _get_edges(elements)
        # 4 datasets (jobs only appear if referenced in edges)
        assert len(nodes) == 4
        assert len(edges) == 3

    def test_root_node_has_highlight_class(self, sample_lineage: dict[str, Any]) -> None:
        """Test that root node receives the 'root' CSS class."""
        elements = lineage_to_cytoscape_elements(sample_lineage, depth=3, direction="both")
        nodes = _get_nodes(elements)
        root_nodes = [n for n in nodes if n["data"]["id"] == "orders"]
        assert len(root_nodes) == 1
        assert "root" in root_nodes[0]["classes"]

    def test_job_nodes_have_job_class(self) -> None:
        """Test that job nodes receive the 'job' CSS class."""
        # Create lineage where job appears in edges
        lineage_with_job: dict[str, Any] = {
            "root": "orders",
            "datasets": {"orders": {"type": "table"}, "raw_orders": {"type": "source"}},
            "edges": [
                {"source": "raw_orders", "target": "dbt_job"},
                {"source": "dbt_job", "target": "orders"},
            ],
            "jobs": {"dbt_job": {"type": "transformation"}},
        }
        elements = lineage_to_cytoscape_elements(lineage_with_job, depth=3, direction="both")
        nodes = _get_nodes(elements)
        job_nodes = [n for n in nodes if n["data"]["node_type"] == "job"]
        assert len(job_nodes) == 1
        assert "job" in job_nodes[0]["classes"]

    def test_empty_lineage_returns_empty_list(self, empty_lineage: dict[str, Any]) -> None:
        """Test that empty lineage data returns empty list."""
        elements = lineage_to_cytoscape_elements(empty_lineage)
        assert elements == []

    def test_depth_1_limits_to_immediate_neighbors(self, sample_lineage: dict[str, Any]) -> None:
        """Test that depth=1 only includes nodes 1 hop from root."""
        elements = lineage_to_cytoscape_elements(sample_lineage, depth=1, direction="both")
        nodes = _get_nodes(elements)
        node_ids = {n["data"]["id"] for n in nodes}
        # Root + immediate neighbors (raw_orders, customers, order_metrics)
        assert "orders" in node_ids
        assert "raw_orders" in node_ids
        assert "customers" in node_ids
        assert "order_metrics" in node_ids
        # dbt_run_orders is not directly connected to root via edges
        assert "dbt_run_orders" not in node_ids

    def test_direction_upstream_only(self, sample_lineage: dict[str, Any]) -> None:
        """Test upstream direction only shows parent nodes."""
        elements = lineage_to_cytoscape_elements(sample_lineage, depth=2, direction="upstream")
        nodes = _get_nodes(elements)
        node_ids = {n["data"]["id"] for n in nodes}
        assert "orders" in node_ids
        assert "raw_orders" in node_ids
        assert "customers" in node_ids
        # order_metrics is downstream, should not appear
        assert "order_metrics" not in node_ids

    def test_direction_downstream_only(self, sample_lineage: dict[str, Any]) -> None:
        """Test downstream direction only shows child nodes."""
        elements = lineage_to_cytoscape_elements(sample_lineage, depth=2, direction="downstream")
        nodes = _get_nodes(elements)
        node_ids = {n["data"]["id"] for n in nodes}
        assert "orders" in node_ids
        assert "order_metrics" in node_ids
        # raw_orders and customers are upstream, should not appear
        assert "raw_orders" not in node_ids
        assert "customers" not in node_ids

    def test_direction_both_includes_all_reachable(self, sample_lineage: dict[str, Any]) -> None:
        """Test both direction includes all reachable nodes."""
        elements = lineage_to_cytoscape_elements(sample_lineage, depth=3, direction="both")
        nodes = _get_nodes(elements)
        node_ids = {n["data"]["id"] for n in nodes}
        assert "orders" in node_ids
        assert "raw_orders" in node_ids
        assert "customers" in node_ids
        assert "order_metrics" in node_ids

    def test_node_label_uses_short_name(self) -> None:
        """Test that qualified names are shortened for labels."""
        lineage = {
            "root": "db.schema.orders",
            "datasets": {"db.schema.orders": {"type": "table"}},
            "edges": [],
            "jobs": {},
        }
        elements = lineage_to_cytoscape_elements(lineage, depth=1, direction="both")
        nodes = _get_nodes(elements)
        assert nodes[0]["data"]["label"] == "orders"

    def test_dataset_details_attached_to_node(self, sample_lineage: dict[str, Any]) -> None:
        """Test that dataset details are included in node data."""
        elements = lineage_to_cytoscape_elements(sample_lineage, depth=3, direction="both")
        nodes = _get_nodes(elements)
        orders_node = [n for n in nodes if n["data"]["id"] == "orders"][0]
        assert "details" in orders_node["data"]
        assert orders_node["data"]["details"]["platform"] == "postgres"

    def test_edges_contain_label(self, sample_lineage: dict[str, Any]) -> None:
        """Test that edges include edge_type as label."""
        elements = lineage_to_cytoscape_elements(sample_lineage, depth=3, direction="both")
        edges = _get_edges(elements)
        labels = {e["data"]["label"] for e in edges}
        assert "transforms" in labels
        assert "joins" in labels


# --- ASCII Fallback ---


class TestAsciiFallback:
    """Tests for _render_ascii_fallback()."""

    def test_renders_header_and_root(
        self, sample_lineage: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that ASCII fallback renders header and root node."""
        _render_ascii_fallback(sample_lineage, depth=2, direction="both")
        output = capsys.readouterr().out
        assert "Lineage Graph" in output
        assert "orders" in output
        assert "(root)" in output

    def test_respects_depth_limit(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test depth limit prevents deep traversal."""
        lineage: dict[str, Any] = {
            "root": "node_a",
            "datasets": {},
            "edges": [
                {"source": "node_a", "target": "node_b"},
                {"source": "node_b", "target": "node_c"},
                {"source": "node_c", "target": "node_d"},
            ],
            "jobs": {},
        }
        _render_ascii_fallback(lineage, depth=1, direction="downstream")
        output = capsys.readouterr().out
        assert "node_a" in output
        assert "node_b" in output
        # node_c and node_d should not appear at depth=1
        assert "node_c" not in output
        assert "node_d" not in output

    def test_shows_dataset_type(
        self, sample_lineage: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that dataset types are shown in brackets."""
        _render_ascii_fallback(sample_lineage, depth=2, direction="upstream")
        output = capsys.readouterr().out
        assert "[table]" in output

    def test_empty_edges(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test rendering with no edges."""
        lineage: dict[str, Any] = {
            "root": "solo",
            "datasets": {},
            "edges": [],
            "jobs": {},
        }
        _render_ascii_fallback(lineage)
        output = capsys.readouterr().out
        assert "solo" in output
        assert "no edges" in output

    def test_upstream_direction(
        self, sample_lineage: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test upstream direction in ASCII output."""
        _render_ascii_fallback(sample_lineage, depth=2, direction="upstream")
        output = capsys.readouterr().out
        assert "direction=upstream" in output


# --- Details Panel Rendering ---


class TestDetailsPanelRendering:
    """Tests for _render_dataset_details() and _render_job_details()."""

    def test_dataset_details_html(self) -> None:
        """Test dataset details render all fields."""
        html = _render_dataset_details(
            "orders",
            {
                "platform": "postgres",
                "type": "table",
                "description": "Customer orders",
                "owners": ["data-team"],
                "tags": ["production"],
                "schema": [{"name": "id"}, {"name": "total"}],
            },
        )
        assert "orders" in html
        assert "postgres" in html
        assert "table" in html
        assert "Customer orders" in html
        assert "data-team" in html
        assert "production" in html
        assert "<code>" in html

    def test_job_details_html(self) -> None:
        """Test job details render all fields."""
        html = _render_job_details(
            "etl_job",
            {
                "type": "dbt",
                "inputs": ["raw_data"],
                "outputs": ["staging_data"],
                "source_url": "https://github.com/example",
            },
        )
        assert "etl_job" in html
        assert "dbt" in html
        assert "raw_data" in html
        assert "staging_data" in html
        assert "github.com" in html

    def test_html_escaping_prevents_injection(self) -> None:
        """Test that user input is HTML-escaped."""
        html = _render_dataset_details(
            "<script>alert(1)</script>",
            {
                "platform": "<img onerror=alert(1)>",
            },
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<img" not in html

    def test_missing_optional_fields(self) -> None:
        """Test rendering with minimal metadata."""
        html = _render_dataset_details("basic_table", {})
        assert "basic_table" in html
        assert "Unknown" in html

    def test_empty_job_details(self) -> None:
        """Test job rendering with empty metadata."""
        html = _render_job_details("empty_job", {})
        assert "empty_job" in html
        assert "Unknown" in html

    def test_schema_truncation(self) -> None:
        """Test that schema columns beyond 10 are truncated."""
        schema = [{"name": f"col_{i}"} for i in range(15)]
        html = _render_dataset_details("wide_table", {"schema": schema})
        assert "+5 more" in html


# --- Export Function ---


class TestExport:
    """Tests for export_lineage_graph()."""

    def test_export_invalid_format_raises(self, sample_lineage: dict[str, Any]) -> None:
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported format"):
            export_lineage_graph(sample_lineage, "out.pdf", fmt="pdf")

    @patch("dataing_notebook.lineage_graph._get_cytoscape_widget")
    def test_export_png(
        self,
        mock_cyto: MagicMock,
        sample_lineage: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Test PNG export writes binary data."""
        mock_widget = MagicMock()
        mock_widget.get_png.return_value = b"\x89PNG fake data"
        mock_cyto.return_value.CytoscapeWidget.return_value = mock_widget

        output_file = str(tmp_path / "lineage.png")
        result = export_lineage_graph(sample_lineage, output_file, fmt="png")

        mock_widget.get_png.assert_called_once()
        assert result.endswith("lineage.png")

    @patch("dataing_notebook.lineage_graph._get_cytoscape_widget")
    def test_export_svg(
        self,
        mock_cyto: MagicMock,
        sample_lineage: dict[str, Any],
        tmp_path: Any,
    ) -> None:
        """Test SVG export writes text data."""
        mock_widget = MagicMock()
        mock_widget.get_svg.return_value = "<svg>fake</svg>"
        mock_cyto.return_value.CytoscapeWidget.return_value = mock_widget

        output_file = str(tmp_path / "lineage.svg")
        result = export_lineage_graph(sample_lineage, output_file, fmt="svg")

        mock_widget.get_svg.assert_called_once()
        assert result.endswith("lineage.svg")


# --- Widget Environment Detection ---


class TestWidgetEnvironment:
    """Tests for is_widget_environment()."""

    def test_returns_false_in_pytest(self) -> None:
        """Test that pytest environment is not a widget environment."""
        assert is_widget_environment() is False

    @patch("dataing_notebook.lineage_graph.get_ipython", create=True)
    def test_returns_false_for_terminal_shell(self, mock_get: MagicMock) -> None:
        """Test that terminal IPython shell returns False."""
        mock_shell = MagicMock()
        mock_shell.__class__.__name__ = "TerminalInteractiveShell"
        mock_get.return_value = mock_shell

        # Need to reimport the function to pick up mock
        from dataing_notebook.lineage_graph import is_widget_environment

        assert is_widget_environment() is False


# --- Render Lineage Graph Integration ---


class TestRenderLineageGraph:
    """Tests for render_lineage_graph() integration."""

    def test_returns_none_for_empty_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that empty data returns None."""
        result = render_lineage_graph({})
        assert result is None
        output = capsys.readouterr().out
        assert "No lineage data" in output

    def test_falls_back_to_ascii_outside_widget_env(
        self, sample_lineage: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that non-widget env falls back to ASCII output."""
        result = render_lineage_graph(sample_lineage, depth=2, direction="both")
        assert result is None
        output = capsys.readouterr().out
        assert "Lineage Graph" in output
        assert "orders" in output
