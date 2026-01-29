"""Snapshot deserialization for local hydration.

This module provides tools to deserialize investigation snapshots into
live Python objects for debugging in JupyterLab notebooks.
"""

from __future__ import annotations

import io
import json
import logging
import warnings
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Current SDK version for compatibility checking
SDK_VERSION = "1.0"


class SchemaColumn(BaseModel):
    """Column in a table schema."""

    name: str
    data_type: str
    nullable: bool = True
    description: str | None = None


class SchemaTable(BaseModel):
    """Table schema with columns."""

    name: str
    columns: list[SchemaColumn] = []
    description: str | None = None
    row_count: int | None = None

    def column_names(self) -> list[str]:
        """Get list of column names."""
        return [col.name for col in self.columns]

    def get_column(self, name: str) -> SchemaColumn | None:
        """Get column by name."""
        for col in self.columns:
            if col.name == name:
                return col
        return None


class NavigableSchema:
    """Navigable schema for exploring table structure.

    Provides dictionary-like access to tables:
        schema.tables['orders'].columns
    """

    def __init__(self, schema_data: dict[str, Any] | None) -> None:
        """Initialize navigable schema.

        Args:
            schema_data: Raw schema data from snapshot.
        """
        self._raw = schema_data or {}
        self._tables: dict[str, SchemaTable] = {}
        self._parse_schema()

    def _parse_schema(self) -> None:
        """Parse raw schema data into SchemaTable objects."""
        # Handle target_table
        if "target_table" in self._raw:
            target = self._raw["target_table"]
            if isinstance(target, dict) and "name" in target:
                table = self._parse_table(target)
                self._tables[table.name] = table

        # Handle reference_tables
        if "reference_tables" in self._raw:
            for table_data in self._raw.get("reference_tables", []):
                if isinstance(table_data, dict) and "name" in table_data:
                    table = self._parse_table(table_data)
                    self._tables[table.name] = table

    def _parse_table(self, table_data: dict[str, Any]) -> SchemaTable:
        """Parse a table dictionary into SchemaTable."""
        columns = []
        for col_data in table_data.get("columns", []):
            if isinstance(col_data, dict):
                columns.append(
                    SchemaColumn(
                        name=col_data.get("name", ""),
                        data_type=col_data.get("data_type", col_data.get("type", "unknown")),
                        nullable=col_data.get("nullable", True),
                        description=col_data.get("description"),
                    )
                )
        return SchemaTable(
            name=table_data.get("name", ""),
            columns=columns,
            description=table_data.get("description"),
            row_count=table_data.get("row_count"),
        )

    @property
    def tables(self) -> dict[str, SchemaTable]:
        """Get all tables as a dictionary."""
        return self._tables

    def table_names(self) -> list[str]:
        """Get list of table names."""
        return list(self._tables.keys())

    def __repr__(self) -> str:
        """Return string representation."""
        return f"NavigableSchema(tables={list(self._tables.keys())})"


class QueryableLineage:
    """Queryable lineage for exploring data dependencies.

    Provides methods to query upstream and downstream dependencies:
        lineage.upstream('orders')
        lineage.downstream('orders')
    """

    def __init__(self, lineage_data: dict[str, Any] | None) -> None:
        """Initialize queryable lineage.

        Args:
            lineage_data: Raw lineage data from snapshot.
        """
        self._raw = lineage_data or {}
        self._target: str = self._raw.get("target", "")
        self._upstream: list[str] = self._raw.get("upstream", [])
        self._downstream: list[str] = self._raw.get("downstream", [])
        self._depth: int = self._raw.get("depth", 2)

    @property
    def target(self) -> str:
        """Get the target table."""
        return self._target

    def upstream(self, table: str | None = None) -> list[str]:
        """Get upstream dependencies.

        Args:
            table: Optional table name (defaults to target).

        Returns:
            List of upstream table names.
        """
        if table is None or table == self._target:
            return self._upstream
        # For non-target tables, we don't have the full graph
        return []

    def downstream(self, table: str | None = None) -> list[str]:
        """Get downstream dependencies.

        Args:
            table: Optional table name (defaults to target).

        Returns:
            List of downstream table names.
        """
        if table is None or table == self._target:
            return self._downstream
        # For non-target tables, we don't have the full graph
        return []

    @property
    def depth(self) -> int:
        """Get the depth of lineage captured."""
        return self._depth

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"QueryableLineage(target={self._target!r}, "
            f"upstream={len(self._upstream)}, downstream={len(self._downstream)})"
        )


@dataclass
class HydratedState:
    """Hydrated investigation state for local debugging.

    Contains all the investigation data in Python-native objects:
    - alert: The anomaly alert that triggered the investigation
    - hypotheses: List of generated hypotheses
    - evidence: List of collected evidence
    - synthesis: Final synthesis result (if complete)
    - dataframes: Dictionary of table name -> pandas DataFrame
    - schema: Navigable schema object
    - lineage: Queryable lineage object
    - metadata: Additional metadata from snapshot

    Attributes:
        version: Schema version of the snapshot.
        investigation_id: UUID of the investigation.
        checkpoint: Checkpoint where snapshot was captured.
        alert: The anomaly alert data.
        hypotheses: List of hypothesis dictionaries.
        evidence: List of evidence dictionaries.
        synthesis: Synthesis result dictionary (if available).
        dataframes: Dictionary of table name to DataFrame.
        schema: Navigable schema object.
        lineage: Queryable lineage object.
        metadata: Additional snapshot metadata.
        environment: Environment metadata from capture time.
    """

    version: str
    investigation_id: str
    checkpoint: str
    alert: dict[str, Any] | None = None
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    synthesis: dict[str, Any] | None = None
    dataframes: dict[str, Any] = field(default_factory=dict)  # pd.DataFrame
    schema: NavigableSchema = field(default_factory=lambda: NavigableSchema(None))
    lineage: QueryableLineage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """Get a human-readable summary of the state."""
        lines = [
            f"Investigation: {self.investigation_id}",
            f"Checkpoint: {self.checkpoint}",
            f"Version: {self.version}",
            f"Hypotheses: {len(self.hypotheses)}",
            f"Evidence: {len(self.evidence)}",
            f"DataFrames: {list(self.dataframes.keys())}",
        ]
        if self.synthesis:
            conf = self.synthesis.get("confidence", "N/A")
            lines.append(f"Synthesis: confidence={conf}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"HydratedState(investigation_id={self.investigation_id!r}, "
            f"checkpoint={self.checkpoint!r}, "
            f"hypotheses={len(self.hypotheses)}, "
            f"evidence={len(self.evidence)})"
        )


def _deserialize_dataframe(data: bytes, table_name: str) -> Any:
    """Deserialize bytes to pandas DataFrame.

    Attempts Parquet format first, falls back to JSON.

    Args:
        data: Raw bytes from snapshot.
        table_name: Name of the table (for error messages).

    Returns:
        pandas DataFrame or None if deserialization fails.
    """
    try:
        import pandas as pd

        # Try Parquet first
        try:
            return pd.read_parquet(io.BytesIO(data))
        except Exception:
            # Fall back to JSON
            try:
                return pd.read_json(io.BytesIO(data))
            except Exception:
                # Try as raw JSON
                try:
                    json_data = json.loads(data.decode("utf-8"))
                    return pd.DataFrame(json_data)
                except Exception:
                    pass

        logger.warning(f"Could not deserialize DataFrame for {table_name}")
        return None
    except ImportError:
        warnings.warn(
            "pandas not installed. Install with: pip install pandas",
            UserWarning,
            stacklevel=2,
        )
        return None


def _check_version_compatibility(snapshot_version: str) -> None:
    """Check if snapshot version is compatible with SDK.

    Args:
        snapshot_version: Version string from snapshot.
    """
    if snapshot_version != SDK_VERSION:
        major_snapshot = snapshot_version.split(".")[0] if snapshot_version else "0"
        major_sdk = SDK_VERSION.split(".")[0]
        if major_snapshot != major_sdk:
            warnings.warn(
                f"Snapshot version {snapshot_version} may not be fully compatible "
                f"with SDK version {SDK_VERSION}. Some features may not work.",
                UserWarning,
                stacklevel=3,
            )


def load_snapshot(
    snapshot_data: bytes | str | dict[str, Any],
    lazy_dataframes: bool = True,
) -> HydratedState:
    """Load and deserialize an investigation snapshot.

    Converts raw snapshot bytes/JSON into a HydratedState object with
    navigable schema, queryable lineage, and pandas DataFrames.

    Args:
        snapshot_data: Snapshot as bytes, JSON string, or dict.
        lazy_dataframes: If True, delay DataFrame deserialization until accessed.
            Set to False to deserialize all DataFrames immediately.

    Returns:
        HydratedState with all investigation data.

    Raises:
        ValueError: If snapshot data is invalid.

    Example:
        >>> state = load_snapshot(snapshot_bytes)
        >>> print(state.synthesis.get('root_cause'))
        >>> df = state.dataframes.get('orders')
    """
    # Parse input data
    if isinstance(snapshot_data, bytes):
        try:
            data = json.loads(snapshot_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid snapshot data: could not parse JSON: {e}") from e
    elif isinstance(snapshot_data, str):
        try:
            data = json.loads(snapshot_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid snapshot data: could not parse JSON: {e}") from e
    elif isinstance(snapshot_data, dict):
        data = snapshot_data
    else:
        raise ValueError(f"Invalid snapshot_data type: {type(snapshot_data)}")

    # Check version compatibility
    version = data.get("version", "1.0")
    _check_version_compatibility(version)

    # Extract investigation identifiers
    investigation_id = str(data.get("investigation_id", "unknown"))
    checkpoint = data.get("checkpoint", "unknown")

    # Parse schema
    schema_data = data.get("schema_snapshot")
    schema = NavigableSchema(schema_data)

    # Parse lineage
    lineage_data = data.get("lineage_snapshot")
    lineage = QueryableLineage(lineage_data) if lineage_data else None

    # Parse sample data into DataFrames
    dataframes: dict[str, Any] = {}
    inline_data = data.get("sample_data_inline", {})
    if inline_data and not lazy_dataframes:
        for table_name, table_data in inline_data.items():
            # Handle base64 encoded bytes
            if isinstance(table_data, str):
                import base64

                try:
                    raw_bytes = base64.b64decode(table_data)
                except Exception:
                    raw_bytes = table_data.encode("utf-8")
            elif isinstance(table_data, bytes):
                raw_bytes = table_data
            else:
                continue

            df = _deserialize_dataframe(raw_bytes, table_name)
            if df is not None:
                dataframes[table_name] = df

    # For lazy loading, store the raw data and deserialize on access
    if lazy_dataframes and inline_data:

        class LazyDataFrameDict(dict):  # type: ignore[type-arg]
            """Dictionary that lazily deserializes DataFrames on access."""

            def __init__(self, raw_data: dict[str, Any]) -> None:
                """Initialize lazy dict."""
                super().__init__()
                self._raw = raw_data
                self._loaded: dict[str, Any] = {}

            def __getitem__(self, key: str) -> Any:
                """Get item, deserializing on first access."""
                if key in self._loaded:
                    return self._loaded[key]
                if key in self._raw:
                    table_data = self._raw[key]
                    if isinstance(table_data, str):
                        import base64

                        try:
                            raw_bytes = base64.b64decode(table_data)
                        except Exception:
                            raw_bytes = table_data.encode("utf-8")
                    elif isinstance(table_data, bytes):
                        raw_bytes = table_data
                    else:
                        raise KeyError(key)
                    df = _deserialize_dataframe(raw_bytes, key)
                    self._loaded[key] = df
                    return df
                raise KeyError(key)

            def get(self, key: str, default: Any = None) -> Any:
                """Get item with default."""
                try:
                    return self[key]
                except KeyError:
                    return default

            def keys(self) -> Any:
                """Get all keys."""
                return self._raw.keys()

            def __contains__(self, key: object) -> bool:
                """Check if key exists."""
                return key in self._raw

            def __len__(self) -> int:
                """Get number of items."""
                return len(self._raw)

            def __repr__(self) -> str:
                """Return string representation."""
                return f"LazyDataFrameDict(tables={list(self._raw.keys())})"

        dataframes = LazyDataFrameDict(inline_data)

    return HydratedState(
        version=version,
        investigation_id=investigation_id,
        checkpoint=checkpoint,
        alert=data.get("alert"),
        hypotheses=data.get("hypotheses", []),
        evidence=data.get("evidence", []),
        synthesis=data.get("synthesis"),
        dataframes=dataframes,
        schema=schema,
        lineage=lineage,
        metadata=data.get("metadata", {}),
        environment=data.get("environment", {}),
    )
