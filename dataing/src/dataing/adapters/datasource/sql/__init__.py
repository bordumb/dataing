"""SQL database adapters.

This module provides adapters for SQL-speaking data sources:
- PostgreSQL
- MySQL
- Trino
- Snowflake
- BigQuery
- Redshift
- DuckDB
"""

from dataing.adapters.datasource.sql.base import SQLAdapter

__all__ = ["SQLAdapter"]
