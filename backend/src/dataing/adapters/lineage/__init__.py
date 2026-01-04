"""Lineage adapter layer for unified lineage retrieval.

This package provides a pluggable adapter architecture that normalizes
different lineage sources (dbt, OpenLineage, Airflow, Dagster, DataHub, etc.)
into a unified interface.

The investigation engine can answer "where did this data come from?" and
"what depends on this?" regardless of which orchestration/catalog tools
the customer uses.

Example usage:
    from dataing.adapters.lineage import get_lineage_registry, DatasetId

    registry = get_lineage_registry()

    # Create a dbt adapter
    adapter = registry.create("dbt", {
        "manifest_path": "/path/to/manifest.json",
        "target_platform": "snowflake",
    })

    # Get upstream datasets
    dataset_id = DatasetId(platform="snowflake", name="analytics.orders")
    upstream = await adapter.get_upstream(dataset_id, depth=2)

    # Create composite adapter for multiple sources
    composite = registry.create_composite([
        {"provider": "dbt", "priority": 10, "manifest_path": "..."},
        {"provider": "openlineage", "priority": 5, "base_url": "..."},
    ])
"""

# Import all adapters to register them
from dataing.adapters.lineage import adapters as _adapters  # noqa: F401

# Re-export public API
from dataing.adapters.lineage.base import BaseLineageAdapter
from dataing.adapters.lineage.exceptions import (
    ColumnLineageNotSupportedError,
    DatasetNotFoundError,
    LineageDepthExceededError,
    LineageError,
    LineageParseError,
    LineageProviderAuthError,
    LineageProviderConnectionError,
    LineageProviderNotFoundError,
)
from dataing.adapters.lineage.graph import build_graph_from_traversal, merge_graphs
from dataing.adapters.lineage.protocols import LineageAdapter
from dataing.adapters.lineage.registry import (
    LineageConfigField,
    LineageConfigSchema,
    LineageProviderDefinition,
    LineageRegistry,
    get_lineage_registry,
    register_lineage_adapter,
)
from dataing.adapters.lineage.types import (
    Column,
    ColumnLineage,
    Dataset,
    DatasetId,
    DatasetType,
    Job,
    JobRun,
    JobType,
    LineageCapabilities,
    LineageEdge,
    LineageGraph,
    LineageProviderInfo,
    LineageProviderType,
    RunStatus,
)

__all__ = [
    # Base and Protocol
    "BaseLineageAdapter",
    "LineageAdapter",
    # Registry
    "LineageRegistry",
    "LineageProviderDefinition",
    "LineageConfigSchema",
    "LineageConfigField",
    "get_lineage_registry",
    "register_lineage_adapter",
    # Types
    "Column",
    "ColumnLineage",
    "Dataset",
    "DatasetId",
    "DatasetType",
    "Job",
    "JobRun",
    "JobType",
    "LineageCapabilities",
    "LineageEdge",
    "LineageGraph",
    "LineageProviderInfo",
    "LineageProviderType",
    "RunStatus",
    # Graph utilities
    "build_graph_from_traversal",
    "merge_graphs",
    # Exceptions
    "ColumnLineageNotSupportedError",
    "DatasetNotFoundError",
    "LineageDepthExceededError",
    "LineageError",
    "LineageParseError",
    "LineageProviderAuthError",
    "LineageProviderConnectionError",
    "LineageProviderNotFoundError",
]
