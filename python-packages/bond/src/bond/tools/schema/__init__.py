"""Schema toolset for Bond agents.

Provides on-demand schema lookup for database tables and lineage.
"""

from bond.tools.schema._models import (
    ColumnSchema,
    GetDownstreamRequest,
    GetTableSchemaRequest,
    GetUpstreamRequest,
    ListTablesRequest,
    TableSchema,
)
from bond.tools.schema._protocols import SchemaLookupProtocol
from bond.tools.schema.tools import schema_toolset

__all__ = [
    # Protocol
    "SchemaLookupProtocol",
    # Models
    "GetTableSchemaRequest",
    "ListTablesRequest",
    "GetUpstreamRequest",
    "GetDownstreamRequest",
    "TableSchema",
    "ColumnSchema",
    # Toolset
    "schema_toolset",
]
