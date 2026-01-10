"""SQL database adapters.

This module provides adapters for SQL-speaking data sources:
- PostgreSQL
- MySQL
- Trino
- Snowflake
- BigQuery
- Redshift
- DuckDB
- SQLite
"""

from dataing.adapters.datasource.sql.base import SQLAdapter
from dataing.adapters.datasource.sql.sqlite import SQLiteAdapter

__all__ = ["SQLAdapter", "SQLiteAdapter"]
