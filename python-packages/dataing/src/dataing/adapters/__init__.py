"""Adapters - Infrastructure implementations of core interfaces.

This package contains all the concrete implementations of the
Protocol interfaces defined in the core module.

Adapters are organized by type:
- datasource/: Data source adapters (PostgreSQL, DuckDB, MongoDB, etc.)
- lineage/: Lineage adapters (dbt, OpenLineage, Airflow, Dagster, DataHub, etc.)
- context/: Context gathering adapters

Note: LLM agents have been promoted to first-class citizens in the
dataing.agents package.
"""

from .context.engine import DefaultContextEngine
from .lineage import (
    BaseLineageAdapter,
    DatasetId,
    LineageAdapter,
    LineageGraph,
    get_lineage_registry,
)

__all__ = [
    # Context adapters
    "DefaultContextEngine",
    # Lineage adapters
    "BaseLineageAdapter",
    "DatasetId",
    "LineageAdapter",
    "LineageGraph",
    "get_lineage_registry",
]
