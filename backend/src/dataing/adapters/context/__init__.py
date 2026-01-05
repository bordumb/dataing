"""Context gathering adapters.

This package provides modular context gathering for investigations:
- SchemaContextBuilder: Builds and formats schema context
- QueryContext: Executes queries and formats results
- AnomalyContext: Confirms anomalies in data
- CorrelationContext: Finds cross-table patterns
- ContextEngine: Thin coordinator for all modules

Note: For resolving tenant data source adapters, use AdapterRegistry
from dataing.adapters.datasource instead of the old DatabaseContext.

Note: Lineage fetching now uses the pluggable lineage adapter layer.
See dataing.adapters.lineage for the full lineage adapter API.
"""

from dataing.core.domain_types import InvestigationContext

from .anomaly_context import AnomalyConfirmation, AnomalyContext, ColumnProfile
from .correlation_context import Correlation, CorrelationContext, TimeSeriesPattern
from .engine import ContextEngine, DefaultContextEngine, EnrichedContext
from .query_context import QueryContext, QueryExecutionError
from .schema_context import SchemaContextBuilder

__all__ = [
    # Core engine
    "ContextEngine",
    "DefaultContextEngine",
    "EnrichedContext",
    "InvestigationContext",
    # Schema
    "SchemaContextBuilder",
    # Query execution
    "QueryContext",
    "QueryExecutionError",
    # Anomaly confirmation
    "AnomalyContext",
    "AnomalyConfirmation",
    "ColumnProfile",
    # Correlation analysis
    "CorrelationContext",
    "Correlation",
    "TimeSeriesPattern",
]
