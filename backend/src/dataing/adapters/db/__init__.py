"""Database adapters implementing the DatabaseAdapter protocol."""

from .duckdb import DuckDBAdapter
from .mock import MockDatabaseAdapter
from .postgres import PostgresAdapter
from .trino import TrinoAdapter

__all__ = ["PostgresAdapter", "TrinoAdapter", "MockDatabaseAdapter", "DuckDBAdapter"]
