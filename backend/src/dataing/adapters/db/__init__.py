"""Application database adapters.

This package contains adapters for the application's own databases,
NOT data source adapters for tenant data. For data source adapters,
see dataing.adapters.datasource.

Contents:
- app_db: Application metadata database (tenants, data sources, API keys)
"""

from .app_db import AppDatabase
from .mock import MockDatabaseAdapter

__all__ = ["AppDatabase", "MockDatabaseAdapter"]
