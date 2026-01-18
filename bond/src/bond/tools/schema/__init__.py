"""Schema toolset for Bond agents.

Provides on-demand schema lookup for database tables and lineage.
"""

from bond.tools.schema._protocols import SchemaLookupProtocol

__all__ = [
    "SchemaLookupProtocol",
]
