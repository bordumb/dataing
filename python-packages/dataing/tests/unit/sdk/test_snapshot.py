"""Unit tests for SDK snapshot deserialization."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from dataing.sdk.snapshot import (
    HydratedState,
    NavigableSchema,
    QueryableLineage,
    SchemaColumn,
    SchemaTable,
    load_snapshot,
)


class TestSchemaColumn:
    """Tests for SchemaColumn model."""

    def test_create_column(self) -> None:
        """Test creating a schema column."""
        col = SchemaColumn(
            name="user_id",
            data_type="integer",
            nullable=False,
            description="Primary user identifier",
        )
        assert col.name == "user_id"
        assert col.data_type == "integer"
        assert col.nullable is False
        assert col.description == "Primary user identifier"

    def test_column_defaults(self) -> None:
        """Test column default values."""
        col = SchemaColumn(name="email", data_type="varchar")
        assert col.nullable is True
        assert col.description is None


class TestSchemaTable:
    """Tests for SchemaTable model."""

    def test_create_table(self) -> None:
        """Test creating a schema table."""
        cols = [
            SchemaColumn(name="id", data_type="integer"),
            SchemaColumn(name="name", data_type="varchar"),
        ]
        table = SchemaTable(name="users", columns=cols, row_count=1000)
        assert table.name == "users"
        assert len(table.columns) == 2
        assert table.row_count == 1000

    def test_column_names(self) -> None:
        """Test getting column names."""
        cols = [
            SchemaColumn(name="id", data_type="integer"),
            SchemaColumn(name="email", data_type="varchar"),
        ]
        table = SchemaTable(name="users", columns=cols)
        names = table.column_names()
        assert names == ["id", "email"]

    def test_get_column(self) -> None:
        """Test getting column by name."""
        cols = [
            SchemaColumn(name="id", data_type="integer"),
            SchemaColumn(name="email", data_type="varchar"),
        ]
        table = SchemaTable(name="users", columns=cols)
        col = table.get_column("email")
        assert col is not None
        assert col.data_type == "varchar"

    def test_get_column_not_found(self) -> None:
        """Test getting non-existent column."""
        table = SchemaTable(name="users", columns=[])
        col = table.get_column("nonexistent")
        assert col is None


class TestNavigableSchema:
    """Tests for NavigableSchema."""

    def test_empty_schema(self) -> None:
        """Test navigable schema with no data."""
        schema = NavigableSchema(None)
        assert len(schema.tables) == 0
        assert schema.table_names() == []

    def test_parse_target_table(self) -> None:
        """Test parsing target table from schema data."""
        data = {
            "target_table": {
                "name": "orders",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "amount", "type": "decimal"},
                ],
            }
        }
        schema = NavigableSchema(data)
        assert "orders" in schema.tables
        table = schema.tables["orders"]
        assert len(table.columns) == 2

    def test_parse_reference_tables(self) -> None:
        """Test parsing reference tables."""
        data = {
            "reference_tables": [
                {
                    "name": "customers",
                    "columns": [{"name": "id", "data_type": "integer"}],
                },
                {
                    "name": "products",
                    "columns": [{"name": "sku", "data_type": "varchar"}],
                },
            ]
        }
        schema = NavigableSchema(data)
        assert len(schema.tables) == 2
        assert "customers" in schema.tables
        assert "products" in schema.tables

    def test_schema_repr(self) -> None:
        """Test schema string representation."""
        schema = NavigableSchema({"target_table": {"name": "orders", "columns": []}})
        repr_str = repr(schema)
        assert "NavigableSchema" in repr_str
        assert "orders" in repr_str


class TestQueryableLineage:
    """Tests for QueryableLineage."""

    def test_empty_lineage(self) -> None:
        """Test queryable lineage with no data."""
        lineage = QueryableLineage(None)
        assert lineage.target == ""
        assert lineage.upstream() == []
        assert lineage.downstream() == []

    def test_lineage_with_data(self) -> None:
        """Test lineage with upstream and downstream."""
        data = {
            "target": "analytics.orders",
            "upstream": ["raw.orders", "raw.customers"],
            "downstream": ["analytics.revenue", "analytics.kpis"],
            "depth": 2,
        }
        lineage = QueryableLineage(data)
        assert lineage.target == "analytics.orders"
        assert lineage.upstream() == ["raw.orders", "raw.customers"]
        assert lineage.downstream() == ["analytics.revenue", "analytics.kpis"]
        assert lineage.depth == 2

    def test_upstream_for_non_target(self) -> None:
        """Test upstream query for non-target table."""
        data = {
            "target": "orders",
            "upstream": ["customers"],
        }
        lineage = QueryableLineage(data)
        # Non-target tables return empty (we don't have full graph)
        assert lineage.upstream("other_table") == []

    def test_lineage_repr(self) -> None:
        """Test lineage string representation."""
        data = {
            "target": "orders",
            "upstream": ["a", "b"],
            "downstream": ["c"],
        }
        lineage = QueryableLineage(data)
        repr_str = repr(lineage)
        assert "QueryableLineage" in repr_str
        assert "orders" in repr_str


class TestHydratedState:
    """Tests for HydratedState dataclass."""

    def test_create_minimal_state(self) -> None:
        """Test creating minimal hydrated state."""
        state = HydratedState(
            version="1.0",
            investigation_id=str(uuid4()),
            checkpoint="start",
        )
        assert state.version == "1.0"
        assert state.checkpoint == "start"
        assert state.hypotheses == []
        assert state.evidence == []
        assert state.synthesis is None

    def test_create_full_state(self) -> None:
        """Test creating state with all fields."""
        state = HydratedState(
            version="1.0",
            investigation_id=str(uuid4()),
            checkpoint="complete",
            alert={"dataset_id": "orders"},
            hypotheses=[{"id": "h1", "title": "Test"}],
            evidence=[{"hypothesis_id": "h1", "supports": True}],
            synthesis={"root_cause": "ETL failure", "confidence": 0.95},
            metadata={"custom_key": "value"},
        )
        assert len(state.hypotheses) == 1
        assert len(state.evidence) == 1
        assert state.synthesis["confidence"] == 0.95

    def test_summary(self) -> None:
        """Test state summary output."""
        state = HydratedState(
            version="1.0",
            investigation_id="inv-123",
            checkpoint="complete",
            hypotheses=[{"id": "h1"}],
            evidence=[{"id": "e1"}, {"id": "e2"}],
            synthesis={"confidence": 0.9},
        )
        summary = state.summary()
        assert "inv-123" in summary
        assert "complete" in summary
        assert "Hypotheses: 1" in summary
        assert "Evidence: 2" in summary
        assert "confidence=0.9" in summary

    def test_repr(self) -> None:
        """Test state string representation."""
        state = HydratedState(
            version="1.0",
            investigation_id="inv-123",
            checkpoint="start",
        )
        repr_str = repr(state)
        assert "HydratedState" in repr_str
        assert "inv-123" in repr_str


class TestLoadSnapshot:
    """Tests for load_snapshot function."""

    def test_load_from_bytes(self) -> None:
        """Test loading snapshot from bytes."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "start",
            "hypotheses": [{"id": "h1"}],
        }
        state = load_snapshot(json.dumps(data).encode("utf-8"))
        assert state.version == "1.0"
        assert len(state.hypotheses) == 1

    def test_load_from_string(self) -> None:
        """Test loading snapshot from JSON string."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "complete",
        }
        state = load_snapshot(json.dumps(data))
        assert state.checkpoint == "complete"

    def test_load_from_dict(self) -> None:
        """Test loading snapshot from dict."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "hypothesis_generated",
            "alert": {"dataset_id": "orders"},
        }
        state = load_snapshot(data)
        assert state.alert is not None
        assert state.alert["dataset_id"] == "orders"

    def test_load_with_schema(self) -> None:
        """Test loading snapshot with schema data."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "start",
            "schema_snapshot": {
                "target_table": {
                    "name": "orders",
                    "columns": [{"name": "id", "type": "integer"}],
                }
            },
        }
        state = load_snapshot(data)
        assert "orders" in state.schema.tables

    def test_load_with_lineage(self) -> None:
        """Test loading snapshot with lineage data."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "start",
            "lineage_snapshot": {
                "target": "orders",
                "upstream": ["customers"],
                "downstream": ["revenue"],
            },
        }
        state = load_snapshot(data)
        assert state.lineage is not None
        assert state.lineage.target == "orders"

    def test_load_without_lineage(self) -> None:
        """Test loading snapshot without lineage."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "start",
        }
        state = load_snapshot(data)
        assert state.lineage is None

    def test_load_with_synthesis(self) -> None:
        """Test loading snapshot with synthesis."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "complete",
            "synthesis": {
                "root_cause": "ETL job failure in upstream pipeline",
                "confidence": 0.92,
                "recommendations": ["Check ETL logs", "Verify source data"],
            },
        }
        state = load_snapshot(data)
        assert state.synthesis is not None
        assert state.synthesis["root_cause"] == "ETL job failure in upstream pipeline"

    def test_load_invalid_bytes(self) -> None:
        """Test loading invalid bytes raises error."""
        with pytest.raises(ValueError, match="Invalid snapshot data"):
            load_snapshot(b"not valid json")

    def test_load_invalid_string(self) -> None:
        """Test loading invalid string raises error."""
        with pytest.raises(ValueError, match="Invalid snapshot data"):
            load_snapshot("not valid json")

    def test_load_invalid_type(self) -> None:
        """Test loading invalid type raises error."""
        with pytest.raises(ValueError, match="Invalid snapshot_data type"):
            load_snapshot(12345)  # type: ignore[arg-type]

    def test_version_compatibility_warning(self) -> None:
        """Test version mismatch produces warning."""
        data = {
            "version": "2.0",  # Different major version
            "investigation_id": str(uuid4()),
            "checkpoint": "start",
        }
        with pytest.warns(UserWarning, match="may not be fully compatible"):
            load_snapshot(data)

    def test_load_with_metadata(self) -> None:
        """Test loading snapshot with metadata."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "complete",
            "metadata": {"custom_key": "custom_value"},
        }
        state = load_snapshot(data)
        assert state.metadata["custom_key"] == "custom_value"

    def test_load_with_environment(self) -> None:
        """Test loading snapshot with environment data."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "complete",
            "environment": {
                "python_version": "3.11.0",
                "platform": "linux",
            },
        }
        state = load_snapshot(data)
        assert state.environment["python_version"] == "3.11.0"

    def test_lazy_dataframes_default(self) -> None:
        """Test that dataframes are lazy by default."""
        data = {
            "version": "1.0",
            "investigation_id": str(uuid4()),
            "checkpoint": "complete",
            "sample_data_inline": {"orders": "e30="},  # Base64 for {}
        }
        state = load_snapshot(data, lazy_dataframes=True)
        # Should have the key but not be a DataFrame yet
        assert "orders" in state.dataframes

    def test_load_all_checkpoints(self) -> None:
        """Test loading snapshots from all checkpoint types."""
        checkpoints = [
            "start",
            "hypothesis_generated",
            "evidence_collected",
            "complete",
            "failed",
        ]
        for checkpoint in checkpoints:
            data = {
                "version": "1.0",
                "investigation_id": str(uuid4()),
                "checkpoint": checkpoint,
            }
            state = load_snapshot(data)
            assert state.checkpoint == checkpoint
