"""Adapters - Infrastructure implementations of core interfaces.

This package contains all the concrete implementations of the
Protocol interfaces defined in the core module.

Adapters are organized by type:
- datasource/: Data source adapters (PostgreSQL, DuckDB, MongoDB, etc.)
- lineage/: Lineage adapters (dbt, OpenLineage, Airflow, Dagster, DataHub, etc.)
- llm/: LLM client adapters (Anthropic)
- context/: Context gathering adapters
"""

from .context.engine import DefaultContextEngine
from .lineage import (
    BaseLineageAdapter,
    DatasetId,
    LineageAdapter,
    LineageGraph,
    get_lineage_registry,
)
from .llm.client import AnthropicClient
from .llm.prompt_manager import PromptManager

__all__ = [
    # LLM adapters
    "AnthropicClient",
    "PromptManager",
    # Context adapters
    "DefaultContextEngine",
    # Lineage adapters
    "BaseLineageAdapter",
    "DatasetId",
    "LineageAdapter",
    "LineageGraph",
    "get_lineage_registry",
]
